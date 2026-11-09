/** Interrumpe una respuesta real después de entregar un prefijo PCM conocido. */
export function interruptAfterBytes(response: Response, bytes: number): Response {
  if (!response.body || !Number.isSafeInteger(bytes) || bytes < 1)
    throw new Error("La prueba necesita una respuesta y un tamaño válidos.");
  const reader = response.body.getReader();
  let delivered = false;
  const cancel = () => reader.cancel().catch(() => undefined);
  const body = new ReadableStream<Uint8Array>(
    {
      async pull(controller) {
        if (delivered) {
          // Este pull solo ocurre cuando el reproductor vuelve a pedir datos,
          // después de decodificar y entregar el prefijo al motor de audio.
          void cancel();
          controller.error(new TypeError("Interrupción de prueba"));
          return;
        }
        const prefix = new Uint8Array(bytes);
        let offset = 0;
        try {
          while (offset < bytes) {
            const chunk = await reader.read();
            if (chunk.done)
              throw new Error("El audio de prueba terminó antes del corte.");
            const count = Math.min(bytes - offset, chunk.value.byteLength);
            prefix.set(chunk.value.subarray(0, count), offset);
            offset += count;
          }
          delivered = true;
          controller.enqueue(prefix);
        } catch (error) {
          void cancel();
          controller.error(error);
        }
      },
      cancel,
    },
    // No precargar otro pull: error() descarta lo que todavía esté en cola.
    { highWaterMark: 0 },
  );
  return new Response(body, { status: response.status, headers: response.headers });
}
