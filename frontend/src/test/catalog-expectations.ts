import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

interface ExpectedSong {
  id: string;
  servers: string[];
}

// Solo para pruebas en Node; no se importa desde la aplicación del navegador.
export function expectedCatalog(
  root = fileURLToPath(new URL("../../../", import.meta.url)),
  nodes = ["S1", "S2"],
) {
  const songs = new Map<string, ExpectedSong>();
  const nodeCounts: Record<string, number> = {};
  for (const node of nodes) {
    const manifest: unknown = JSON.parse(
      readFileSync(join(root, "deploy", "catalogs", `${node}.json`), "utf8"),
    );
    if (!Array.isArray(manifest) || !manifest.length)
      throw new Error(`El manifiesto de ${node} debe contener canciones.`);
    const ids = new Set<string>();
    for (const name of manifest) {
      if (
        typeof name !== "string" ||
        !name ||
        /[/\\]/.test(name) ||
        !/\.(mp3|wav|ogg|flac)$/i.test(name)
      )
        throw new Error(`Nombre de audio inválido en ${node}.`);
      const id = createHash("sha256")
        .update(readFileSync(join(root, "music", name)))
        .digest("hex");
      ids.add(id);
      const song = songs.get(id) ?? { id, servers: [] };
      if (!song.servers.includes(node)) song.servers.push(node);
      songs.set(id, song);
    }
    nodeCounts[node] = ids.size;
  }
  return {
    songs: [...songs.values()]
      .map((song) => ({ id: song.id, servers: song.servers.sort() }))
      .sort((left, right) => left.id.localeCompare(right.id)),
    nodeCounts,
  };
}
