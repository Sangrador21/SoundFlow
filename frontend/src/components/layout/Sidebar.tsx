import { AudioLines, Library, ListMusic, Radio, Server } from "lucide-react";
export type View = "library" | "servers";
export function Sidebar({
  view,
  onView,
  onQueue,
}: {
  view: View;
  onView: (view: View) => void;
  onQueue: () => void;
}) {
  return (
    <aside className="sidebar">
      <a
        className="brand"
        href="#"
        onClick={(event) => {
          event.preventDefault();
          onView("library");
        }}
        aria-label="SoundFlow, ir a biblioteca"
      >
        <span className="brand-symbol">
          <AudioLines size={25} />
        </span>
        <span>
          SoundFlow<small>TU MÚSICA, EN CONEXIÓN</small>
        </span>
      </a>
      <div className="sidebar-section">TU ESPACIO</div>
      <nav aria-label="Navegación principal">
        <button
          className={`nav-item ${view === "library" ? "is-active" : ""}`}
          aria-current={view === "library" ? "page" : undefined}
          onClick={() => onView("library")}
        >
          <Library size={19} />
          Biblioteca
        </button>
        <button className="nav-item" onClick={onQueue}>
          <ListMusic size={19} />A continuación
        </button>
        <button
          className={`nav-item ${view === "servers" ? "is-active" : ""}`}
          aria-current={view === "servers" ? "page" : undefined}
          onClick={() => onView("servers")}
        >
          <Server size={19} />
          Servidores
        </button>
      </nav>
      <div className="sidebar-note">
        <Radio size={20} />
        <p>
          La música nos conecta.
          <span>Encuentra tu siguiente canción y dale play.</span>
        </p>
        <div className="sidebar-wave" aria-hidden="true">
          {[18, 28, 14, 38, 26, 44, 19, 32, 24, 39, 17, 29, 12].map(
            (height, i) => (
              <i key={i} style={{ height }} />
            ),
          )}
        </div>
      </div>
      <div className="sidebar-footer">
        <span>P06</span>
        <div>
          Servicios web<small>Sistemas Distribuidos</small>
        </div>
      </div>
    </aside>
  );
}
