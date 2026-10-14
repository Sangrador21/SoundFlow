from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Song:
    """Representa una canción local dentro de la biblioteca."""

    path: str
    title: str
    artist: str
    duration: float

    @property
    def filename(self) -> str:
        return Path(self.path).name

    @property
    def display_name(self) -> str:
        if self.artist and self.artist.lower() not in {"desconocido", "unknown"}:
            return f"{self.title} — {self.artist}"
        return self.title

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Song":
        return cls(
            path=str(data["path"]),
            title=str(data["title"]),
            artist=str(data["artist"]),
            duration=float(data["duration"]),
        )
