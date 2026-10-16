import type { Catalog, Lease, Ticket } from "../types/api";
import { abortError, delay } from "../utils/format";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}
export class ClusterApi {
  private learned: string[] = [];
  constructor(
    public readonly servers: string[],
    private readonly fetcher: typeof fetch = (input, init) =>
      globalThis.fetch(input, init),
  ) {}

  private async json<T>(
    url: string,
    init: RequestInit,
    signal: AbortSignal,
    timeout = 70_000,
  ): Promise<T> {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    if (signal.aborted) throw abortError();
    signal.addEventListener("abort", cancel, { once: true });
    const timer = setTimeout(cancel, timeout);
    try {
      const response = await this.fetcher(url, {
        ...init,
        signal: controller.signal,
      });
      const data: unknown = await response.json();
      if (!response.ok) {
        const body = data as { error?: string; message?: string };
        throw new ApiError(
          body.error ||
            body.message ||
            `El servidor respondió ${response.status}.`,
          response.status,
        );
      }
      return data as T;
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", cancel);
    }
  }

  async catalog(signal: AbortSignal): Promise<Catalog> {
    if (!this.servers.length)
      throw new Error(
        "Configura al menos un servidor para cargar tu biblioteca.",
      );
    const controllers = this.servers.map(() => new AbortController());
    const cancel = () =>
      controllers.forEach((controller) => controller.abort());
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
    try {
      const result = await Promise.any(
        this.servers.map(async (server, index) => {
          const data = await this.json<Catalog>(
            server + "/api/catalog",
            {},
            controllers[index]!.signal,
          );
          if (
            !Array.isArray(data.songs) ||
            !Array.isArray(data.nodes) ||
            !Array.isArray(data.offline)
          ) {
            throw new Error("El servidor no devolvió un catálogo válido.");
          }
          return data;
        }),
      );
      this.learned = result.nodes.map((node) => node.base_url);
      return result;
    } catch {
      if (signal.aborted) throw abortError();
      throw new Error(
        "No fue posible cargar la biblioteca. Revisa las direcciones y espera si Render está iniciando los servidores.",
      );
    } finally {
      signal.removeEventListener("abort", cancel);
      cancel();
    }
  }

  async acquire(
    songId: string,
    start: number,
    signal: AbortSignal,
    waiting: (ticket: Ticket) => void,
    leased: (lease: Lease) => void,
  ): Promise<Lease> {
    let lastError: unknown = new Error("No hay servidores disponibles.");
    for (const server of [...new Set([...this.servers, ...this.learned])]) {
      let lease: Lease | null = null;
      try {
        const ticket = await this.json<Ticket>(
          server + "/api/requests",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ song_id: songId, start }),
          },
          signal,
        );
        lease = { coordinator: server, ticket };
        leased(lease);
        const deadline =
          Date.now() + Math.max(180_000, ticket.wait_timeout * 1000 + 10_000);
        while (lease.ticket.state === "waiting") {
          waiting(lease.ticket);
          if (Date.now() >= deadline)
            throw new ApiError(
              "Se agotó el tiempo de espera. Puedes volver a intentar.",
              504,
            );
          await delay(700, signal);
          lease.ticket = await this.json<Ticket>(
            `${server}/api/requests/${ticket.request_id}`,
            {},
            signal,
            15_000,
          );
        }
        if (lease.ticket.state !== "ready" || !lease.ticket.stream) {
          throw new ApiError(
            lease.ticket.message || "La solicitud no pudo completarse.",
            lease.ticket.error_code || 409,
          );
        }
        return lease;
      } catch (error) {
        if (lease) this.release(lease);
        if (signal.aborted) throw abortError();
        if (
          error instanceof ApiError &&
          ![404, 410, 502, 503, 504].includes(error.status)
        )
          throw error;
        lastError = error;
      }
    }
    throw lastError;
  }

  release(lease: Lease): void {
    // keepalive permite liberar una reserva incluso al cerrar o recargar la página.
    void this.fetcher(
      `${lease.coordinator}/api/requests/${lease.ticket.request_id}`,
      {
        method: "DELETE",
        keepalive: true,
        signal: AbortSignal.timeout(5000),
      },
    ).catch(() => undefined);
  }
  async audio(url: string, signal: AbortSignal): Promise<Response> {
    const response = await this.fetcher(url, { signal, cache: "no-store" });
    if (!response.ok)
      throw new ApiError(
        `No se pudo recibir el audio (${response.status}).`,
        response.status,
      );
    if (!response.body)
      throw new Error("El navegador no admite recepción progresiva del audio.");
    return response;
  }
  async completed(
    server: string,
    id: string,
    signal: AbortSignal,
  ): Promise<boolean> {
    const result = await this.json<{ state: string }>(
      `${server}/api/streams/${id}`,
      {},
      signal,
      10_000,
    );
    return result.state === "completed";
  }
}
