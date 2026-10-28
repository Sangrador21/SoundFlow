import type { Lease, Song, Ticket } from "../../types/api";
import { ClusterApi, ApiError } from "../../services/cluster-api";
import { delay, errorMessage } from "../../utils/format";
import type { EngineEvent, PlayerEngine } from "./audio/audio-engine";
import { PcmDecoder, SAMPLE_RATE } from "./audio/pcm-decoder";
import type { OfflineSource } from "../offline/offline-store";

export type PlaybackStatus =
  | "idle"
  | "loading"
  | "waiting"
  | "buffering"
  | "playing"
  | "paused"
  | "ended"
  | "error";
export interface QueueItem {
  key: string;
  song: Song;
}
export interface PlaybackState {
  current: Song | null;
  status: PlaybackStatus;
  position: number;
  bufferedUntil: number;
  volume: number;
  queue: QueueItem[];
  queueOpen: boolean;
  entry: string | null;
  server: string | null;
  waitPosition: number;
  message: string;
  source: "server" | "local" | null;
}
export class PlaybackController {
  private state: PlaybackState = {
    current: null,
    status: "idle",
    position: 0,
    bufferedUntil: 0,
    volume: 0.7,
    queue: [],
    queueOpen: false,
    entry: null,
    server: null,
    waitPosition: 0,
    message: "Elige una canción para comenzar.",
    source: null,
  };
  private listeners = new Set<() => void>();
  private history: Song[] = [];
  private generation = 0;
  private abort: AbortController | null = null;
  private lease: Lease | null = null;
  private start = 0;
  private shouldPause = false;
  private queueKey = 0;
  private receivedFrames = 0;

  constructor(
    private api: ClusterApi,
    private readonly engine: PlayerEngine,
    private readonly offline?: OfflineSource,
  ) {
    engine.onEvent = (event) => this.handleEngine(event);
  }
  getSnapshot = (): PlaybackState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  private update(changes: Partial<PlaybackState>): void {
    this.state = { ...this.state, ...changes };
    this.listeners.forEach((listener) => listener());
  }
  private cancel(): void {
    this.abort?.abort();
    this.abort = null;
    if (this.lease) this.api.release(this.lease);
    this.lease = null;
  }
  setApi(api: ClusterApi): void {
    this.stop();
    this.api = api;
  }

  play(
    song: Song,
    start = 0,
    remember = true,
    paused = false,
    local = false,
  ): void {
    const useLocal = local || navigator.onLine === false;
    if (useLocal && !this.offline?.has(song.id)) {
      this.update({
        message:
          "Esta canción no tiene una copia completa disponible sin conexión.",
      });
      return;
    }
    // El permiso de audio debe solicitarse en el mismo gesto del usuario.
    const ready = this.engine.unlock();
    ready.catch(() => undefined);
    if (remember && this.state.current && this.state.current.id !== song.id)
      this.history.push(this.state.current);
    this.cancel();
    const id = ++this.generation;
    this.engine.reset(id, paused);
    this.abort = new AbortController();
    const requestedStart = Math.max(
      0,
      Math.min(start, Math.max(0, song.duration - 0.05)),
    );
    this.start = Math.round(requestedStart * SAMPLE_RATE) / SAMPLE_RATE;
    this.receivedFrames = 0;
    this.shouldPause = paused;
    this.update({
      current: song,
      status: "loading",
      position: this.start,
      bufferedUntil: this.start,
      server: null,
      entry: null,
      waitPosition: 0,
      message: "Preparando tu canción…",
      source: useLocal ? "local" : "server",
    });
    const signal = this.abort.signal;
    void ready
      .then(() => {
        if (id !== this.generation || signal.aborted) return;
        this.engine.reset(id, paused);
        return useLocal
          ? this.playLocal(song, id, signal)
          : this.download(song, id, signal);
      })
      .catch((error) => {
        if (id === this.generation && !signal.aborted) this.fail(error);
      });
  }
  playOffline(song: Song): void {
    this.play(song, 0, true, false, true);
  }

