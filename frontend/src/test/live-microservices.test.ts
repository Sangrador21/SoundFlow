// @vitest-environment node
import { expect, it } from "vitest";
import { ClusterApi } from "../services/cluster-api";
import { downloadRecent } from "../features/offline/recent-downloads";
import type { OfflineStore } from "../features/offline/offline-store";

const gateway = process.env.SOUNDFLOW_GATEWAY_URL;
it.skipIf(!gateway)("P08 real: diagnóstico y descarga íntegra MP3 por una reserva del gateway", async () => {
  const services = await fetch(gateway + "/api/services");
  expect(services.status).toBe(200);
  const api = new ClusterApi([gateway!]);
  const signal = new AbortController().signal;
  const catalog = await api.catalog(signal);
  expect(catalog.entrypoints).toEqual([gateway]);
  const song = catalog.songs.find((item) => item.servers.length === 1 && item.servers[0] === "S2")!;
  expect(song).toBeDefined();
  let saved: Blob | undefined;
  const store = {
    update() {},
    async save(_song: unknown, blob: Blob) { saved = blob; },
  } as unknown as OfflineStore;
  await downloadRecent(api, song, store, signal);
  expect(saved?.type).toBe("audio/mpeg");
  expect(saved!.size).toBeGreaterThan(1000);
}, 30_000);
