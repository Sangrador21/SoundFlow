import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { SoundFlowProvider } from "./SoundFlowProvider";
import { assigned, json, pcmHeaders, second, song } from "../test/fakes";

vi.mock("../features/player/audio/audio-engine", async () => ({
  AudioEngine: (await import("../test/fakes")).FakeEngine,
}));

describe("Aplicación completa en el DOM", () => {
  it("carga la biblioteca, permite reproducir, agregar, ocultar y vaciar la cola", async () => {
    localStorage.clear();
    let number = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(async (url, init) => {
        if (String(url).endsWith("/api/catalog"))
          return json({ songs: [song, second], nodes: [], offline: [] });
        if (init?.method === "POST") return json(assigned(++number));
        if (init?.method === "DELETE")
          return new Response(null, { status: 204 });
        if (String(url).endsWith("/audio"))
          return new Response(new Uint8Array(8), { headers: pcmHeaders });
        return json({ state: "completed" });
      }),
    );
    const user = userEvent.setup();
    const app = render(
      <SoundFlowProvider>
        <App />
      </SoundFlowProvider>,
    );
    const first = await screen.findByRole("button", {
      name: "Reproducir Canción uno",
    });
    expect(
      screen.queryByRole("complementary", { name: "Cola de reproducción" }),
    ).not.toBeInTheDocument();
    await user.click(first);
    expect(
      within(screen.getByRole("region", { name: "Canción actual" })).getByRole(
        "heading",
        { name: song.title },
      ),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Agregar Canción dos a la cola" }),
    );
    const queue = screen.getByRole("complementary", {
      name: "Cola de reproducción",
    });
    expect(
      within(queue).getByRole("button", {
        name: "Reproducir Canción dos desde la cola",
      }),
    ).toBeInTheDocument();
    await user.click(
      within(queue).getByRole("button", { name: "Vaciar cola" }),
    );
    expect(
      screen.queryByRole("complementary", { name: "Cola de reproducción" }),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Canción actual" })).getByRole(
        "heading",
        { name: song.title },
      ),
    ).toBeInTheDocument();
    app.unmount();
    vi.unstubAllGlobals();
  });
});
