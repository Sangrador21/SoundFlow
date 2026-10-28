export interface WorkerState {
  offlineReady: boolean;
  waiting: ServiceWorker | null;
  error: string;
}

export function registerServiceWorker(
  notify: (state: WorkerState) => void,
): () => void {
  if (
    !import.meta.env.PROD ||
    !("serviceWorker" in navigator) ||
    !window.isSecureContext
  )
    return () => {};
  let alive = true;
  let registration: ServiceWorkerRegistration | undefined;
  const cleanups: (() => void)[] = [];
  const publish = () => {
    if (alive && registration)
      notify({
        offlineReady: registration.active?.state === "activated",
        waiting: registration.waiting,
        error: "",
      });
  };
  const listen = (
    target: EventTarget,
    event: string,
    listener: EventListener,
  ) => {
    target.addEventListener(event, listener);
    cleanups.push(() => target.removeEventListener(event, listener));
  };
  const observe = () => {
    const worker = registration?.installing;
    if (worker) listen(worker, "statechange", publish);
    publish();
  };
  // Register immediately: the browser performs precaching outside React's render.
  void navigator.serviceWorker
    .register(import.meta.env.BASE_URL + "sw.js", {
      scope: import.meta.env.BASE_URL,
      updateViaCache: "none",
    })
    .then((value) => {
      if (!alive) return;
      registration = value;
      listen(value, "updatefound", observe);
      listen(navigator.serviceWorker, "controllerchange", publish);
      observe();
      void navigator.serviceWorker.ready.then(() => publish());
      const check = () => {
        if (navigator.onLine && document.visibilityState === "visible")
          void value.update().catch(() => {});
      };
      listen(window, "online", check);
      listen(document, "visibilitychange", check);
      const timer = window.setInterval(check, 60 * 60 * 1000);
      cleanups.push(() => clearInterval(timer));
    })
    .catch(() => {
      if (alive)
        notify({
          offlineReady: false,
          waiting: null,
          error:
            "No se pudo preparar el acceso sin conexión. Puedes seguir usando la versión web.",
        });
    });
  return () => {
    alive = false;
    cleanups.forEach((dispose) => dispose());
  };
}

export function activateUpdate(worker: ServiceWorker): Promise<void> {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer);
      navigator.serviceWorker.removeEventListener("controllerchange", changed);
    };
    const changed = () => {
      cleanup();
      resolve();
    };
    const timer = window.setTimeout(() => {
      cleanup();
      reject(
        new Error("No se pudo aplicar la actualización. Vuelve a intentar."),
      );
    }, 15_000);
    navigator.serviceWorker.addEventListener("controllerchange", changed);
    try {
      worker.postMessage({ type: "SOUNDFLOW_ACTIVATE_UPDATE" });
    } catch (error) {
      cleanup();
      reject(error);
    }
  });
}