  private async playLocal(
    song: Song,
    id: number,
    signal: AbortSignal,
  ): Promise<void> {
    const copy = await this.offline?.get(song.id);
    if (signal.aborted || id !== this.generation) return;
    if (!copy || !this.engine.decodeFile)
      throw new Error(
        "La copia local ya no está disponible. Vuelve a guardarla con conexión.",
      );
    const audio = await this.engine.decodeFile(copy.blob);
    if (signal.aborted || id !== this.generation) return;
    if (!audio.length || audio.sampleRate !== SAMPLE_RATE)
      throw new Error("La copia local tiene un formato de audio incompatible.");
    this.start = Math.min(this.start, Math.max(0, audio.duration - 0.05));
    this.update({
      current: { ...song, duration: audio.duration },
      position: this.start,
      bufferedUntil: this.start,
      source: "local",
      server: null,
      entry: null,
      status: this.shouldPause ? "paused" : "buffering",
      message: "Reproduciendo la copia guardada en este dispositivo.",
    });
    void this.offline?.touch(song.id).catch(() => {});
    const left = audio.getChannelData(0);
    const right = audio.getChannelData(Math.min(1, audio.numberOfChannels - 1));
    for (
      let offset = Math.round(this.start * SAMPLE_RATE);
      offset < audio.length;
      offset += 65536
    ) {
      while (this.state.bufferedUntil - this.state.position > 20)
        await delay(100, signal);
      if (signal.aborted || id !== this.generation) return;
      const end = Math.min(offset + 65536, audio.length);
      this.engine.feed(id, {
        left: left.slice(offset, end),
        right: right.slice(offset, end),
        frames: end - offset,
      });
      this.update({ bufferedUntil: end / SAMPLE_RATE });
    }
    if (!signal.aborted && id === this.generation) this.engine.finish(id);
  }
  private async download(
    song: Song,
    id: number,
    signal: AbortSignal,
  ): Promise<void> {
    let recoveryStarted = 0;
    while (!signal.aborted && id === this.generation) {
      let lease: Lease | null = null;
      const requestAbort = new AbortController();
      const cancel = () => requestAbort.abort();
      signal.addEventListener("abort", cancel, { once: true });
      let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
      let timeout: ReturnType<typeof setTimeout> | undefined;
      try {
        lease = await this.api.acquire(
          song.id,
          this.start + this.receivedFrames / SAMPLE_RATE,
          signal,
          (ticket: Ticket) => {
            if (id === this.generation)
              this.update({
                status: this.shouldPause ? "paused" : "waiting",
                waitPosition: ticket.position,
                message: ticket.message,
              });
          },
          (created) => {
            if (id === this.generation) this.lease = created;
            else this.api.release(created);
          },
        );
        if (signal.aborted || id !== this.generation) return;
        this.lease = lease;
        const stream = lease.ticket.stream!;
        this.update({
          entry: lease.coordinator,
          server: stream.server_id,
          waitPosition: 0,
          message: recoveryStarted
            ? "Recuperando la conexión…"
            : "Recibiendo audio…",
        });
        timeout = setTimeout(cancel, 25_000);
        const response = await this.api.audio(
          stream.audio_url,
          requestAbort.signal,
        );
        clearTimeout(timeout);
        if (
          response.headers.get("X-Audio-Format") !== "s16le" ||
          Number(response.headers.get("X-Sample-Rate")) !== SAMPLE_RATE ||
          Number(response.headers.get("X-Channels")) !== 2
        ) {
          throw new ApiError(
            "El servidor devolvió un formato de audio incompatible.",
            415,
          );
        }
        const decoder = new PcmDecoder();
        reader = response.body!.getReader();
        while (!signal.aborted) {
          // Búfer acotado por tiempo, no por cantidad de canciones ni de clientes.
          while (this.state.bufferedUntil - this.state.position > 20)
            await delay(100, signal);
          timeout = setTimeout(cancel, 15_000);
          const result = await reader.read();
          clearTimeout(timeout);
          if (signal.aborted || id !== this.generation) return;
          if (result.done) break;
          const block = decoder.decode(result.value);
          if (block.frames) {
            this.receivedFrames += block.frames;
            this.engine.feed(id, block);
            this.update({
              bufferedUntil: this.start + this.receivedFrames / SAMPLE_RATE,
            });
            recoveryStarted = 0;
          }
        }
        if (
          !decoder.aligned ||
          !(await this.api.completed(
            stream.server_url,
            stream.stream_id,
            signal,
          ))
        ) {
          throw new Error(
            "La transferencia terminó antes de completar el audio.",
          );
        }
        if (id === this.generation && !signal.aborted) this.engine.finish(id);
        return;
      } catch (error) {
        if (signal.aborted || id !== this.generation) return;
        if (
          this.offline?.has(song.id) &&
          !(error instanceof ApiError && [400, 403, 415].includes(error.status))
        ) {
          this.play(song, this.state.position, false, this.shouldPause, true);
          return;
        }
        if (
          error instanceof ApiError &&
          [400, 403, 404, 415, 504].includes(error.status)
        )
          throw error;
        recoveryStarted ||= Date.now();
        if (Date.now() - recoveryStarted > 180_000)
          throw new Error("No se pudo recuperar el audio. Vuelve a intentar.");
        this.update({
          message:
            "Conexión interrumpida. Buscando otro servidor para continuar…",
        });
        await delay(1000, signal);
      } finally {
        clearTimeout(timeout);
        signal.removeEventListener("abort", cancel);
        requestAbort.abort();
        void reader?.cancel().catch(() => undefined);
        if (lease) this.api.release(lease);
        if (this.lease === lease) this.lease = null;
      }
    }
  }
  private fail(error: unknown): void {
    this.cancel();
    ++this.generation;
    this.engine.reset(0, false);
    this.update({
      status: "error",
      message: errorMessage(error),
      waitPosition: 0,
    });
  }
  private handleEngine(event: EngineEvent): void {
    if (event.id !== this.generation || !this.state.current) return;
    if (event.type === "suspended") {
      if (["playing", "buffering"].includes(this.state.status)) {
        this.shouldPause = true;
        this.engine.pause(this.generation, true);
        this.update({
          status: "paused",
          message:
            "El navegador pausó el audio. Pulsa reproducir para continuar.",
        });
      }
      return;
    }
    if (event.type === "ended") {
      if (
        this.state.queue.some(
          (item) =>
            navigator.onLine !== false || this.offline?.has(item.song.id),
        )
      )
        this.next();
      else
        this.update({
          status: "ended",
          position: this.state.current.duration,
          message: "Canción finalizada.",
        });
      return;
    }
    if (["idle", "ended", "error"].includes(this.state.status)) return;
    const position = this.start + event.played / SAMPLE_RATE;
    if (this.shouldPause) {
      this.update({ position, status: "paused" });
      return;
    }
    if (this.state.status === "waiting" && !event.frames && !event.played)
      return;
    if (this.state.status === "loading" && !event.frames && !event.played)
      return;
    this.update({
      position,
      status: event.buffering ? "buffering" : "playing",
      message: event.buffering
        ? "Preparando más audio…"
        : this.state.source === "local"
          ? "Reproduciendo una copia sin conexión."
          : "Disfruta tu música.",
    });
  }
  toggle(): void {
    const { current, status } = this.state;
    if (!current) return;
    if (status === "playing" || status === "buffering") {
      this.shouldPause = true;
      this.engine.pause(this.generation, true);
      this.update({ status: "paused", message: "Reproducción pausada." });
    } else if (status === "paused") {
      const id = this.generation;
      void this.engine
        .unlock()
        .then(() => {
          if (id !== this.generation) return;
          this.shouldPause = false;
          this.engine.pause(id, false);
          this.update({ status: "buffering", message: "Continuando…" });
        })
        .catch((error) => {
          if (id === this.generation) this.fail(error);
        });
    } else if (!["loading", "waiting"].includes(status))
      this.play(current, 0, false, false, this.state.source === "local");
  }
  seek(second: number): void {
    if (this.state.current)
      this.play(
        this.state.current,
        second,
        false,
        this.state.status === "paused",
        this.state.source === "local",
      );
  }
  stop(): void {
    this.cancel();
    ++this.generation;
    this.engine.reset(0, false);
    this.shouldPause = false;
    this.update({
      status: "idle",
      position: 0,
      bufferedUntil: 0,
      waitPosition: 0,
      message: "Reproducción detenida.",
    });
  }
  volume(value: number): void {
    const level = Math.max(0, Math.min(1, value));
    this.engine.volume(level);
    this.update({ volume: level });
  }
  add(songs: Song[]): void {
    if (!songs.length) return;
    this.update({
      queue: [
        ...this.state.queue,
        ...songs.map((song) => ({ key: String(++this.queueKey), song })),
      ],
      queueOpen: true,
    });
    if (!this.state.current) this.next();
  }
  remove(key: string): void {
    const queue = this.state.queue.filter((item) => item.key !== key);
    this.update({
      queue,
      queueOpen: queue.length ? this.state.queueOpen : false,
    });
  }
  clear(): void {
    this.update({ queue: [], queueOpen: false });
  }
  toggleQueue(): void {
    this.update({ queueOpen: !this.state.queueOpen });
  }
  playQueued(key: string): void {
    const item = this.state.queue.find((row) => row.key === key);
    if (item && navigator.onLine === false && !this.offline?.has(item.song.id))
      return;
    if (item) {
      this.remove(key);
      this.play(item.song);
    }
  }
  next(): void {
    const next = this.state.queue.find(
      (item) => navigator.onLine !== false || this.offline?.has(item.song.id),
    );
    if (next) this.playQueued(next.key);
  }
  previous(): void {
    if (this.state.current && this.state.position > 3)
      this.play(
        this.state.current,
        0,
        false,
        false,
        this.state.source === "local",
      );
    else if (this.history.length) {
      const song = this.history.at(-1)!;
      if (navigator.onLine === false && !this.offline?.has(song.id)) return;
      this.history.pop();
      if (this.state.current)
        this.update({
          queue: [
            { key: String(++this.queueKey), song: this.state.current },
            ...this.state.queue,
          ],
        });
      this.play(song, 0, false);
    } else if (this.state.current)
      this.play(
        this.state.current,
        0,
        false,
        false,
        this.state.source === "local",
      );
  }
  dispose(): void {
    this.cancel();
    ++this.generation;
    this.engine.dispose();
    this.listeners.clear();
  }
}
