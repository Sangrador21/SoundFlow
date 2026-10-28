import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Clock3, ListPlus, Music2, Play, Search, X } from "lucide-react";
import { useSoundFlow } from "../../app/SoundFlowProvider";
import type { Song } from "../../types/api";
import { Artwork } from "../../components/ui/Artwork";
import { Button, IconButton } from "../../components/ui/Button";
import { displayArtist, formatTime } from "../../utils/format";
import { useOnline } from "../../pwa/network";

export function CatalogTable({
  songs,
  loading,
}: {
  songs: Song[];
  loading: boolean;
}) {
  const { player, playback, offline } = useSoundFlow();
  const online = useOnline();
  const [query, setQuery] = useState("");
  const [server, setServer] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const all = useRef<HTMLInputElement>(null);
  const filtered = useMemo(
    () =>
      songs.filter(
        (song) =>
          (!server || song.servers.includes(server)) &&
          `${song.title} ${song.artist} ${song.filename}`
            .toLocaleLowerCase("es")
            .includes(query.trim().toLocaleLowerCase("es")),
      ),
    [songs, query, server],
  );
  const selectedSongs = songs.filter(
    (song) => selected.has(song.id) && (online || offline.has(song.id)),
  );
  const selectedVisible = filtered.filter((song) =>
    selected.has(song.id),
  ).length;
  useEffect(() => {
    if (all.current)
      all.current.indeterminate =
        selectedVisible > 0 && selectedVisible < filtered.length;
  }, [selectedVisible, filtered.length]);
  function toggle(id: string) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  return (
    <section className="library-card card" aria-labelledby="library-heading">
      <div className="library-heading">
        <div>
          <h2 id="library-heading">
            Tu biblioteca <span>{songs.length}</span>
          </h2>
          <p>Encuentra algo que quieras escuchar.</p>
        </div>
        <Button
          variant="soft"
          disabled={!selectedSongs.length}
          onClick={() => {
            player.add(selectedSongs);
            setSelected(new Set());
          }}
        >
          <ListPlus size={17} />
          <span>Agregar a cola</span>
          {selectedSongs.length > 0 && <b>{selectedSongs.length}</b>}
        </Button>
      </div>
      <div className="library-filters">
        <label className="search-field">
          <Search size={18} />
          <input
            type="search"
            placeholder="Buscar canciones o artistas…"
            aria-label="Buscar canciones o artistas"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query && (
            <IconButton label="Limpiar búsqueda" onClick={() => setQuery("")}>
              <X size={14} />
            </IconButton>
          )}
        </label>
        <select
          aria-label="Filtrar por servidor"
          value={server}
          onChange={(event) => setServer(event.target.value)}
        >
          <option value="">Todos los servidores</option>
          {[...new Set(songs.flatMap((song) => song.servers))]
            .sort()
            .map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
        </select>
      </div>
      {loading && !songs.length ? (
        <div
          className="catalog-skeleton"
          role="status"
          aria-label="Cargando biblioteca"
        >
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i}>
              <i />
              <span />
              <b />
            </div>
          ))}
        </div>
      ) : filtered.length ? (
        <div className="table-scroll">
          <table className="song-table">
            <thead>
              <tr>
                <th className="checkbox-cell">
                  <input
                    ref={all}
                    type="checkbox"
                    aria-label="Seleccionar todas las canciones visibles"
                    checked={
                      filtered.length > 0 && selectedVisible === filtered.length
                    }
                    onChange={(event) =>
                      setSelected((previous) => {
                        const next = new Set(previous);
                        filtered.forEach((song) =>
                          event.target.checked
                            ? next.add(song.id)
                            : next.delete(song.id),
                        );
                        return next;
                      })
                    }
                  />
                </th>
                <th className="number-cell">#</th>
                <th>Canción</th>
                <th className="artist-cell">Artista</th>
                <th className="sources-cell">Disponible en</th>
                <th className="duration-cell">
                  <Clock3 size={15} aria-label="Duración" />
                </th>
                <th className="action-cell">
                  <span className="sr-only">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((song, index) => {
                const current = playback.current?.id === song.id;
                return (
                  <tr
                    key={song.id}
                    className={`${current ? "is-current" : ""} ${selected.has(song.id) ? "is-selected" : ""}`}
                  >
                    <td className="checkbox-cell">
                      <input
                        type="checkbox"
                        aria-label={`Seleccionar ${song.title}`}
                        checked={selected.has(song.id)}
                        onChange={() => toggle(song.id)}
                      />
                    </td>
                    <td className="number-cell">
                      <span
                        className={
                          current && playback.status === "playing"
                            ? "mini-equalizer"
                            : ""
                        }
                      >
                        {current && playback.status === "playing" ? (
                          <>
                            <i />
                            <i />
                            <i />
                          </>
                        ) : (
                          index + 1
                        )}
                      </span>
                    </td>
                    <td>
                      <button
                        className="song-name"
                        disabled={!online && !offline.has(song.id)}
                        onClick={() => player.play(song)}
                        aria-label={`Reproducir ${song.title}`}
                      >
                        <span className="song-art">
                          <Artwork id={song.id} />
                          <span className="song-play">
                            <Play size={15} fill="currentColor" />
                          </span>
                        </span>
                        <span>
                          <strong>{song.title}</strong>
                          <small>{displayArtist(song.artist)}</small>
                        </span>
                      </button>
                    </td>
                    <td className="artist-cell">
                      <span className="artist-text">
                        {displayArtist(song.artist)}
                      </span>
                    </td>
                    <td className="sources-cell">
                      <div className="source-list">
                        {song.servers.map((id) => (
                          <span
                            className={`source-badge ${!song.available ? "is-unavailable" : ""}`}
                            key={id}
                          >
                            <i />
                            {id}
                          </span>
                        ))}
                        {offline.has(song.id) && (
                          <span className="offline-source">Guardada</span>
                        )}
                      </div>
                    </td>
                    <td className="duration-cell">
                      {formatTime(song.duration)}
                    </td>
                    <td className="action-cell">
                      <IconButton
                        label={`Agregar ${song.title} a la cola`}
                        disabled={!online && !offline.has(song.id)}
                        onClick={() => player.add([song])}
                      >
                        <ListPlus size={18} />
                      </IconButton>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="library-empty">
          <span>
            <Music2 size={31} strokeWidth={1.4} />
          </span>
          <h3>
            {songs.length
              ? "No encontramos esa canción"
              : "Tu biblioteca está esperando"}
          </h3>
          <p>
            {songs.length
              ? "Prueba con otro título, artista o servidor."
              : "Conecta tus servidores y agrega archivos a sus bibliotecas para comenzar."}
          </p>
          {(query || server) && (
            <Button
              variant="ghost"
              onClick={() => {
                setQuery("");
                setServer("");
              }}
            >
              Limpiar filtros
            </Button>
          )}
        </div>
      )}
      <div className="library-footer">
        {selectedSongs.length ? (
          <>
            <Check size={13} />
            {selectedSongs.length} canción
            {selectedSongs.length === 1 ? "" : "es"} seleccionada
            {selectedSongs.length === 1 ? "" : "s"}
          </>
        ) : (
          <>
            Selecciona una canción para reproducirla. Usa las casillas para
            preparar tu cola.
          </>
        )}
      </div>
    </section>
  );
}
