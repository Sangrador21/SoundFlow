import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CatalogTable } from "./CatalogTable";
import { song, second } from "../../test/fakes";
const play = vi.fn(),
  add = vi.fn();
vi.mock("../../app/SoundFlowProvider", () => ({
  useSoundFlow: () => ({
    player: { play, add },
    playback: { current: null, status: "idle" },
  }),
}));

describe("Biblioteca web", () => {
  it("reproduce con un clic y agrega varias seleccionadas sin exigir abrir la cola", async () => {
    const user = userEvent.setup();
    render(<CatalogTable songs={[song, second]} loading={false} />);
    await user.click(
      screen.getByRole("button", { name: "Reproducir Canción uno" }),
    );
    expect(play).toHaveBeenCalledWith(song);
    await user.click(
      screen.getByRole("checkbox", { name: "Seleccionar Canción uno" }),
    );
    await user.click(
      screen.getByRole("checkbox", { name: "Seleccionar Canción dos" }),
    );
    await user.click(screen.getByRole("button", { name: /Agregar a cola/ }));
    expect(add).toHaveBeenCalledWith([song, second]);
  });
  it("filtra por búsqueda y por servidor", async () => {
    const user = userEvent.setup();
    render(<CatalogTable songs={[song, second]} loading={false} />);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Filtrar por servidor" }),
      "S2",
    );
    expect(
      screen.queryByRole("button", { name: "Reproducir Canción uno" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reproducir Canción dos" }),
    ).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox"), "no existe");
    expect(screen.getByText("No encontramos esa canción")).toBeInTheDocument();
  });
});
