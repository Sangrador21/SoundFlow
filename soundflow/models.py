from __future__ import annotations
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Song:
    path: str
    title: str
    artist: str
    duration: float
    id: str = ''
    servers: list[str] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return Path(self.path).name

    @property
    def display_name(self) -> str:
        if self.artist and self.artist.lower() not in {'desconocido', 'unknown'}:
            return f'{self.title} — {self.artist}'
        return self.title

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Song':
        return cls(path=str(data.get('filename', data.get('path', 'audio'))),
                   title=str(data['title']), artist=str(data.get('artist', 'Desconocido')),
                   duration=float(data.get('duration', 0)), id=str(data.get('id', '')),
                   servers=list(data.get('servers', [])))
