const STORAGE_KEY = "soundflow.servers.v1";

export function normalizeServers(
  value: string | string[],
  requireHttps = false,
): string[] {
  const values = typeof value === "string" ? value.split(/[,\n]/) : value;
  return [
    ...new Set(
      values
        .map((raw) => raw.trim())
        .filter(Boolean)
        .map((raw) => {
          const url = new URL(raw);
          if (
            !["http:", "https:"].includes(url.protocol) ||
            url.username ||
            url.password ||
            url.search ||
            url.hash ||
            !["", "/"].includes(url.pathname)
          ) {
            throw new Error(
              "Usa direcciones base HTTP o HTTPS, sin rutas ni credenciales.",
            );
          }
          if (requireHttps && url.protocol !== "https:") {
            throw new Error("La página HTTPS requiere servidores con HTTPS.");
          }
          return url.origin;
        }),
    ),
  ];
}
export function defaultServers(): string[] {
  const value =
    import.meta.env.VITE_API_URLS ||
    (import.meta.env.DEV ? "http://127.0.0.1:5000,http://127.0.0.1:5001" : "");
  return normalizeServers(value, location.protocol === "https:");
}
export function loadServers(): string[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored
      ? normalizeServers(
          JSON.parse(stored) as string[],
          location.protocol === "https:",
        )
      : defaultServers();
  } catch {
    return defaultServers();
  }
}
export function saveServers(values: string[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(values));
}
