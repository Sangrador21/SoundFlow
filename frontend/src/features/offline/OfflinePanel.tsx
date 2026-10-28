import { Download, Play, Trash2, WifiOff } from "lucide-react";
import { useSoundFlow } from "../../app/SoundFlowProvider";
import { Button, IconButton } from "../../components/ui/Button";
import { formatTime } from "../../utils/format";

export function OfflinePanel() {
  const { offline, offlineState: state, player, recent } = useSoundFlow();
  const remove = async (id?: string) => {
    recent.cancel();
    try {
      if (id) await offline.remove(id);
      else await offline.clear();
      offline.update({
        message: id
          ? "Copia eliminada de este dispositivo."
          : "Copias locales eliminadas.",
      });
    } catch {
      offline.update({
        message: "No se pudieron eliminar las copias. Vuelve a intentar.",
      });
    }
  };
  return (
    <section className="offline-card card" aria-labelledby="offline-title">
      <div className="offline-heading">
        <div>
          <h2 id="offline-title">
            <WifiOff size={18} /> Disponibles sin conexión{" "}
            <span>{state.tracks.length}/3</span>
          </h2>
          <p>
            Tus tres canciones recientes completas, guardadas en este navegador.
          </p>
        </div>
        {!!state.tracks.length && (
          <Button variant="ghost" onClick={() => void remove()}>
            <Trash2 size={15} /> Borrar copias
          </Button>
        )}
      </div>
      <label className="offline-setting">
        <input
          type="checkbox"
          checked={state.enabled}
          onChange={(event) => {
          recent.setEnabled(event.target.checked);
          }}
        />{" "}
        Guardar recientes automáticamente
      </label>
      {state.activeId && (
        <div className="offline-progress" role="status">
          <Download size={16} />
          <span>Preparando copia: {state.progress}%</span>
          <progress
            max={100}
            value={state.progress}
            aria-label="Progreso de la copia sin conexión"
          />
        </div>
      )}
      {state.tracks.length ? (
        <ul className="offline-tracks">
          {state.tracks.map((track) => (
            <li key={track.id}>
              <IconButton
                label={`Reproducir ${track.song.title} sin conexión`}
                onClick={() => player.playOffline(track.song)}
              >
                <Play size={17} fill="currentColor" />
              </IconButton>
              <div>
                <strong>{track.song.title}</strong>
                <span>
                  {formatTime(track.song.duration)} ·{" "}
                  {(track.bytes / 1024 / 1024).toFixed(1)} MB · Copia completa
                </span>
              </div>
              <IconButton
                label={`Eliminar copia de ${track.song.title}`}
                onClick={() => void remove(track.id)}
              >
                <Trash2 size={16} />
              </IconButton>
            </li>
          ))}
        </ul>
      ) : (
        <p className="offline-empty">
          Escucha una canción con conexión y espera a que termine de guardarse.
          Aquí aparecerá cuando esté completa.
        </p>
      )}
      {state.message && (
        <p className="offline-message" role="status">
          {state.message}
        </p>
      )}
    </section>
  );
}
