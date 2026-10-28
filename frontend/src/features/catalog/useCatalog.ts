import { useCallback, useEffect, useRef, useState } from "react";
import { useSoundFlow } from "../../app/SoundFlowProvider";
import type { Catalog } from "../../types/api";
import { errorMessage } from "../../utils/format";
import { loadCatalog, saveCatalog } from "./catalog-storage";
import { useOnline } from "../../pwa/network";

const EMPTY: Catalog = { songs: [], nodes: [], offline: [] };
export function useCatalog() {
  const { api } = useSoundFlow();
  const online = useOnline();
  const [saved, setSaved] = useState(false);
  const [catalog, setCatalog] = useState<Catalog>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);
  const refresh = useCallback(() => {
    abort.current?.abort();
    if (!navigator.onLine) {
      setCatalog(loadCatalog(api.servers) || EMPTY);
      setSaved(true);
      setLoading(false);
      setError("");
      return;
    }
    const controller = new AbortController();
    abort.current = controller;
    setLoading(true);
    setError("");
    void api
      .catalog(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setCatalog(data);
          setSaved(false);
          saveCatalog(api.servers, data);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          const previous = loadCatalog(api.servers);
          if (previous) {
            setCatalog(previous);
            setSaved(true);
          }
          setError(errorMessage(reason));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [api]);
  useEffect(() => {
    setCatalog(EMPTY);
    setSaved(false);
    refresh();
    return () => abort.current?.abort();
  }, [refresh, online]);
  return { catalog, loading, error, refresh, saved };
}
