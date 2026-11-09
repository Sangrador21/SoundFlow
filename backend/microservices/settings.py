"""Configuración por proceso. Las direcciones internas nunca se compilan en la PWA."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re

from dotenv import load_dotenv
from soundflow.http_utils import normalize_url

ROOT = Path(__file__).resolve().parents[2]


def positive(name, default, maximum=None):
    value = float(os.getenv(name, str(default)))
    if not math.isfinite(value) or value <= 0 or maximum is not None and value > maximum:
        raise ValueError(f'{name} tiene un valor inválido.')
    return value


@dataclass(frozen=True)
class ServiceSettings:
    role: str
    token: str
    base_url: str
    nodes: dict
    catalog_url: str
    playback_url: str
    origins: list
    node_id: str
    music: Path
    database: str
    timeout: float
    wait_timeout: float
    cpu: float
    memory: float
    maintenance: bool
    verify: bool | str

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / 'backend' / '.env', override=False)
        role = os.getenv('SOUNDFLOW_SERVICE', '')
        if role not in {'gateway', 'catalog', 'playback', 'media'}:
            raise ValueError('SOUNDFLOW_SERVICE debe ser gateway, catalog, playback o media.')
        token = os.getenv('SOUNDFLOW_CLUSTER_TOKEN', '')
        if not token.strip():
            raise ValueError('Configura SOUNDFLOW_CLUSTER_TOKEN; no se envía al navegador.')
        raw = json.loads(os.getenv('SOUNDFLOW_MEDIA_NODES', '{}'))
        if not isinstance(raw, dict) or any(not isinstance(k, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', k)
                                           or not isinstance(v, str) for k, v in raw.items()):
            raise ValueError('SOUNDFLOW_MEDIA_NODES debe ser un objeto JSON de identificadores y URL.')
        nodes = {key: normalize_url(url) for key, url in raw.items()}
        if role in {'catalog', 'playback'} and not 1 <= len(nodes) <= 16:
            raise ValueError('Configura de 1 a 16 nodos en SOUNDFLOW_MEDIA_NODES.')
        origins = [x.strip().rstrip('/') for x in os.getenv('SOUNDFLOW_CORS_ORIGINS',
                    'http://localhost:5173,http://127.0.0.1:5173').split(',') if x.strip()]
        if not origins or '*' in origins:
            raise ValueError('Configura orígenes CORS explícitos.')
        for origin in origins:
            normalize_url(origin)
        node_id = os.getenv('SOUNDFLOW_NODE_ID', 'S1')
        music = Path(os.getenv('SOUNDFLOW_MUSIC_DIR', str(ROOT / '.local_music' / node_id))).resolve()
        base = os.getenv('SOUNDFLOW_BASE_URL') or os.getenv('RENDER_EXTERNAL_URL') or 'http://127.0.0.1:8000'
        return cls(role, token, normalize_url(base), nodes,
                   normalize_url(os.getenv('SOUNDFLOW_CATALOG_URL', 'http://127.0.0.1:8001')),
                   normalize_url(os.getenv('SOUNDFLOW_PLAYBACK_URL', 'http://127.0.0.1:8002')),
                   origins, node_id, music, os.getenv('SOUNDFLOW_TICKETS_DB', str(ROOT / '.state/playback.sqlite3')),
                   positive('SOUNDFLOW_RPC_TIMEOUT', 10), positive('SOUNDFLOW_WAIT_TIMEOUT', 120),
                   positive('SOUNDFLOW_CPU_THRESHOLD', 95, 100), positive('SOUNDFLOW_MEMORY_THRESHOLD', 95, 100),
                   os.getenv('SOUNDFLOW_MAINTENANCE', '').lower() in {'true', 'yes', '1'},
                   os.getenv('SOUNDFLOW_CA') or True)


def create_service(config=None):
    from .common import Rpc
    config = config or ServiceSettings.from_env()
    rpc = Rpc(config.token, config.timeout, config.verify)
    if config.role == 'media':
        from .media import MediaService
        return MediaService(config.music, config.base_url, server_id=config.node_id, token=config.token,
                            origins=config.origins, cpu_threshold=config.cpu, memory_threshold=config.memory,
                            maintenance=config.maintenance)
    if config.role == 'catalog':
        from .catalog import CatalogService
        return CatalogService(config.nodes, rpc)
    if config.role == 'playback':
        from .playback import PlaybackService
        return PlaybackService(config.catalog_url, config.nodes, rpc, config.database, wait_timeout=config.wait_timeout)
    from .gateway import GatewayService
    return GatewayService(config.catalog_url, config.playback_url, rpc, config.base_url, config.origins)
