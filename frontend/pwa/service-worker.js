/* The build inserts the exact asset list and a content-based version. */
const CONFIG = /* SOUNDFLOW_CONFIG */;
const PREFIX = "soundflow-shell:" + CONFIG.base + ":";
const CACHE = PREFIX + CONFIG.version;
const FILES = new Set(CONFIG.files.map(path => new URL(path, self.location.origin).href));
const INDEX = new URL(CONFIG.base + "index.html", self.location.origin).href;

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    try {
      const cache = await caches.open(CACHE);
      // Fail installation atomically if any asset cannot be downloaded.
      await cache.addAll([...FILES].map(url => new Request(url, { cache: "reload" })));
    } catch (error) {
      await caches.delete(CACHE);
      throw error;
    }
    // Updates wait for an explicit user action; never interrupt playback.
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const ownWindows = windows.filter(client => new URL(client.url).pathname.startsWith(CONFIG.base));
    // Keep old assets while other open SoundFlow windows may still need them.
    if (ownWindows.length <= 1) {
      await Promise.all((await caches.keys()).filter(key => key.startsWith(PREFIX) && key !== CACHE)
        .map(key => caches.delete(key)));
    }
    await self.clients.claim();
  })());
});

self.addEventListener("message", event => {
  if (event.data?.type !== "SOUNDFLOW_ACTIVATE_UPDATE") return;
  // Only a window belonging to this application can authorize an update.
  if (!event.source?.url) return;
  const source = new URL(event.source.url);
  if (source.origin === self.location.origin && source.pathname.startsWith(CONFIG.base))
    event.waitUntil(self.skipWaiting());
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  // API tickets, metrics, PCM, Range requests and other origins always use the network.
  if (request.method !== "GET" || url.origin !== self.location.origin ||
      !url.pathname.startsWith(CONFIG.base) || /\/api(?:\/|$)/.test(url.pathname) ||
      request.headers.has("range") || ["audio", "video"].includes(request.destination)) return;
  const navigation = request.mode === "navigate";
  url.search = "";
  url.hash = "";
  if (!navigation && !FILES.has(url.href) && !url.pathname.startsWith(CONFIG.base + "assets/")) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const key = navigation ? INDEX : url.href;
    const stored = await cache.match(key);
    if (stored) return stored;
    // An older open window can still request its content-hashed chunks.
    if (!navigation) {
      for (const name of await caches.keys()) {
        if (name.startsWith(PREFIX) && name !== CACHE) {
          const previous = await (await caches.open(name)).match(key);
          if (previous) return previous;
        }
      }
    }
    // Do not dynamically cache unknown responses or streaming resources.
    return fetch(request);
  })());
});
