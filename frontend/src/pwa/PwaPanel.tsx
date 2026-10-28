import { useEffect, useState } from "react";
import { Download, RefreshCw, WifiOff } from "lucide-react";
import { Button } from "../components/ui/Button";
import { Modal } from "../components/ui/Modal";
import { useSoundFlow } from "../app/SoundFlowProvider";
import { activateUpdate, registerServiceWorker } from "./service-worker";
import type { WorkerState } from "./service-worker";
import { useOnline } from "./network";

interface InstallPrompt extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}
const installed = () =>
  window.matchMedia?.("(display-mode: standalone)").matches ||
  (navigator as Navigator & { standalone?: boolean }).standalone === true;

export function PwaPanel() {
  const { player, playback } = useSoundFlow();
  const online = useOnline();
  const [state, setState] = useState<WorkerState>({
    offlineReady: false,
    waiting: null,
    error: "",
  });
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const [isInstalled, setInstalled] = useState(installed);
  const [help, setHelp] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => registerServiceWorker(setState), []);
  useEffect(() => {
    const offer = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPrompt);
    };
    const done = () => {
      setInstalled(true);
      setPrompt(null);
      setHelp(false);
    };
    const display = window.matchMedia?.("(display-mode: standalone)");
    const changed = () => setInstalled(installed());
    window.addEventListener("beforeinstallprompt", offer);
    window.addEventListener("appinstalled", done);
    display?.addEventListener("change", changed);
    return () => {
      window.removeEventListener("beforeinstallprompt", offer);
      window.removeEventListener("appinstalled", done);
      display?.removeEventListener("change", changed);
    };
  }, []);
  const install = async () => {
    if (!prompt) {
      setHelp(true);
      return;
    }
    setBusy(true);
    try {
      await prompt.prompt();
      await prompt.userChoice;
    } catch {
      setHelp(true);
    } finally {
      setPrompt(null);
      setBusy(false);
    }
  };
  const update = async () => {
    if (!state.waiting) return;
    setBusy(true);
    setMessage("");
    try {
      // Only this explicit action stops playback and reloads this window.
      player.stop();
      await activateUpdate(state.waiting);
      window.location.reload();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "No se pudo actualizar.",
      );
      setBusy(false);
    }
  };
  const active = !["idle", "ended", "error"].includes(playback.status);
  return (
    <section className="pwa-panel" aria-label="Aplicación SoundFlow">
      <div className="pwa-summary">
        <span>
          {isInstalled ? "SoundFlow instalada" : "Lleva tu música contigo"}
        </span>
        {!isInstalled && (
          <Button variant="soft" disabled={busy} onClick={() => void install()}>
            <Download size={16} /> Instalar aplicación
          </Button>
        )}
      </div>
      {!online && (
        <div className="pwa-notice" role="status">
          <WifiOff size={18} />
          <p>
            <strong>Estás sin conexión.</strong> Puedes abrir la interfaz y
            consultar tu última biblioteca guardada. Escucha las pistas de
            «Disponibles sin conexión»; las demás necesitan Internet.
          </p>
        </div>
      )}
      {state.offlineReady && online && (
        <p className="pwa-ready">
          Interfaz disponible sin conexión en este navegador.
        </p>
      )}
      {state.waiting && (
        <div className="pwa-notice" role="status">
          <RefreshCw size={18} />
          <p>
            Hay una nueva versión disponible.
            {active
              ? " Al actualizar se detendrá la reproducción y se vaciará la cola de esta ventana."
              : " Al actualizar se recargará esta ventana y se vaciará su cola."}
          </p>
          <Button disabled={busy} onClick={() => void update()}>
            Actualizar ahora
          </Button>
        </div>
      )}
      {(message || state.error) && (
        <p role="status" className="form-error">
          {message || state.error}
        </p>
      )}
      {help && (
        <Modal title="Instalar SoundFlow" onClose={() => setHelp(false)}>
          <div className="modal-body install-help">
            <p>
              Abre SoundFlow desde su dirección publicada con HTTPS, o desde
              localhost para pruebas locales.
            </p>
            <ul>
              <li>
                <strong>Chrome o Edge:</strong> busca el icono de instalación en
                la barra de direcciones o la opción de instalar en el menú.
              </li>
              <li>
                <strong>Safari en Mac:</strong> utiliza Archivo → Añadir al
                Dock, si está disponible.
              </li>
              <li>
                <strong>iPhone o iPad:</strong> en Safari, abre Compartir →
                Añadir a pantalla de inicio.
              </li>
            </ul>
            <p>
              La opción depende del navegador y del dispositivo. Las copias
              completas de tus tres canciones recientes pueden escucharse sin
              Internet.
            </p>
            <div className="modal-actions">
              <Button onClick={() => setHelp(false)}>Entendido</Button>
            </div>
          </div>
        </Modal>
      )}
    </section>
  );
}
