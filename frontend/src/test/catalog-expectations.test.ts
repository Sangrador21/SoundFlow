// @vitest-environment node
import { createHash } from "node:crypto";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";
import { expectedCatalog } from "./catalog-expectations";

it("asigna todos los audios originales y conserva canciones compartidas y exclusivas", () => {
  const root = fileURLToPath(new URL("../../../", import.meta.url));
  const expected = expectedCatalog(root);
  const originals = new Set(
    readdirSync(join(root, "music"))
      .filter(
        (name) =>
          name !== "demo_tono.wav" && /\.(mp3|wav|ogg|flac)$/i.test(name),
      )
      .map((name) =>
        createHash("sha256")
          .update(readFileSync(join(root, "music", name)))
          .digest("hex"),
      ),
  );
  expect(
    new Set(
      expected.songs.map((song) => song.id).filter((id) => originals.has(id)),
    ),
    "Asigna cada audio de music/ a S1.json o S2.json; demo_tono.wav es opcional.",
  ).toEqual(originals);
  expect(expected.songs.some((song) => song.servers.length > 1)).toBe(true);
  for (const node of ["S1", "S2"])
    expect(
      expected.songs.some(
        (song) => song.servers.length === 1 && song.servers[0] === node,
      ),
    ).toBe(true);
});

it("adapta el catálogo esperado al agregar audio y deduplica por contenido", () => {
  const root = mkdtempSync(join(tmpdir(), "soundflow-catalog-"));
  try {
    mkdirSync(join(root, "music"));
    mkdirSync(join(root, "deploy", "catalogs"), { recursive: true });
    writeFileSync(join(root, "music", "original.mp3"), "mismo audio");
    writeFileSync(join(root, "music", "copia.mp3"), "mismo audio");
    const s1 = join(root, "deploy", "catalogs", "S1.json");
    const s2 = join(root, "deploy", "catalogs", "S2.json");
    writeFileSync(s1, JSON.stringify(["original.mp3"]));
    writeFileSync(s2, JSON.stringify(["copia.mp3"]));
    const initial = expectedCatalog(root);
    expect(initial.songs).toHaveLength(1);
    expect(initial.songs[0]?.servers).toEqual(["S1", "S2"]);
    writeFileSync(join(root, "music", "nueva.mp3"), "audio nuevo");
    writeFileSync(s2, JSON.stringify(["copia.mp3", "nueva.mp3"]));
    const updated = expectedCatalog(root);
    expect(updated.songs).toHaveLength(2);
    expect(updated.nodeCounts).toEqual({ S1: 1, S2: 2 });
    expect(updated.songs.some((song) => song.servers.length === 1)).toBe(true);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

it("rechaza un manifiesto que intenta salir de la biblioteca", () => {
  const root = mkdtempSync(join(tmpdir(), "soundflow-catalog-"));
  try {
    mkdirSync(join(root, "deploy", "catalogs"), { recursive: true });
    writeFileSync(
      join(root, "deploy", "catalogs", "S1.json"),
      JSON.stringify(["../fuera.mp3"]),
    );
    expect(() => expectedCatalog(root)).toThrow("Nombre de audio inválido");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
