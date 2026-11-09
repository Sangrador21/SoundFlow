import { describe, expect, it, vi } from "vitest";
import { PlaybackController } from "./playback-controller";
import { ClusterApi } from "../../services/cluster-api";
import { interruptAfterBytes } from "../../test/interrupted-response";
import {
  assigned,
  FakeEngine,
  json,
  pcmHeaders,
  second,
  song,
} from "../../test/fakes";

function create() {
  let index = 0;
  const fetcher = vi.fn<typeof fetch>(async (url, init) => {
    if (init?.method === "DELETE") return new Response(null, { status: 204 });
    if (init?.method === "POST")
      return json(assigned(++index, JSON.parse(init.body as string).start));
    if (String(url).endsWith("/audio"))
      return new Response(new Uint8Array(8), { headers: pcmHeaders });
    return json({ state: "completed" });
  });
  const engine = new FakeEngine();
  const player = new PlaybackController(
    new ClusterApi(["https://s1.test"], fetcher),
    engine,
  );
  return { player, engine, fetcher };
}
describe("Reproductor web", () => {
  it("reproduce directamente y vaciar la cola conserva la canción actual", async () => {
    const { player, engine, fetcher } = create();
    player.play(song);
    await vi.waitFor(() => expect(engine.ends).toHaveLength(1));
    expect(player.getSnapshot().current?.id).toBe(song.id);
    player.add([second, song]);
    expect(player.getSnapshot().queueOpen).toBe(true);
    player.clear();
    expect(player.getSnapshot().queue).toHaveLength(0);
    expect(player.getSnapshot().current?.id).toBe(song.id);
    expect(
      fetcher.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1);
    player.dispose();
  });
  it("avanza por segundos, descarta eventos antiguos y detener no vuelve a buffering", async () => {
    const { player, engine, fetcher } = create();
    player.play(song);
    await vi.waitFor(() => expect(engine.ends).toHaveLength(1));
    const old = engine.ends[0]!;
    player.seek(5.75);
    await vi.waitFor(() => expect(engine.ends).toHaveLength(2));
    const posts = fetcher.mock.calls.filter(
      (call) => call[1]?.method === "POST",
    );
    expect(JSON.parse(posts[1]![1]!.body as string).start).toBe(5.75);
    engine.onEvent({
      type: "ended",
      id: old,
      played: 1,
      frames: 0,
      buffering: false,
    });
    expect(player.getSnapshot().position).toBe(5.75);
    player.stop();
    engine.onEvent({
      type: "progress",
      id: old,
      played: 0,
      frames: 0,
      buffering: true,
    });
    expect(player.getSnapshot().status).toBe("idle");
    player.dispose();
  });
  it("consume la cola una sola vez y se detiene al terminar", async () => {
    const { player, engine } = create();
    player.play(song);
    await vi.waitFor(() => expect(engine.ends).toHaveLength(1));
    player.add([second]);
    engine.onEvent({
      type: "ended",
      id: engine.ends[0]!,
      played: 20 * 44100,
      frames: 0,
      buffering: false,
    });
    await vi.waitFor(() => expect(engine.ends).toHaveLength(2));
    expect(player.getSnapshot().current?.id).toBe(second.id);
    expect(player.getSnapshot().queue).toHaveLength(0);
    engine.onEvent({
      type: "ended",
      id: engine.ends[1]!,
      played: 20 * 44100,
      frames: 0,
      buffering: false,
    });
    expect(player.getSnapshot().status).toBe("ended");
    engine.onEvent({
      type: "progress",
      id: engine.ends[1]!,
      played: 20 * 44100,
      frames: 0,
      buffering: false,
    });
    expect(player.getSnapshot().status).toBe("ended");
    player.dispose();
  });
  it.each([false, true])("reanuda sin duplicar muestras ni canales (fallo antes del audio: %s)", async (failBeforeAudio) => {
    const bytes = new Uint8Array(32);
    const view = new DataView(bytes.buffer);
    for (let i = 0; i < 16; i++) view.setInt16(i * 2, i * 256, true);
    const starts: number[] = [];
    let attempts = 0;
    const fetcher = vi.fn<typeof fetch>(async (url, init) => {
      if (init?.method === "DELETE") return new Response(null, { status: 204 });
      if (init?.method === "POST") {
        const start = JSON.parse(init.body as string).start as number;
        starts.push(start);
        if (failBeforeAudio && starts.length === 1)
          throw new TypeError("Conexión cerrada antes de recibir audio");
        return json(assigned(starts.length, start));
      }
      if (String(url).endsWith("/audio")) {
        if (attempts++ === 0) {
          return interruptAfterBytes(
            new Response(bytes, { headers: pcmHeaders }),
            10,
          );
        }
        return new Response(bytes.slice(8), { headers: pcmHeaders });
      }
      return json({ state: "completed" });
    });
    const engine = new FakeEngine();
    const player = new PlaybackController(
      new ClusterApi(["https://s1.test"], fetcher),
      engine,
    );
    player.play(song);
    await vi.waitFor(() => expect(engine.ends).toHaveLength(1), {
      timeout: 4000,
    });
    expect(starts).toEqual(failBeforeAudio ? [0, 0, 2 / 44100] : [0, 2 / 44100]);
    expect(engine.blocks.flatMap((block) => [...block.left])).toEqual(
      Array.from({ length: 8 }, (_, i) => (i * 512) / 32768),
    );
    expect(engine.blocks.flatMap((block) => [...block.right])).toEqual(
      Array.from({ length: 8 }, (_, i) => (i * 512 + 256) / 32768),
    );
    player.dispose();
  });
});
