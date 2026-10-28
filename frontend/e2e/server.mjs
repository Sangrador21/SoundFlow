// Local test fixture only; never shipped in the production application.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve, extname } from "node:path";
import { createHash } from "node:crypto";

const root = resolve("dist");
let revision = 0;
let requests = 0;
let downloadMode = "full";
const song = {
  id: "a".repeat(64),
  title: "Canción de prueba",
  artist: "SoundFlow",
  filename: "test.wav",
  duration: 8,
  servers: ["S2"],
  available: true,
};
const songs = [
  song,
  ...["b", "c", "d"].map((id, index) => ({
    ...song,
    id: id.repeat(64),
    title: "Reciente " + (index + 2),
  })),
];
const types = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".webmanifest": "application/manifest+json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};
async function serve(req, res) {
  const path = new URL(req.url, "http://localhost").pathname;
  res.setHeader("Access-Control-Allow-Origin", "http://127.0.0.1:4173");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
  res.setHeader(
    "Access-Control-Expose-Headers",
    "X-Audio-Format, X-Sample-Rate, X-Channels, X-Download-Bytes, X-Download-SHA256",
  );
  res.setHeader("Cache-Control", "no-store");
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }
  if (path === "/__test__/revision") {
    revision++;
    res.end(String(revision));
    return;
  }
  if (path === "/__test__/download-mode") {
    downloadMode =
      new URL(req.url, "http://localhost").searchParams.get("mode") || "full";
    res.end("ok");
    return;
  }
  if (path === "/api/streams/test/download") {
    const bytes = await readFile(resolve("e2e/fixtures/tone.mp3"));
    const data = downloadMode === "partial" ? bytes.subarray(0, 128) : bytes;
    res.writeHead(200, {
      "Content-Type": "audio/mpeg",
      "Content-Length": String(data.length),
      "X-Download-Bytes": String(bytes.length),
      "X-Download-SHA256": createHash("sha256").update(bytes).digest("hex"),
    });
    res.end(data);
    return;
  }
  if (path === "/api/streams/test/audio") {
    res.writeHead(200, {
      "Content-Type": "application/octet-stream",
      "X-Audio-Format": "s16le",
      "X-Sample-Rate": "44100",
      "X-Channels": "2",
    });
    const pcm = Buffer.alloc(44100 * 4 * 8);
    for (let i = 0; i < pcm.length / 4; i++) {
      const sample = Math.round(
        Math.sin((i * 2 * Math.PI * 440) / 44100) * 2000,
      );
      pcm.writeInt16LE(sample, i * 4);
      pcm.writeInt16LE(sample, i * 4 + 2);
    }
    res.end(pcm);
    return;
  }
  if (path.startsWith("/api/") || path.startsWith("/SoundFlow/api/")) {
    res.setHeader("Content-Type", "application/json");
    if (path.endsWith("catalog"))
      res.end(JSON.stringify({ songs, nodes: [], offline: [] }));
    else if (path.endsWith("requests") && req.method === "POST") {
      requests++;
      res.statusCode = 201;
      res.end(
        JSON.stringify({
          request_id: "ticket",
          state: "ready",
          position: 0,
          wait_timeout: 120,
          stream: {
            stream_id: "test",
            server_id: "S2",
            server_url: "http://127.0.0.1:4174",
            audio_url: "http://127.0.0.1:4174/api/streams/test/audio",
            start: 0,
            duration: 8,
          },
        }),
      );
    } else if (req.method === "DELETE") {
      res.statusCode = 204;
      res.end();
    } else res.end(JSON.stringify({ state: "completed", requests }));
    return;
  }
  if (!path.startsWith("/SoundFlow/")) {
    res.writeHead(404);
    res.end();
    return;
  }
  const local = path.slice("/SoundFlow/".length) || "index.html";
  const file = resolve(root, local);
  if (!file.startsWith(root + "/")) {
    res.writeHead(403);
    res.end();
    return;
  }
  try {
    let data = await readFile(file);
    if (local === "sw.js" && revision)
      data = Buffer.from(
        data
          .toString()
          .replace(
            /"version":"([^"]+)"/,
            (_, version) => `"version":"${version}-${revision}"`,
          ),
      );
    res.setHeader(
      "Content-Type",
      types[extname(file)] || "application/octet-stream",
    );
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end();
  }
}
const servers = [4173, 4174].map((port) =>
  createServer((req, res) => {
    void serve(req, res);
  }).listen(port, "127.0.0.1"),
);
process.on("SIGTERM", () => servers.forEach((server) => server.close()));
