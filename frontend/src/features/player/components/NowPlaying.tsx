import { ArrowDown, Disc3, Radio } from "lucide-react";
import { useSoundFlow } from "../../../app/SoundFlowProvider";
import { Artwork } from "../../../components/ui/Artwork";
import { displayArtist } from "../../../utils/format";

export function NowPlaying() {
  const { playback } = useSoundFlow();
  const playing = playback.status === "playing";
  return (
    <section className="now-playing" aria-label="Canción actual">
      <div className="now-copy">
        <div className="hero-eyebrow">
          <Radio size={13} />
          {playback.current ? "EN REPRODUCCIÓN" : "ENCUENTRA TU RITMO"}
        </div>
        <h1>
          {playback.current?.title || (
            <>
              Tu música,
              <br />
              <span>sin fronteras.</span>
            </>
          )}
        </h1>
        <p>
          {playback.current
            ? displayArtist(playback.current.artist)
            : "Un solo lugar para todas tus canciones. Elige una y deja que suene."}
        </p>
        <div className="hero-tag">
          {playback.server ? (
            <>
              <i className={playing ? "dot dot--green" : "dot dot--lilac"} />
              Audio desde {playback.server}
            </>
          ) : (
            <>
              <Disc3 size={14} />
              Hecho para escuchar
            </>
          )}
        </div>
      </div>
      <div className="hero-art">
        <div className="orbit orbit--one" />
        <div className="orbit orbit--two" />
        <Artwork id={playback.current?.id} large spinning={playing} />
        <span className="floating-note">
          <ArrowDown size={13} />
          Dale play a tu día
        </span>
      </div>
    </section>
  );
}
