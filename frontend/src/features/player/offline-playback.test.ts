import { afterEach, describe, expect, it, vi } from "vitest";
import { PlaybackController } from "./playback-controller";
import { ClusterApi } from "../../services/cluster-api";
import { FakeEngine, song, second } from "../../test/fakes";
import type { OfflineSource } from "../offline/offline-store";

afterEach(() => vi.restoreAllMocks());
function setup() {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
  const fetcher = vi.fn<typeof fetch>();
  class LocalEngine extends FakeEngine {
    async decodeFile() {
      const values = new Float32Array(44100 * 2).fill(0.25);
      return {
        length: values.length,
        duration: 2,
        numberOfChannels: 2,
        sampleRate: 44100,
        getChannelData: () => values,
      } as unknown as AudioBuffer;
    }
  }
  const engine = new LocalEngine();
  const source: OfflineSource = {
    has: () => true,
    touch: vi.fn(async () => {}),
    get: vi.fn(async (id) => ({
      id,
      song,
      blob: new Blob(["mp3"]),
      sha256: "a".repeat(64),
      lastUsed: 1,
    })),
  };
  const player = new PlaybackController(
    new ClusterApi(["https://s1.test"], fetcher),
    engine,
    source,
  );
  return { player, engine, fetcher };
}
describe("Reproducción local con el mismo motor y controles", () => {
  it("reproduce, pausa y avanza sin peticiones HTTP", async () => {
    const { player, engine, fetcher } = setup();
    player.play(song);
    await vi.waitFor(() => expect(engine.ends).toHaveLength(1));
    expect(player.getSnapshot().source).toBe("local");
    engine.onEvent({
      type: "progress",
      id: engine.ends[0]!,
      played: 4410,
      frames: 100,
      buffering: false,
    });
    player.toggle();
    expect(player.getSnapshot().status).toBe("paused");
    player.seek(0.75);
    await vi.waitFor(() => expect(engine.ends).toHaveLength(2));
    expect(player.getSnapshot().position).toBe(0.75);
    expect(player.getSnapshot().status).toBe("paused");
    expect(fetcher).not.toHaveBeenCalled();
    player.dispose();
  });
  it("avanza la cola offline una sola vez al terminar", async () => {
    const { player, engine, fetcher } = setup();
    player.play(song);
    await vi.waitFor(() => expect(engine.ends).toHaveLength(1));
    player.add([second]);
    engine.onEvent({
      type: "ended",
      id: engine.ends[0]!,
      played: 88200,
      frames: 0,
      buffering: false,
    });
    await vi.waitFor(() => expect(engine.ends).toHaveLength(2));
    expect(player.getSnapshot().current?.id).toBe(second.id);
    expect(player.getSnapshot().queue).toHaveLength(0);
    expect(fetcher).not.toHaveBeenCalled();
    player.dispose();
  });

  it("utiliza una copia existente cuando el servidor falla aunque onLine sea true", async () => {
    const { player, engine, fetcher } = setup();
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    fetcher.mockRejectedValue(new TypeError("Servidor sin conexión"));
    player.play(song);
    await vi.waitFor(() => expect(engine.ends).toHaveLength(1));
    expect(player.getSnapshot().source).toBe("local");
    expect(fetcher).toHaveBeenCalledOnce();
    player.dispose();
  });
});
