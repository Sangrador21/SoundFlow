import { useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  CircleAlert,
  ListMusic,
  LoaderCircle,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Square,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useSoundFlow } from "../../../app/SoundFlowProvider";
import { IconButton } from "../../../components/ui/Button";
import { Artwork } from "../../../components/ui/Artwork";
import { displayArtist, formatTime } from "../../../utils/format";

export function PlayerBar() {
  const { playback: p, player } = useSoundFlow();
  const [draft, setDraft] = useState<{ id: string; value: number } | null>(
    null,
  );
  const unmuted = useRef(0.7);
  const duration = p.current?.duration || 0;
  const position =
    draft && draft.id === p.current?.id ? draft.value : p.position;
  const busy = ["loading", "waiting"].includes(p.status);
  const playing = ["playing", "buffering"].includes(p.status);
  const commit = (value: number) => {
    setDraft(null);
    player.seek(value);
  };
  return (
    <footer className="player-bar" aria-label="Reproductor">
      <div className="player-track">
        <Artwork id={p.current?.id} />
        <div>
          <strong title={p.current?.title}>
            {p.current?.title || "Tu próxima canción"}
          </strong>
          <span>
            {p.current
              ? displayArtist(p.current.artist)
              : "Selecciona desde la biblioteca"}
          </span>
        </div>
      </div>
      <div className="player-center">
        <div className="transport-controls">
          <IconButton
            label="Canción anterior"
            disabled={!p.current}
            onClick={() => player.previous()}
          >
            <SkipBack size={19} fill="currentColor" />
          </IconButton>
          <IconButton
            label={
              busy ? "Preparando audio" : playing ? "Pausar" : "Reproducir"
            }
            className="play-control"
            disabled={!p.current || busy}
            onClick={() => player.toggle()}
          >
            {busy ? (
              <LoaderCircle size={23} className="animate-spin" />
            ) : playing ? (
              <Pause size={21} fill="currentColor" />
            ) : (
              <Play size={21} fill="currentColor" />
            )}
          </IconButton>
          <IconButton
            label="Siguiente canción"
            disabled={!p.queue.length}
            onClick={() => player.next()}
          >
            <SkipForward size={19} fill="currentColor" />
          </IconButton>
          <IconButton
            label="Detener reproducción"
            disabled={!p.current}
            onClick={() => player.stop()}
          >
            <Square size={16} fill="currentColor" />
          </IconButton>
        </div>
        <div className="seek-row">
          <span>{formatTime(position)}</span>
          <input
            type="range"
            className="seek-slider"
            min={0}
            max={duration || 1}
            step={0.1}
            value={Math.min(position, duration || 1)}
            disabled={!duration}
            aria-label="Posición de reproducción"
            aria-valuetext={`${formatTime(position)} de ${formatTime(duration)}`}
            style={
              {
                "--played": `${duration ? (position / duration) * 100 : 0}%`,
                "--buffered": `${duration ? Math.min(100, (p.bufferedUntil / duration) * 100) : 0}%`,
              } as CSSProperties
            }
            onChange={(event) =>
              setDraft({ id: p.current!.id, value: event.target.valueAsNumber })
            }
            onPointerUp={(event) => commit(event.currentTarget.valueAsNumber)}
            onPointerCancel={() => setDraft(null)}
            onKeyUp={(event) => {
              if (
                [
                  "ArrowLeft",
                  "ArrowRight",
                  "Home",
                  "End",
                  "ArrowUp",
                  "ArrowDown",
                ].includes(event.key)
              )
                commit(event.currentTarget.valueAsNumber);
            }}
          />
          <span>{formatTime(duration)}</span>
        </div>
        <div
          className={`player-status ${p.status === "error" ? "is-error" : ""}`}
          role="status"
          aria-live="polite"
        >
          {p.status === "error" && <CircleAlert size={12} />}
          {p.message}
          {p.waitPosition > 0 && ` · Posición FIFO: ${p.waitPosition}`}
        </div>
      </div>
      <div className="player-extras">
        <IconButton
          label={p.queueOpen ? "Ocultar cola" : "Mostrar cola"}
          aria-expanded={p.queueOpen}
          onClick={() => player.toggleQueue()}
        >
          <ListMusic size={19} />
        </IconButton>
        <span className="extra-divider" />
        <IconButton
          label={p.volume ? "Silenciar" : "Activar sonido"}
          onClick={() => {
            if (p.volume) {
              unmuted.current = p.volume;
              player.volume(0);
            } else player.volume(unmuted.current);
          }}
        >
          {p.volume ? <Volume2 size={19} /> : <VolumeX size={19} />}
        </IconButton>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={p.volume}
          aria-label="Volumen"
          onChange={(event) => player.volume(event.target.valueAsNumber)}
        />
      </div>
    </footer>
  );
}
