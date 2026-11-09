// @vitest-environment node
import { expect, it, vi } from "vitest";
import { interruptAfterBytes } from "./interrupted-response";

it("entrega el prefijo antes del fallo y no adelanta la interrupción", async () => {
  const cancel = vi.fn();
  const pull = vi.fn((controller: ReadableStreamDefaultController<Uint8Array>) => {
    controller.enqueue(Uint8Array.from({ length: 20 }, (_, i) => i));
  });
  const original = new Response(
    new ReadableStream({ pull, cancel }, { highWaterMark: 0 }),
    { headers: { "X-Audio-Format": "s16le" } },
  );
  const response = interruptAfterBytes(original, 11);
  const reader = response.body!.getReader();
  await Promise.resolve();
  expect(pull).not.toHaveBeenCalled();
  expect(response.headers.get("X-Audio-Format")).toBe("s16le");
  expect((await reader.read()).value).toEqual(
    Uint8Array.from({ length: 11 }, (_, i) => i),
  );
  // Esperar turnos del event loop no debe causar error ni descartar el prefijo.
  await new Promise((resolve) => setTimeout(resolve, 30));
  expect(cancel).not.toHaveBeenCalled();
  await expect(reader.read()).rejects.toThrow("Interrupción de prueba");
  expect(cancel).toHaveBeenCalledOnce();
});

it("construye el prefijo a partir de varios bloques de red", async () => {
  let index = 0;
  const original = new Response(
    new ReadableStream(
      {
        pull(controller) {
          controller.enqueue(Uint8Array.from([index++, index++, index++]));
        },
      },
      { highWaterMark: 0 },
    ),
  );
  const reader = interruptAfterBytes(original, 7).body!.getReader();
  expect((await reader.read()).value).toEqual(
    Uint8Array.from([0, 1, 2, 3, 4, 5, 6]),
  );
  await expect(reader.read()).rejects.toThrow("Interrupción de prueba");
});

it("rechaza un audio demasiado corto y permite cancelar antes del corte", async () => {
  const short = interruptAfterBytes(new Response(new Uint8Array(3)), 7);
  await expect(short.body!.getReader().read()).rejects.toThrow("antes del corte");
  const cancelled = vi.fn();
  const response = interruptAfterBytes(
    new Response(
      new ReadableStream({ cancel: cancelled }, { highWaterMark: 0 }),
    ),
    7,
  );
  await response.body!.cancel();
  expect(cancelled).toHaveBeenCalledOnce();
});
