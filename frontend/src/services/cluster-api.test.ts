import { describe, expect, it, vi } from "vitest";
import { ClusterApi } from "./cluster-api";
import { assigned, json, song } from "../test/fakes";

describe("Coordinación HTTP del navegador", () => {
  it("conserva el contexto global de fetch al usar el cliente sin adaptador", async () => {
    const nativeFetch = function (this: unknown) {
      if (this !== globalThis) throw new TypeError("Illegal invocation");
      return Promise.resolve(json({ songs: [song], nodes: [], offline: [] }));
    };
    vi.stubGlobal("fetch", nativeFetch);
    try {
      const api = new ClusterApi(["https://s1.test"]);
      expect((await api.catalog(new AbortController().signal)).songs[0]?.id).toBe(
        song.id,
      );
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it("carga el catálogo con el servidor alternativo si la entrada cae", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("Offline"))
      .mockResolvedValueOnce(json({ songs: [song], nodes: [], offline: [] }));
    const api = new ClusterApi(["https://s1.test", "https://s2.test"], fetcher);
    expect((await api.catalog(new AbortController().signal)).songs[0]?.id).toBe(
      song.id,
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("muestra FIFO, consulta el ticket y obtiene una asignación sin crear otro", async () => {
    const ready = assigned(1);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        json({ ...ready, state: "waiting", position: 2, stream: null }),
      )
      .mockResolvedValueOnce(json(ready));
    const api = new ClusterApi(["https://s1.test"], fetcher);
    const waiting = vi.fn(),
      lease = vi.fn();
    const result = await api.acquire(
      song.id,
      4.5,
      new AbortController().signal,
      waiting,
      lease,
    );
    expect(waiting).toHaveBeenCalledWith(
      expect.objectContaining({ position: 2 }),
    );
    expect(result.ticket.stream?.server_id).toBe("S2");
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "https://s1.test/api/requests/ticket-1",
      expect.anything(),
    );
    const post = JSON.parse(fetcher.mock.calls[0]![1]!.body as string);
    expect(post).toEqual({ song_id: song.id, start: 4.5 });
  });
});
