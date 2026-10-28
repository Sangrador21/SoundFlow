import { beforeEach, describe, expect, it } from "vitest";
import { loadCatalog, saveCatalog } from "./catalog-storage";
import { song } from "../../test/fakes";

describe("Biblioteca de referencia sin conexión", () => {
  beforeEach(() => localStorage.clear());
  it("conserva metadatos pero no métricas, sesiones ni disponibilidad en vivo", () => {
    saveCatalog(["https://s1.test"], { songs: [song], nodes: [], offline: [] });
    const stored = loadCatalog(["https://s1.test"]);
    expect(stored?.songs[0]).toEqual({ ...song, available: false });
    expect(stored?.nodes).toEqual([]);
    expect(loadCatalog(["https://other.test"])).toBeNull();
  });
  it("ignora datos corruptos o con tipos inesperados", () => {
    localStorage.setItem("soundflow.catalog.v1", "broken");
    expect(loadCatalog([])).toBeNull();
    localStorage.setItem(
      "soundflow.catalog.v1",
      JSON.stringify({ servers: "", songs: [{ id: "bad" }] }),
    );
    expect(loadCatalog([])).toBeNull();
  });
});
