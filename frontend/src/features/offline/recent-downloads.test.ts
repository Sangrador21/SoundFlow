// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHash } from "node:crypto";
import { ClusterApi } from "../../services/cluster-api";
import { OfflineStore } from "./offline-store";
import { downloadRecent } from "./recent-downloads";
import { assigned, json, song } from "../../test/fakes";

function setup(mode = "ok") {
  const bytes = new TextEncoder().encode("complete compressed audio");
  const fetcher = vi.fn<typeof fetch>(async (url, init) => {
    if (init?.method === "POST") return json(assigned(1));
    if (init?.method === "DELETE") return new Response(null, { status: 204 });
    if (String(url).endsWith("/download"))
      return new Response(mode === "partial" ? bytes.slice(0, 4) : bytes, {
        headers: {
          "Content-Type": "audio/mpeg",
          "X-Download-Bytes": String(bytes.length),
          "X-Download-SHA256":
            mode === "corrupt"
              ? "0".repeat(64)
              : createHash("sha256").update(bytes).digest("hex"),
        },
      });
    return json({ state: "completed" });
  });
  const store = new OfflineStore();
  const save = vi.spyOn(store, "save").mockResolvedValue(undefined);
  return {
    store,
    save,
    fetcher,
    api: new ClusterApi(["https://s1.test"], fetcher),
  };
}
describe("Descarga comprimida e integridad", () => {
  it("solo confirma una copia completa y libera la reserva", async () => {
    const { store, save, api, fetcher } = setup();
    await downloadRecent(api, song, store, new AbortController().signal);
    expect(save).toHaveBeenCalledOnce();
    expect(
      fetcher.mock.calls.some((call) => call[1]?.method === "DELETE"),
    ).toBe(true);
  });
  it.each(["partial", "corrupt"])("no guarda una copia %s", async (mode) => {
    const { store, save, api, fetcher } = setup(mode);
    await expect(
      downloadRecent(api, song, store, new AbortController().signal),
    ).rejects.toThrow();
    expect(save).not.toHaveBeenCalled();
    expect(
      fetcher.mock.calls.some((call) => call[1]?.method === "DELETE"),
    ).toBe(true);
  });
});
