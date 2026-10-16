export function formatTime(value: number): string {
  const seconds = Math.max(0, Math.floor(Number.isFinite(value) ? value : 0));
  return `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}
export function displayArtist(value: string): string {
  return value && !["desconocido", "unknown"].includes(value.toLowerCase())
    ? value
    : "Artista desconocido";
}
export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Ocurrió un error inesperado.";
}
export function abortError(): DOMException {
  return new DOMException("Operación cancelada", "AbortError");
}
export function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const done = () => {
      signal?.removeEventListener("abort", cancel);
      resolve();
    };
    const id = setTimeout(done, ms);
    const cancel = () => {
      clearTimeout(id);
      signal?.removeEventListener("abort", cancel);
      reject(abortError());
    };
    signal?.addEventListener("abort", cancel, { once: true });
  });
}
