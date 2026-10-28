import type { Catalog, Song } from "../../types/api";

const KEY = "soundflow.catalog.v1";
function scope(servers: string[]) {
  return [...servers].sort().join(",");
}
function isSong(value: unknown): value is Song {
  if (!value || typeof value !== "object") return false;
  const song = value as Partial<Song>;
  return (
    typeof song.id === "string" &&
    /^[a-f0-9]{64}$/.test(song.id) &&
    typeof song.title === "string" &&
    typeof song.artist === "string" &&
    typeof song.filename === "string" &&
    typeof song.duration === "number" &&
    Number.isFinite(song.duration) &&
    song.duration >= 0 &&
    Array.isArray(song.servers) &&
    song.servers.every((server) => typeof server === "string")
  );
}
export function saveCatalog(servers: string[], catalog: Catalog): void {
  try {
    // Metadata only: no audio, tickets, metrics, credentials or sessions.
    const songs = catalog.songs.map(
      ({ id, title, artist, filename, duration, servers }) => ({
        id,
        title,
        artist,
        filename,
        duration,
        servers,
      }),
    );
    localStorage.setItem(
      KEY,
      JSON.stringify({ servers: scope(servers), songs, savedAt: Date.now() }),
    );
  } catch {
    /* Private mode or quota restrictions must not prevent streaming. */
  }
}
export function loadCatalog(servers: string[]): Catalog | null {
  try {
    const data = JSON.parse(localStorage.getItem(KEY) || "null");
    if (
      !data ||
      data.servers !== scope(servers) ||
      !Array.isArray(data.songs) ||
      !data.songs.every(isSong)
    )
      return null;
    return {
      songs: data.songs.map((song: Song) => ({ ...song, available: false })),
      nodes: [],
      offline: [],
    };
  } catch {
    return null;
  }
}
