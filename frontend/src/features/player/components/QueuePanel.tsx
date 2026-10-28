import { ListMusic, Play, Trash2, X } from "lucide-react";
import { useSoundFlow } from "../../../app/SoundFlowProvider";
import { IconButton, Button } from "../../../components/ui/Button";
import { Artwork } from "../../../components/ui/Artwork";
import { displayArtist, formatTime } from "../../../utils/format";
import { useOnline } from "../../../pwa/network";

export function QueuePanel() {
  const { playback, player, offline } = useSoundFlow();
  const online = useOnline();
  if (!playback.queueOpen) return null;
  return (
    <aside className="queue-panel card" aria-label="Cola de reproducción">
      <div className="queue-heading">
        <div>
          <span className="eyebrow">TU SELECCIÓN</span>
          <h2>
            A continuación <span>{playback.queue.length}</span>
          </h2>
        </div>
        <IconButton label="Ocultar cola" onClick={() => player.toggleQueue()}>
          <X size={18} />
        </IconButton>
      </div>
      {playback.queue.length ? (
        <>
          <ol className="queue-items">
            {playback.queue.map((item, index) => (
              <li key={item.key}>
                <span className="queue-index">{index + 1}</span>
                <Artwork id={item.song.id} />
                <button
                  className="queue-track"
                  disabled={!online && !offline.has(item.song.id)}
                  onClick={() => player.playQueued(item.key)}
                  aria-label={`Reproducir ${item.song.title} desde la cola`}
                >
                  <strong>{item.song.title}</strong>
                  <span>{displayArtist(item.song.artist)}</span>
                </button>
                <span className="queue-duration">
                  {formatTime(item.song.duration)}
                </span>
                <IconButton
                  label={`Quitar ${item.song.title} de la cola`}
                  onClick={() => player.remove(item.key)}
                >
                  <X size={15} />
                </IconButton>
              </li>
            ))}
          </ol>
          <div className="queue-bottom">
            <Button variant="ghost" onClick={() => player.clear()}>
              <Trash2 size={15} />
              Vaciar cola
            </Button>
            <span>La canción actual continúa.</span>
          </div>
        </>
      ) : (
        <div className="queue-empty">
          <ListMusic size={34} strokeWidth={1.3} />
          <h3>Prepara lo que sigue</h3>
          <p>Agrega canciones desde tu biblioteca para escucharlas en orden.</p>
        </div>
      )}
      <div className="queue-tip">
        <Play size={12} fill="currentColor" />
        Puedes reproducir una canción sin agregarla a la cola.
      </div>
    </aside>
  );
}
