import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import type { Plugin, ResolvedConfig } from "vite";

// No service worker in the development server: test the compiled application.
export function soundFlowPwa(): Plugin {
  let config: ResolvedConfig;
  return {
    name: "soundflow-pwa",
    apply: "build",
    enforce: "post",
    configResolved(value) {
      config = value;
    },
    generateBundle(_options, bundle) {
      const base = config.base;
      if (!base.startsWith("/") || !base.endsWith("/") || base.includes(".."))
        throw new Error("VITE_BASE_PATH debe comenzar y terminar con /.");
      const template = readFileSync(
        resolve(config.root, "pwa/service-worker.js"),
        "utf8",
      );
      const files = new Map<string, string | Uint8Array>();
      for (const [name, item] of Object.entries(bundle)) {
        if (!name.endsWith(".map"))
          files.set(name, item.type === "chunk" ? item.code : item.source);
      }
      function publicFiles(directory: string, prefix = "") {
        for (const entry of readdirSync(directory, { withFileTypes: true })) {
          const name = prefix + entry.name;
          if (entry.isDirectory())
            publicFiles(resolve(directory, entry.name), name + "/");
          else if (entry.isFile())
            files.set(name, readFileSync(resolve(directory, entry.name)));
        }
      }
      publicFiles(config.publicDir);
      const manifest = JSON.stringify(
        {
          id: base,
          name: "SoundFlow",
          short_name: "SoundFlow",
          lang: "es",
          description:
            "Tu música, en conexión. Biblioteca y reproducción distribuida.",
          start_url: base,
          scope: base,
          display: "standalone",
          background_color: "#f6f3fb",
          theme_color: "#1e0a4e",
          icons: [
            {
              src: base + "icons/icon-192.png",
              sizes: "192x192",
              type: "image/png",
              purpose: "any",
            },
            {
              src: base + "icons/icon-512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "any",
            },
            {
              src: base + "icons/maskable-512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
        },
        null,
        2,
      );
      files.set("manifest.webmanifest", manifest);
      const hash = createHash("sha256").update(template).update(base);
      for (const [name, contents] of [...files].sort(([a], [b]) =>
        a.localeCompare(b),
      ))
        hash.update(name).update(contents);
      const version = hash.digest("hex").slice(0, 16);
      const settings = {
        base,
        version,
        files: [...files.keys()].sort().map((name) => base + name),
      };
      this.emitFile({
        type: "asset",
        fileName: "manifest.webmanifest",
        source: manifest,
      });
      this.emitFile({
        type: "asset",
        fileName: "sw.js",
        source: template.replace(
          "/* SOUNDFLOW_CONFIG */",
          JSON.stringify(settings),
        ),
      });
    },
  };
}
