import type { Song } from "../../types/api";

export const MAX_OFFLINE_TRACKS = 3;
export const MAX_OFFLINE_BYTES = 24 * 1024 * 1024;
export interface OfflineTrack {
  id: string;
  song: Song;
  blob: Blob;
  sha256: string;
  lastUsed: number;
}
export type OfflineSummary = Omit<OfflineTrack, "blob"> & { bytes: number };
export interface OfflineState {
  tracks: OfflineSummary[];
  activeId: string | null;
  progress: number;
  message: string;
  enabled: boolean;
}
export interface OfflineSource {
  has(id: string): boolean;
  get(id: string): Promise<OfflineTrack | null>;
  touch(id: string): Promise<void>;
}
const NAME = "soundflow-recent:" + import.meta.env.BASE_URL;

export class OfflineStore implements OfflineSource {
  private db: Promise<IDBDatabase> | null = null;
  private channel: BroadcastChannel | null = null;
  private listeners = new Set<() => void>();
  private state: OfflineState = {
    tracks: [],
    activeId: null,
    progress: 0,
    message: "",
    enabled: true,
  };
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  update(changes: Partial<OfflineState>) {
    this.state = { ...this.state, ...changes };
    this.listeners.forEach((listener) => listener());
  }
  has = (id: string) => this.state.tracks.some((track) => track.id === id);
  private open(): Promise<IDBDatabase> {
    this.db ??= new Promise((resolve, reject) => {
      if (!globalThis.indexedDB) {
        reject(
          new Error("Este navegador no permite guardar canciones localmente."),
        );
        return;
      }
      const request = indexedDB.open(NAME, 1);
      request.onupgradeneeded = () =>
        request.result.createObjectStore("tracks", { keyPath: "id" });
      request.onerror = () => reject(request.error);
      request.onblocked = () =>
        reject(
          new Error(
            "Cierra otras ventanas de SoundFlow para preparar el almacenamiento.",
          ),
        );
      request.onsuccess = () => {
        request.result.onversionchange = () => {
          request.result.close();
          this.db = null;
        };
        resolve(request.result);
      };
    });
    return this.db;
  }
  async start(): Promise<void> {
    try {
      try {
        this.update({
          enabled: localStorage.getItem(NAME + ":enabled") !== "false",
        });
      } catch {}
      await this.refresh();
      if (globalThis.BroadcastChannel && !this.channel) {
        this.channel = new BroadcastChannel(NAME);
        this.channel.onmessage = () => {
          void this.refresh().catch(() => {});
        };
      }
    } catch (error) {
      this.update({
        message:
          error instanceof Error
            ? error.message
            : "No se pudo abrir el almacenamiento local.",
      });
    }
  }
  dispose() {
    this.channel?.close();
    this.channel = null;
  }
  async refresh(): Promise<void> {
    const db = await this.open();
    const tracks = await new Promise<OfflineTrack[]>((resolve, reject) => {
      const tx = db.transaction("tracks", "readonly");
      const request = tx.objectStore("tracks").getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    this.update({
      tracks: tracks
        .sort((a, b) => b.lastUsed - a.lastUsed)
        .map(({ blob, ...track }) => ({ ...track, bytes: blob.size })),
    });
  }
  async get(id: string): Promise<OfflineTrack | null> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const request = db
        .transaction("tracks", "readonly")
        .objectStore("tracks")
        .get(id);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error);
    });
  }
  private async change(run: (store: IDBObjectStore) => void): Promise<void> {
    const db = await this.open();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("tracks", "readwrite");
      tx.oncomplete = () => resolve();
      tx.onabort = () =>
        reject(
          tx.error ||
            new Error(
              "No se pudo guardar la canción. Revisa el espacio disponible.",
            ),
        );
      tx.onerror = () => {};
      try {
        run(tx.objectStore("tracks"));
      } catch (error) {
        tx.abort();
        reject(error);
      }
    });
    await this.refresh();
    this.channel?.postMessage("changed");
  }
  async save(
    song: Song,
    blob: Blob,
    sha256: string,
    signal?: AbortSignal,
  ): Promise<void> {
    if (!blob.size || blob.size > MAX_OFFLINE_BYTES)
      throw new Error("La copia supera 24 MiB o está vacía.");
    if (signal?.aborted) throw new DOMException("Cancelado", "AbortError");
    await this.change((store) => {
      const all = store.getAll();
      all.onsuccess = () => {
        if (signal?.aborted) {
          store.transaction.abort();
          return;
        }
        const tracks = (all.result as OfflineTrack[])
          .filter((track) => track.id !== song.id)
          .sort((a, b) => b.lastUsed - a.lastUsed);
        const { id, title, artist, filename, duration, servers } = song;
        store.put({
          id,
          song: {
            id,
            title,
            artist,
            filename,
            duration,
            servers,
            available: false,
          },
          blob,
          sha256,
          lastUsed: Date.now(),
        });
        tracks
          .slice(MAX_OFFLINE_TRACKS - 1)
          .forEach((track) => store.delete(track.id));
      };
    });
  }
  async touch(id: string): Promise<void> {
    await this.change((store) => {
      const request = store.get(id);
      request.onsuccess = () => {
        if (request.result)
          store.put({ ...request.result, lastUsed: Date.now() });
      };
    });
  }
  remove(id: string) {
    return this.change((store) => {
      store.delete(id);
    });
  }
  clear() {
    return this.change((store) => {
      store.clear();
    });
  }
  setEnabled(enabled: boolean) {
    try {
      localStorage.setItem(NAME + ":enabled", String(enabled));
    } catch {}
    this.update({ enabled });
  }
}
