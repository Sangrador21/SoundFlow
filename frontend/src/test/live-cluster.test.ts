// @vitest-environment node
import { expect, it, vi } from "vitest";
import { ClusterApi } from "../services/cluster-api";
import { PlaybackController } from "../features/player/playback-controller";
import type { StereoBlock } from "../features/player/audio/pcm-decoder";
import { FakeEngine } from "./fakes";
import { expectedCatalog } from "./catalog-expectations";
import { interruptAfterBytes } from "./interrupted-response";

const servers = (process.env.SOUNDFLOW_LIVE_URLS || "")
  .split(",")
  .filter(Boolean);
it.skipIf(!servers.length)(
  "contrato real: catálogo distribuido, fallback y audio de S2 entrando por S1",
  async () => {
    const catalogApi = new ClusterApi(["http://127.0.0.1:1", servers[1]!]);
    const catalog = await catalogApi.catalog(new AbortController().signal);
    expect(catalog.nodes.map((node) => node.server_id).sort()).toEqual([
      "S1",
      "S2",
    ]);
    const expected = expectedCatalog();
    expect(
      catalog.songs
        .map((song) => ({ id: song.id, servers: [...song.servers].sort() }))
        .sort((left, right) => left.id.localeCompare(right.id)),
    ).toEqual(expected.songs);
    for (const node of catalog.nodes)
      expect(node.song_count).toBe(expected.nodeCounts[node.server_id]);
    expect(catalog.offline).toEqual([]);
    const song = catalog.songs.find(
      (song) => song.servers.length === 1 && song.servers[0] === "S2",
    )!;
    expect(song).toBeDefined();
    class ConsumingEngine extends FakeEngine {
      frames = 0;
      override feed(id: number, block: StereoBlock) {
        super.feed(id, block);
        this.frames += block.frames;
        this.onEvent({
          type: "progress",
          id,
          played: this.frames,
          frames: 0,
          buffering: false,
        });
      }
    }
    const engine = new ConsumingEngine();
    const player = new PlaybackController(
      new ClusterApi(["http://127.0.0.1:1", servers[0]!]),
      engine,
    );
    try {
      player.play(song, Math.max(0, song.duration - 1.5));
      await vi.waitFor(() => expect(engine.ends).toHaveLength(1), {
        timeout: 20_000,
      });
      expect(player.getSnapshot().server).toBe("S2");
      expect(player.getSnapshot().entry).toBe(servers[0]);
      expect(engine.frames).toBeGreaterThan(22_050);
      expect(engine.frames).toBeLessThan(100_000);
    } finally {
      player.dispose();
    }
  },
  25_000,
);

it.skipIf(!servers.length)(
  "recupera una interrupción real de MP3 y conserva las muestras recibidas",
  async () => {
    const { PcmDecoder } = await import("../features/player/audio/pcm-decoder");
    const catalogApi = new ClusterApi([servers[0]!]);
    const signal = new AbortController().signal;
    const catalog = await catalogApi.catalog(signal);
    const song = catalog.songs.find(
      (item) => item.servers.length === 1 && item.servers[0] === "S2",
    )!;
    const start = Math.max(0, song.duration - 1.5);
    const baseline = await catalogApi.acquire(
      song.id,
      start,
      signal,
      () => undefined,
      () => undefined,
    );
    const referenceResponse = await catalogApi.audio(
      baseline.ticket.stream!.audio_url,
      signal,
    );
    const reference = new PcmDecoder().decode(
      new Uint8Array(await referenceResponse.arrayBuffer()),
    );
    catalogApi.release(baseline);
    let interrupted = false;
    // 2048 muestras estéreo completas y tres bytes que deben volver a pedirse.
    const cutBytes = 8195;
    const starts: number[] = [];
    const flakyFetch: typeof fetch = async (url, init) => {
      if (init?.method === "POST")
        starts.push(JSON.parse(init.body as string).start);
      const response = await fetch(url, init);
      if (!String(url).endsWith("/audio") || interrupted) return response;
      interrupted = true;
      return interruptAfterBytes(response, cutBytes);
    };
    class ConsumingEngine extends FakeEngine {
      frames = 0;
      override feed(id: number, block: StereoBlock) {
        super.feed(id, block);
        this.frames += block.frames;
        this.onEvent({
          type: "progress",
          id,
          played: this.frames,
          frames: 0,
          buffering: false,
        });
      }
    }
    const engine = new ConsumingEngine();
    const player = new PlaybackController(
      new ClusterApi([servers[0]!], flakyFetch),
      engine,
    );
    try {
      player.play(song, start);
      await vi.waitFor(() => expect(engine.ends).toHaveLength(1), {
        timeout: 20_000,
      });
      expect(interrupted).toBe(true);
      // Un fallo de transporte antes de recibir PCM puede repetir la misma
      // reserva. Solo debe avanzar una vez: después de las 2048 muestras.
      const positions = starts.filter(
        (value, index) => index === 0 || value !== starts[index - 1],
      );
      const initialStart = Math.round(start * 44_100) / 44_100;
      expect(positions).toEqual([
        initialStart,
        initialStart + Math.floor(cutBytes / 4) / 44_100,
      ]);
      const left = new Float32Array(
        engine.blocks.flatMap((block) => Array.from(block.left)),
      );
      const right = new Float32Array(
        engine.blocks.flatMap((block) => Array.from(block.right)),
      );
      expect(
        Buffer.from(left.buffer).equals(Buffer.from(reference.left.buffer)),
      ).toBe(true);
      expect(
        Buffer.from(right.buffer).equals(Buffer.from(reference.right.buffer)),
      ).toBe(true);
    } finally {
      player.dispose();
    }
  },
  25_000,
);
