import {
  AudioLines,
  ChevronRight,
  Library,
  ListMusic,
  RefreshCw,
  Server,
  Settings2,
} from "lucide-react";
import { IconButton, Button } from "../ui/Button";
import { useSoundFlow } from "../../app/SoundFlowProvider";
import type { View } from "./Sidebar";

export function Header({
  view,
  onView,
  loading,
  nodeCount,
  onRefresh,
  onSettings,
}: {
  view: View;
  onView: (view: View) => void;
  loading: boolean;
  nodeCount: number;
  onRefresh: () => void;
  onSettings: () => void;
}) {
  const { playback, player } = useSoundFlow();
  return (
    <header className="app-header">
      <div className="breadcrumb">
        <AudioLines className="mobile-brand" size={25} />
        <span>Tu espacio</span>
        <ChevronRight size={14} />
        <strong>{view === "library" ? "Biblioteca" : "Servidores"}</strong>
      </div>
      <div className="header-actions">
        <span className="connection-badge">
          <i className={nodeCount ? "dot dot--green" : "dot dot--amber"} />
          {nodeCount
            ? `${nodeCount} servidor${nodeCount === 1 ? "" : "es"}`
            : "Sin conexión"}
        </span>
        <IconButton
          label={loading ? "Actualizando biblioteca" : "Actualizar biblioteca"}
          onClick={onRefresh}
          disabled={loading}
        >
          <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
        </IconButton>
        <IconButton label="Configurar servidores" onClick={onSettings}>
          <Settings2 size={19} />
        </IconButton>
        <Button
          variant="soft"
          className="queue-toggle"
          aria-expanded={playback.queueOpen}
          onClick={() => player.toggleQueue()}
        >
          <ListMusic size={18} />
          <span>Cola</span>
          <b>{playback.queue.length}</b>
        </Button>
      </div>
      <nav className="mobile-nav" aria-label="Navegación móvil">
        <button
          className={view === "library" ? "is-active" : ""}
          onClick={() => onView("library")}
        >
          <Library size={16} />
          Biblioteca
        </button>
        <button
          className={view === "servers" ? "is-active" : ""}
          onClick={() => onView("servers")}
        >
          <Server size={16} />
          Servidores
        </button>
      </nav>
    </header>
  );
}
