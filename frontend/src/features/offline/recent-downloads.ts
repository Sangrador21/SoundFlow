import type { Lease, Song } from "../../types/api";
import { ClusterApi } from "../../services/cluster-api";
import { OfflineStore, MAX_OFFLINE_BYTES } from "./offline-store";
import type { PlaybackController } from "../player/playback-controller";
import { delay } from "../../utils/format";

export async function downloadRecent(
  api: ClusterApi,
  song: Song,
  store: OfflineStore,
  signal: AbortSignal,
): Promise<void> {
  let lease: Lease | null = null;
  try {
    lease = await api.acquire(
      song.id,
      0,
      signal,
      () =>
        store.update({
          message: "Esperando un servidor para guardar la copia…",
        }),
      (created) => {
        lease = created;
      },
    );
    const stream = lease.ticket.stream!;
    const response = await api.audio(
      `${stream.server_url}/api/streams/${stream.stream_id}/download`,
      signal,
    );
    const size = Number(response.headers.get("X-Download-Bytes"));
    const digest = response.headers.get("X-Download-SHA256") || "";
    if (
      response.status !== 200 ||
      !Number.isSafeInteger(size) ||
      size <= 0 ||
      size > MAX_OFFLINE_BYTES ||
      !/^[a-f0-9]{64}$/.test(digest) ||
      !response.headers.get("Content-Type")?.startsWith("audio/mpeg")
    )
      throw new Error(
        "El servidor no ofrece una copia MP3 completa compatible. Actualiza el backend.",
      );
    const reader = response.body!.getReader();
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let received = 0;
    try {
      while (true) {
        const result = await reader.read();
        if (result.done) break;
        signal.throwIfAborted();
        received += result.value.byteLength;
        if (received > size || received > MAX_OFFLINE_BYTES)
          throw new Error("La descarga excede su tamaño anunciado.");
        chunks.push(new Uint8Array(result.value));
        store.update({
          progress: Math.round((received * 100) / size),
          message: "Guardando una canción reciente…",
        });
      }
    } finally {
      await reader.cancel().catch(() => {});
    }
    signal.throwIfAborted();
    let complete = false;
    for (let attempt = 0; received === size && attempt < 20; attempt++) {
      if (await api.completed(stream.server_url, stream.stream_id, signal)) {
        complete = true;
        break;
      }
      await delay(100, signal);
    }
    if (received !== size || !complete)
      throw new Error(
        "La descarga se interrumpió; no se guardó una copia incompleta.",
      );
    const blob = new Blob(chunks, { type: "audio/mpeg" });
    const actual = [
      ...new Uint8Array(
        await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()),
      ),
    ]
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
    if (actual !== digest)
      throw new Error("La copia no superó la verificación de integridad.");
    await store.save(song, blob, actual, signal);
  } finally {
    if (lease) api.release(lease);
  }
}

export class RecentDownloads {
  private timer: ReturnType<typeof setTimeout> | undefined;
  private abort: AbortController | null = null;
  private last = "";
  private loading = false;
  private generation = 0;
  setEnabled(enabled: boolean) {
    this.store.setEnabled(enabled);
    if (enabled) this.last = "";
    this.observe();
  }
  constructor(
    private api: ClusterApi,
    private readonly player: PlaybackController,
    private readonly store: OfflineStore,
  ) {}
  setApi(api: ClusterApi) {
    this.cancel();
    this.last = "";
    this.api = api;
  }
  cancel() {
    clearTimeout(this.timer);
    this.abort?.abort();
    this.abort = null;
    ++this.generation;
    this.store.update({ activeId: null, progress: 0 });
  }
  observe = () => {
    const state = this.player.getSnapshot();
    if (
      !this.store.getSnapshot().enabled ||
      navigator.onLine === false ||
      state.status === "idle"
    ) {
      this.cancel();
      return;
    }
    if (state.status === "loading") {
      if (!this.loading) {
        this.cancel();
        this.last = "";
      }
      this.loading = true;
      return;
    }
    this.loading = false;
    const song = state.current;
    if (
      !song ||
      state.source !== "server" ||
      state.status !== "playing" ||
      song.id === this.last
    )
      return;
    this.cancel();
    this.last = song.id;
    if (this.store.has(song.id)) {
      void this.store.touch(song.id).catch(() => {});
      return;
    }
    const generation = this.generation;
    this.timer = setTimeout(() => {
      const controller = new AbortController();
      this.abort = controller;
      this.store.update({
        activeId: song.id,
        progress: 0,
        message: "Preparando una copia reciente…",
      });
      const timeout = setTimeout(() => controller.abort(), 180_000);
      void downloadRecent(this.api, song, this.store, controller.signal)
        .then(() => {
          if (generation === this.generation)
            this.store.update({
              message: "Canción guardada para escuchar sin conexión.",
            });
        })
        .catch((error) => {
          if (generation === this.generation)
            this.store.update({
              message: controller.signal.aborted
                ? "Copia interrumpida. Puedes volver a reproducir la canción para reintentar."
                : error instanceof Error
                  ? error.message
                  : "No se pudo guardar la canción.",
            });
        })
        .finally(() => {
          clearTimeout(timeout);
          if (generation === this.generation) {
            this.abort = null;
            this.store.update({ activeId: null, progress: 0 });
          }
        });
    }, 1500);
  };
  connect(): () => void {
    const unsubscribe = this.player.subscribe(this.observe);
    const changed = () => {
      if (navigator.onLine) this.last = "";
      this.observe();
    };
    window.addEventListener("online", changed);
    window.addEventListener("offline", changed);
    this.observe();
    return () => {
      unsubscribe();
      window.removeEventListener("online", changed);
      window.removeEventListener("offline", changed);
      this.cancel();
    };
  }
}
