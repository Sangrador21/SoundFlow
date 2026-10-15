from __future__ import annotations
import hashlib
import threading
from pathlib import Path
from mutagen import File as MutagenFile
from .models import Song

SUPPORTED_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac'}


class MusicLibrary:
    """Catálogo local. El hash del contenido identifica la misma canción en otros nodos."""
    def __init__(self, music_dir: Path) -> None:
        self.music_dir = Path(music_dir).resolve()
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._files: dict[str, tuple[tuple[int, int], Song]] = {}
        self._by_id: dict[str, Song] = {}

    def scan(self) -> list[Song]:
        with self._lock:
            files: dict[str, tuple[tuple[int, int], Song]] = {}
            for path in sorted(self.music_dir.iterdir()):
                if path.is_symlink() or not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                try:
                    stat = path.stat()
                    stamp = (stat.st_size, stat.st_mtime_ns)
                    cached = self._files.get(str(path))
                    if cached and cached[0] == stamp:
                        files[str(path)] = cached
                        continue
                    digest = hashlib.sha256()
                    with path.open('rb') as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                            digest.update(chunk)
                    title, artist, duration = path.stem, 'Desconocido', 0.0
                    try:
                        audio = MutagenFile(path, easy=True)
                        if audio is not None:
                            duration = float(getattr(audio.info, 'length', 0) or 0)
                            if audio.tags:
                                title = str(audio.tags.get('title', [title])[0])
                                artist = str(audio.tags.get('artist', [artist])[0])
                    except Exception:
                        pass
                    song = Song(str(path), title, artist, duration, digest.hexdigest())
                    files[str(path)] = (stamp, song)
                except OSError:
                    continue
            self._files = files
            self._by_id = {song.id: song for _, song in files.values()}
            return list(self._by_id.values())

    def all(self) -> list[Song]:
        return self.scan()

    def get(self, song_id: str) -> Song | None:
        self.scan()
        with self._lock:
            return self._by_id.get(song_id)

    def public_catalog(self) -> list[dict]:
        return [{'id': song.id, 'filename': song.filename, 'path': song.filename,
                 'title': song.title, 'artist': song.artist, 'duration': song.duration}
                for song in self.scan()]

    def search(self, query: str) -> list[Song]:
        value = query.strip().casefold()
        return [song for song in self.scan() if not value or value in
                f'{song.title} {song.artist} {song.filename}'.casefold()]
