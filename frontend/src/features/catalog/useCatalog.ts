import { useCallback, useEffect, useRef, useState } from "react";
import { useSoundFlow } from "../../app/SoundFlowProvider";
import type { Catalog } from "../../types/api";
import { errorMessage } from "../../utils/format";

const EMPTY: Catalog = { songs: [], nodes: [], offline: [] };
export function useCatalog() {
  const { api } = useSoundFlow();
  const [catalog, setCatalog] = useState<Catalog>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);
  const refresh = useCallback(() => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setLoading(true);
    setError("");
    void api
      .catalog(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setCatalog(data);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [api]);
  useEffect(() => {
    setCatalog(EMPTY);
    refresh();
    return () => abort.current?.abort();
  }, [refresh]);
  return { catalog, loading, error, refresh };
}
