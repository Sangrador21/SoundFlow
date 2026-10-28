// @vitest-environment node
import { IDBFactory } from "fake-indexeddb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OfflineStore } from "./offline-store";
import { song } from "../../test/fakes";

let store: OfflineStore;
beforeEach(() => {
  vi.stubGlobal("indexedDB", new IDBFactory());
  vi.stubGlobal("BroadcastChannel", undefined);
  store = new OfflineStore();
});
afterEach(() => {
  store.dispose();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
const track = (index: number) => ({
  ...song,
  id: String(index).repeat(64),
  title: "Track " + index,
});
async function save(index: number) {
  await store.save(
    track(index),
    new Blob(["audio"], { type: "audio/mpeg" }),
    "a".repeat(64),
  );
}

describe("Copias recientes atómicas en IndexedDB", () => {
  it("mantiene tres completas y reemplaza la menos reciente, incluyendo reproducciones locales", async () => {
    let time = 10;
    vi.spyOn(Date, "now").mockImplementation(() => time++);
    await save(1);
    await save(2);
    await save(3);
    await store.touch(track(1).id);
    await save(4);
    expect(store.getSnapshot().tracks.map((track) => track.song.title)).toEqual(
      ["Track 4", "Track 1", "Track 3"],
    );
    expect(await store.get(track(2).id)).toBeNull();
    expect(await (await store.get(track(1).id))!.blob.text()).toBe("audio");
  });
  it("una escritura cancelada no elimina las copias anteriores", async () => {
    await save(1);
    await save(2);
    await save(3);
    const signal = AbortSignal.abort();
    await expect(
      store.save(track(4), new Blob(["audio"]), "a".repeat(64), signal),
    ).rejects.toThrow();
    expect(store.getSnapshot().tracks).toHaveLength(3);
    expect(store.has(track(4).id)).toBe(false);
  });
  it("serializa escrituras concurrentes y conserva el máximo de tres", async () => {
    await Promise.all([save(1), save(2), save(3), save(4)]);
    await store.refresh();
    expect(store.getSnapshot().tracks).toHaveLength(3);
    await store.remove(track(4).id);
    expect(store.has(track(4).id)).toBe(false);
    await store.clear();
    expect(store.getSnapshot().tracks).toHaveLength(0);
  });
});
