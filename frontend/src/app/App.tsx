import { useState } from "react";
import { CircleAlert, Cloud, LoaderCircle, Settings2 } from "lucide-react";
import { useSoundFlow } from "./SoundFlowProvider";
import { useCatalog } from "../features/catalog/useCatalog";
import { CatalogTable } from "../features/catalog/CatalogTable";
import { ClusterView } from "../features/cluster/ClusterView";
import { ConnectionSettings } from "../features/cluster/ConnectionSettings";
import { NowPlaying } from "../features/player/components/NowPlaying";
import { PlayerBar } from "../features/player/components/PlayerBar";
import { QueuePanel } from "../features/player/components/QueuePanel";
import { Sidebar } from "../components/layout/Sidebar";
import type { View } from "../components/layout/Sidebar";
import { Header } from "../components/layout/Header";
import { Button } from "../components/ui/Button";
import { PwaPanel } from "../pwa/PwaPanel";
import { useOnline } from "../pwa/network";
import { OfflinePanel } from "../features/offline/OfflinePanel";

export function App() {
  const { playback, servers } = useSoundFlow();
  const { catalog, loading, error, refresh, saved } = useCatalog();
  const online = useOnline();
  const [view, setView] = useState<View>("library");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { player } = useSoundFlow();
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Ir al contenido
      </a>
      <Sidebar
        view={view}
        onView={setView}
        onQueue={() => player.toggleQueue()}
      />
      <div className="workspace">
        <Header
          view={view}
          onView={setView}
          loading={loading}
          nodeCount={catalog.nodes.length}
          onRefresh={refresh}
          onSettings={() => setSettingsOpen(true)}
        />
        <main id="main-content" className="main-content">
          <div className="content-width">
            <PwaPanel />
            {saved && (
              <p className="catalog-saved" role="status">
                Última biblioteca guardada: información de referencia, sin
                verificar disponibilidad actual.
              </p>
            )}
            {online && (!servers.length || error) && (
              <div className="connection-notice" role="alert">
                <CircleAlert size={20} />
                <div>
                  <strong>
                    {!servers.length
                      ? "Conecta tu biblioteca"
                      : "No pudimos conectar con tus servidores"}
                  </strong>
                  <p>
                    {!servers.length
                      ? "Configura las direcciones de S1 y S2 para comenzar."
                      : error}
                  </p>
                </div>
                <Button variant="soft" onClick={() => setSettingsOpen(true)}>
                  <Settings2 size={16} />
                  Configurar
                </Button>
              </div>
            )}
            {loading && (
              <div className="loading-notice" role="status">
                <LoaderCircle size={15} className="animate-spin" />
                Consultando tu biblioteca… Si Render estaba en reposo, puede
                tardar aproximadamente un minuto.
              </div>
            )}
            {view === "library" ? (
              <>
                <div className="library-intro">
                  <div>
                    <span className="eyebrow">HECHO PARA TI</span>
                    <h2>Hoy suena a ti.</h2>
                  </div>
                  <span>
                    <Cloud size={15} />
                    {online && !saved
                      ? "Tu biblioteca conectada"
                      : "Tu biblioteca guardada"}
                  </span>
                </div>
                <NowPlaying />
                <OfflinePanel />
                <div
                  className={`library-layout ${playback.queueOpen ? "with-queue" : ""}`}
                >
                  <CatalogTable songs={catalog.songs} loading={loading} />
                  <QueuePanel />
                </div>
              </>
            ) : (
              <>
                <ClusterView catalog={catalog} />
                {playback.queueOpen && (
                  <div className="server-queue">
                    <QueuePanel />
                  </div>
                )}
              </>
            )}
            <div className="page-footer">
              <span>SoundFlow</span>
              <p>Tu música, en conexión.</p>
            </div>
          </div>
        </main>
        <PlayerBar />
      </div>
      {settingsOpen && (
        <ConnectionSettings onClose={() => setSettingsOpen(false)} />
      )}
    </div>
  );
}
