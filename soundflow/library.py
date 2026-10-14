from __future__ import annotations

from pathlib import Path
import threading

from mutagen import File as MutagenFile

from .models import Song


SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac"}


class MusicLibrary:
    """
    Biblioteca musical compartida por el hilo principal (GUI) y el hilo
    de búsqueda.

    Se protege con RLock para evitar condiciones de carrera mientras se
    recarga el catálogo y, al mismo tiempo, otro hilo realiza una búsqueda.
    """

    def __init__(self, music_dir: Path) -> None:
        self.music_dir = Path(music_dir)
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self._songs: list[Song] = []
        self._lock = threading.RLock()

    def scan(self) -> list[Song]:
        songs: list[Song] = []

        for path in sorted(self.music_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            title = path.stem
            artist = "Desconocido"
            duration = 0.0

            try:
                audio = MutagenFile(path, easy=True)
                if audio is not None:
                    if getattr(audio, "info", None) is not None:
                        duration = float(getattr(audio.info, "length", 0.0) or 0.0)

                    tags = getattr(audio, "tags", None)
                    if tags:
                        title_values = tags.get("title")
                        artist_values = tags.get("artist")

                        if title_values:
                            title = str(title_values[0])
                        if artist_values:
                            artist = str(artist_values[0])
            except Exception:
                # Un archivo puede reproducirse aunque no tenga metadatos legibles; en ese caso usamos el nombre del archivo.
                pass

            songs.append(
                Song(
                    path=str(path.resolve()),
                    title=title,
                    artist=artist,
                    duration=duration,
                )
            )

        with self._lock:
            self._songs = songs
            return list(self._songs)

    def all(self) -> list[Song]:
        with self._lock:
            return list(self._songs)

    def search(self, query: str) -> list[Song]:
        normalized = query.strip().casefold()

        with self._lock:
            snapshot = list(self._songs)

        if not normalized:
            return snapshot

        return [
            song
            for song in snapshot
            if normalized in song.title.casefold()
            or normalized in song.artist.casefold()
            or normalized in song.filename.casefold()
        ]
