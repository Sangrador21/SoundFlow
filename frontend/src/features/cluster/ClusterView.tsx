import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  CloudOff,
  HardDrive,
  Radio,
  Server,
} from "lucide-react";
import type { Catalog } from "../../types/api";

export function ClusterView({ catalog }: { catalog: Catalog }) {
  return (
    <section className="cluster-view" aria-label="Estado de los servidores">
      <div className="page-heading">
        <span className="eyebrow">EN CONEXIÓN</span>
        <h1>Tu música, distribuida.</h1>
        <p>
          Conoce qué servidores forman parte de tu biblioteca y cómo están
          trabajando.
        </p>
      </div>
      <div className="cluster-summary">
        <div>
          <Server size={19} />
          <strong>{catalog.nodes.length}</strong>
          <span>Servidores disponibles</span>
        </div>
        <div>
          <Radio size={19} />
          <strong>{catalog.songs.length}</strong>
          <span>Canciones únicas</span>
        </div>
        <div>
          <Activity size={19} />
          <strong>
            {catalog.nodes.reduce(
              (n, node) => n + node.resources.active_streams,
              0,
            )}
          </strong>
          <span>Transferencias activas</span>
        </div>
      </div>
      <div className="node-grid">
        {catalog.nodes.map((node) => (
          <article className="node-card card" key={node.base_url}>
            <div className="node-top">
              <span className="node-icon">
                <Server size={23} />
              </span>
              <span
                className={`badge ${node.resources.accepting ? "badge--green" : "badge--amber"}`}
              >
                <i
                  className={`dot ${node.resources.accepting ? "dot--green" : "dot--amber"}`}
                />
                {node.resources.maintenance
                  ? "En mantenimiento"
                  : node.resources.accepting
                    ? "Disponible"
                    : "Ocupado"}
              </span>
            </div>
            <h2>{node.server_id}</h2>
            <a
              href={node.base_url + "/api/health"}
              target="_blank"
              rel="noreferrer"
            >
              {node.base_url}
              <ArrowUpRight size={13} />
            </a>
            <div className="node-library">
              <HardDrive size={16} />
              <strong>{node.song_count}</strong> canciones en su biblioteca
            </div>
            <div className="node-metrics">
              {[
                ["CPU", node.resources.cpu_percent],
                ["Memoria", node.resources.memory_percent],
              ].map(([label, raw]) => {
                const value = Number(raw);
                return (
                  <div key={label}>
                    <div>
                      <span>{label}</span>
                      <strong>{value.toFixed(1)} %</strong>
                    </div>
                    <meter
                      min={0}
                      max={100}
                      value={value}
                      aria-label={`${label} de ${node.server_id}`}
                    />
                  </div>
                );
              })}
            </div>
            <div className="node-foot">
              <CheckCircle2 size={14} />
              {node.resources.active_streams} transferencia
              {node.resources.active_streams === 1 ? "" : "s"} activa
              {node.resources.active_streams === 1 ? "" : "s"}
            </div>
          </article>
        ))}
        {catalog.offline.map((url) => (
          <article className="node-card card node-card--offline" key={url}>
            <CloudOff size={26} />
            <h2>Sin conexión</h2>
            <p>{url}</p>
            <span>El nodo no respondió a la última consulta.</span>
          </article>
        ))}
      </div>
      {!catalog.nodes.length && !catalog.offline.length && (
        <div className="card library-empty">
          <Server size={35} />
          <h3>Aún no hay servidores conectados</h3>
          <p>Abre la configuración para indicar sus direcciones.</p>
        </div>
      )}
      <p className="cluster-note">
        Los valores corresponden a la última actualización. La espera de
        solicitudes del servicio es independiente de tu cola de reproducción.
      </p>
    </section>
  );
}
