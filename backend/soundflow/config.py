"""Configuración común del servidor local y del proceso WSGI de Render."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path

from dotenv import load_dotenv

from .http_utils import normalize_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / 'backend' / '.env', override=False)


def number(name: str, default: float, *, maximum: float | None = None) -> float:
    value = float(os.getenv(name, str(default)))
    if not math.isfinite(value) or value <= 0 or (maximum is not None and value > maximum):
        raise ValueError(f'{name} tiene un valor inválido.')
    return value


@dataclass(frozen=True)
class Settings:
    server_id: str
    base_url: str
    music_dir: Path
    peers: list[str]
    allowed_origins: list[str]
    cpu_threshold: float
    memory_threshold: float
    wait_timeout: float
    peer_timeout: float
    maintenance: bool
    cluster_token: str
    ca: str | bool

    @classmethod
    def from_env(cls) -> 'Settings':
        server_id = os.getenv('SOUNDFLOW_NODE_ID', 'S1')
        base = os.getenv('SOUNDFLOW_BASE_URL') or os.getenv('RENDER_EXTERNAL_URL') or 'http://127.0.0.1:5000'
        music = Path(os.getenv('SOUNDFLOW_MUSIC_DIR', str(PROJECT_ROOT / '.local_music' / server_id)))
        if not music.is_absolute():
            music = PROJECT_ROOT / music
        origins = [x.strip().rstrip('/') for x in os.getenv(
            'SOUNDFLOW_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if x.strip()]
        if not origins or '*' in origins:
            raise ValueError('Configura orígenes CORS explícitos; no se admite *.')
        for origin in origins:
            normalize_url(origin)
        return cls(
            server_id=server_id, base_url=normalize_url(base), music_dir=music,
            peers=[normalize_url(p.strip()) for p in os.getenv('SOUNDFLOW_PEERS', '').split(',') if p.strip()],
            allowed_origins=origins,
            cpu_threshold=number('SOUNDFLOW_CPU_THRESHOLD', 95, maximum=100),
            memory_threshold=number('SOUNDFLOW_MEMORY_THRESHOLD', 95, maximum=100),
            wait_timeout=number('SOUNDFLOW_WAIT_TIMEOUT', 120),
            peer_timeout=number('SOUNDFLOW_PEER_TIMEOUT', 2),
            maintenance=os.getenv('SOUNDFLOW_MAINTENANCE', '').lower() in {'1', 'true', 'yes'},
            cluster_token=os.getenv('SOUNDFLOW_CLUSTER_TOKEN', ''),
            ca=os.getenv('SOUNDFLOW_CA') or True,
        )
