import { expect, it, vi } from "vitest";
import { ClusterApi } from "./cluster-api";
import { assigned, json, song } from "../test/fakes";

it("P08 aprende gateways de respaldo y no utiliza medios como coordinadores", async () => {
  const fetcher = vi.fn<typeof fetch>(async (url, init) => {
    if (String(url).endsWith("/api/catalog"))
      return json({ songs: [song], nodes: [{ base_url: "https://media.test" }],
        offline: [], entrypoints: ["https://backup-gateway.test"] });
    if (String(url).startsWith("https://gateway.test") && init?.method === "POST")
      return json({ error: "Temporalmente fuera de servicio" }, 503);
    return json(assigned(1));
  });
  const api = new ClusterApi(["https://gateway.test"], fetcher);
  const signal = new AbortController().signal;
  await api.catalog(signal);
  const lease = await api.acquire(song.id, 0, signal, () => {}, () => {});
  expect(lease.coordinator).toBe("https://backup-gateway.test");
  expect(fetcher.mock.calls.some(([url]) => String(url).startsWith("https://media.test"))).toBe(false);
});
