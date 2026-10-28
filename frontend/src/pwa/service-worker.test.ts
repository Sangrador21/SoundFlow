// @vitest-environment node
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { describe, expect, it, vi } from "vitest";

const origin = "https://example.test";
const template = readFileSync(
  new URL("../../pwa/service-worker.js", import.meta.url),
  "utf8",
);
function worker() {
  const handlers = new Map<string, (event: any) => void>();
  const cache = {
    addAll: vi.fn().mockResolvedValue(undefined),
    match: vi.fn().mockResolvedValue(undefined),
  };
  const storage = {
    open: vi.fn().mockResolvedValue(cache),
    keys: vi
      .fn()
      .mockResolvedValue([
        "unrelated",
        "soundflow-shell:/SoundFlow/:old",
        "soundflow-shell:/SoundFlow/:new",
      ]),
    delete: vi.fn().mockResolvedValue(true),
  };
  const self = {
    location: { origin },
    addEventListener: (name: string, callback: (event: any) => void) =>
      handlers.set(name, callback),
    clients: {
      claim: vi.fn().mockResolvedValue(undefined),
      matchAll: vi.fn().mockResolvedValue([{ url: origin + "/SoundFlow/" }]),
    },
    skipWaiting: vi.fn().mockResolvedValue(undefined),
  };
  const fetcher = vi.fn().mockResolvedValue(new Response("network"));
  vm.runInNewContext(
    template.replace(
      "/* SOUNDFLOW_CONFIG */",
      JSON.stringify({
        base: "/SoundFlow/",
        version: "new",
        files: [
          "/SoundFlow/index.html",
          "/SoundFlow/assets/app.js",
          "/SoundFlow/worklets/pcm-player.js",
        ],
      }),
    ),
    { self, caches: storage, fetch: fetcher, URL, Request, Set, Promise },
  );
  function request(path: string, init: RequestInit = {}, mode = "cors") {
    const respondWith = vi.fn();
    handlers.get("fetch")!({
      request: {
        url: new URL(path, origin).href,
        method: init.method || "GET",
        mode,
        headers: new Headers(init.headers),
        destination: "",
      },
      respondWith,
    });
    return respondWith;
  }
  async function event(name: string, extra = {}) {
    let result: Promise<unknown> = Promise.resolve();
    handlers.get(name)!({
      ...extra,
      waitUntil: (value: Promise<unknown>) => {
        result = value;
      },
    });
    return result;
  }
  return { request, event, self, cache, storage, fetcher };
}

describe("Service worker: política de caché y ciclo de vida", () => {
  it("precarga el conjunto exacto y no activa actualizaciones automáticamente", async () => {
    const w = worker();
    await w.event("install");
    expect(w.cache.addAll.mock.calls[0]![0].map((r: Request) => r.url)).toEqual(
      [
        origin + "/SoundFlow/index.html",
        origin + "/SoundFlow/assets/app.js",
        origin + "/SoundFlow/worklets/pcm-player.js",
      ],
    );
    expect(w.self.skipWaiting).not.toHaveBeenCalled();
  });
  it("elimina la caché incompleta si falla la instalación", async () => {
    const w = worker();
    w.cache.addAll.mockRejectedValueOnce(new Error("offline"));
    await expect(w.event("install")).rejects.toThrow("offline");
    expect(w.storage.delete).toHaveBeenCalledWith(
      "soundflow-shell:/SoundFlow/:new",
    );
  });
  it("no intercepta API, PCM, operaciones, Range, otros orígenes ni otros repositorios", () => {
    const w = worker();
    for (const [path, init] of [
      ["/api/catalog", {}],
      ["/SoundFlow/api/requests", {}],
      ["https://soundflow-s1.onrender.com/api/catalog", {}],
      ["https://soundflow-s2.onrender.com/api/streams/123/audio", {}],
      ["/SoundFlow/assets/app.js", { method: "POST" }],
      ["/SoundFlow/assets/app.js", { headers: { Range: "bytes=0-9" } }],
      ["/Other/index.html", {}],
      ["/SoundFlow/unknown.wav", {}],
    ] as [string, RequestInit][])
      expect(w.request(path, init)).not.toHaveBeenCalled();
  });
  it("sirve la interfaz y los recursos conocidos sin red", async () => {
    const w = worker();
    w.cache.match.mockResolvedValue(new Response("cached"));
    const answer = w.request("/SoundFlow/?source=installed", {}, "navigate");
    expect(await (await answer.mock.calls[0]![0]).text()).toBe("cached");
    expect(w.cache.match).toHaveBeenCalledWith(
      origin + "/SoundFlow/index.html",
    );
    expect(w.fetcher).not.toHaveBeenCalled();
  });
  it("limpia solo sus cachés antiguas y conserva las de otras aplicaciones", async () => {
    const w = worker();
    await w.event("activate");
    expect(w.storage.delete.mock.calls).toEqual([
      ["soundflow-shell:/SoundFlow/:old"],
    ]);
    expect(w.self.clients.claim).toHaveBeenCalled();
  });
  it("conserva recursos anteriores si hay más ventanas de SoundFlow abiertas", async () => {
    const w = worker();
    w.self.clients.matchAll.mockResolvedValue([
      { url: origin + "/SoundFlow/" },
      { url: origin + "/SoundFlow/?second" },
    ]);
    await w.event("activate");
    expect(w.storage.delete).not.toHaveBeenCalled();
  });
  it("solo acepta la actualización desde una ventana de la propia aplicación", async () => {
    const w = worker();
    await w.event("message", {
      data: { type: "SOUNDFLOW_ACTIVATE_UPDATE" },
      source: { url: origin + "/Other/" },
    });
    expect(w.self.skipWaiting).not.toHaveBeenCalled();
    await w.event("message", {
      data: { type: "SOUNDFLOW_ACTIVATE_UPDATE" },
      source: { url: origin + "/SoundFlow/" },
    });
    expect(w.self.skipWaiting).toHaveBeenCalledOnce();
  });
});
