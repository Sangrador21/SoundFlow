import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/__test__/download-mode?mode=full");
  await page.addInitScript(() => {
    localStorage.setItem(
      "soundflow.servers.v1",
      JSON.stringify(["http://127.0.0.1:4174"]),
    );
  });
  await page.goto("/SoundFlow/");
  await expect(
    page.getByRole("button", { name: "Reproducir Canción de prueba" }),
  ).toBeVisible();
  await expect(
    page.getByText("Interfaz disponible sin conexión en este navegador."),
  ).toBeVisible();
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
});

test("manifiesto, iconos, ámbito y apertura sin conexión bajo /SoundFlow/", async ({
  page,
  context,
  request,
}) => {
  await page.screenshot({
    path: "test-results/pwa-desktop.png",
    fullPage: true,
  });
  const manifest = await (
    await request.get("/SoundFlow/manifest.webmanifest")
  ).json();
  expect(manifest).toMatchObject({
    start_url: "/SoundFlow/",
    scope: "/SoundFlow/",
    display: "standalone",
  });
  for (const icon of manifest.icons)
    expect((await request.get(icon.src)).status()).toBe(200);
  expect(
    await page.evaluate(
      async () => (await navigator.serviceWorker.ready).scope,
    ),
  ).toBe("http://127.0.0.1:4173/SoundFlow/");
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText("Estás sin conexión.")).toBeVisible();
  await expect(
    page.getByText("Última biblioteca guardada:", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reproducir Canción de prueba" }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/pwa-offline.png",
    fullPage: true,
  });
  await page.getByRole("searchbox").fill("prueba");
  await expect(
    page.getByRole("button", { name: "Reproducir Canción de prueba" }),
  ).toBeVisible();
  await context.setOffline(false);
  await expect(
    page.getByRole("button", { name: "Reproducir Canción de prueba" }),
  ).toBeEnabled();
  await expect(
    page.getByText("Última biblioteca guardada:", { exact: false }),
  ).not.toBeVisible();
});

test("la reproducción usa REST y PCM sin guardarlos en Cache Storage", async ({
  page,
}) => {
  await page
    .getByRole("button", { name: "Reproducir Canción de prueba" })
    .click();
  await expect(
    page.getByRole("button", { name: "Pausar", exact: true }),
  ).toBeVisible();
  // Also exercise a same-origin API URL to prove the worker bypasses /api/.
  const fromWorker = await page.evaluate(async () => {
    const response = await fetch("/SoundFlow/api/health");
    return (await response.json()).state;
  });
  expect(fromWorker).toBe("completed");
  const entries = await page.evaluate(async () => {
    const lists = await Promise.all(
      (await caches.keys()).map(async (key) =>
        (await (await caches.open(key)).keys()).map((request) => request.url),
      ),
    );
    return lists.flat();
  });
  expect(
    entries.some((url) => url.includes("/api/") || url.includes(":4174")),
  ).toBe(false);
  expect(entries.some((url) => url.endsWith("/worklets/pcm-player.js"))).toBe(
    true,
  );
});

test("una actualización espera consentimiento y no recarga al detectarse", async ({
  page,
  request,
}) => {
  await page
    .getByRole("button", { name: "Reproducir Canción de prueba" })
    .click();
  await expect(
    page.getByRole("button", { name: "Pausar", exact: true }),
  ).toBeVisible();
  const oldVersion = await page.evaluate(async () =>
    (await caches.keys()).find((key) => key.startsWith("soundflow-shell:")),
  );
  await page.evaluate(() => {
    (window as Window & { unchanged?: boolean }).unchanged = true;
  });
  await request.post("/__test__/revision");
  await page.evaluate(async () => {
    await (await navigator.serviceWorker.ready).update();
  });
  await expect(
    page.getByRole("button", { name: "Actualizar ahora" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as Window & { unchanged?: boolean }).unchanged,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("button", { name: "Pausar", exact: true }),
  ).toBeVisible();
  await Promise.all([
    page.waitForEvent("load"),
    page.getByRole("button", { name: "Actualizar ahora" }).click(),
  ]);
  await expect(
    page.getByText("Interfaz disponible sin conexión en este navegador."),
  ).toBeVisible();
  expect(
    await page.evaluate(
      async (version) => (await caches.keys()).includes(version!),
      oldVersion,
    ),
  ).toBe(false);
});

test("la vista móvil mantiene accesible la instalación y el reproductor", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Instalar aplicación" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/pwa-mobile.png",
    fullPage: true,
  });
});

test("guarda una copia completa y reproduce, pausa y avanza tras recargar sin red", async ({
  page,
  context,
}) => {
  await page
    .getByRole("button", { name: "Reproducir Canción de prueba", exact: true })
    .click();
  const local = page.getByRole("button", {
    name: "Reproducir Canción de prueba sin conexión",
    exact: true,
  });
  await expect(local).toBeVisible({ timeout: 15_000 });
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText("Estás sin conexión.")).toBeVisible();
  await expect(local).toBeVisible();
  const network: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) network.push(request.url());
  });
  await local.click();
  await expect(
    page.getByText("Copia local · Sin conexión", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Pausar", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pausar", exact: true }).click();
  const seek = page.getByRole("slider", { name: "Posición de reproducción" });
  await expect(seek).toBeEnabled();
  await seek.focus();
  await seek.press("ArrowRight");
  await expect(
    page.getByRole("button", { name: "Reproducir", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reproducir", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Pausar", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/offline-playback.png",
    fullPage: true,
  });
  expect(network).toEqual([]);
  await page
    .getByRole("button", {
      name: "Eliminar copia de Canción de prueba",
      exact: true,
    })
    .click();
  await expect(local).not.toBeVisible();
});

test("las cuatro canciones recientes se limitan a tres copias completas", async ({
  page,
}) => {
  for (const name of [
    "Canción de prueba",
    "Reciente 2",
    "Reciente 3",
    "Reciente 4",
  ]) {
    await page
      .getByRole("button", { name: `Reproducir ${name}`, exact: true })
      .click();
    await expect(
      page.getByRole("button", {
        name: `Reproducir ${name} sin conexión`,
        exact: true,
      }),
    ).toBeVisible({ timeout: 15_000 });
  }
  await expect(
    page.getByRole("button", {
      name: "Reproducir Canción de prueba sin conexión",
      exact: true,
    }),
  ).not.toBeVisible();
  await expect(page.locator(".offline-tracks li")).toHaveCount(3);
  await page
    .getByRole("button", { name: "Borrar copias", exact: true })
    .click();
  await expect(page.locator(".offline-tracks li")).toHaveCount(0);
});

test("una copia interrumpida no aparece como disponible", async ({
  page,
  request,
}) => {
  await request.post("/__test__/download-mode?mode=partial");
  await page
    .getByRole("button", { name: "Reproducir Canción de prueba", exact: true })
    .click();
  await expect(
    page.getByText(
      "La descarga se interrumpió; no se guardó una copia incompleta.",
      { exact: true },
    ),
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    page.getByRole("button", {
      name: "Reproducir Canción de prueba sin conexión",
      exact: true,
    }),
  ).not.toBeVisible();
});
