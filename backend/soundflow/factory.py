from __future__ import annotations

from .config import Settings
from .server_core import SoundFlowServer


def create_server(settings: Settings | None = None) -> SoundFlowServer:
    config = settings or Settings.from_env()
    return SoundFlowServer(
        config.music_dir, config.base_url, server_id=config.server_id,
        peers=config.peers, verify=config.ca, allowed_origins=config.allowed_origins,
        cpu_threshold=config.cpu_threshold, memory_threshold=config.memory_threshold,
        wait_timeout=config.wait_timeout, peer_timeout=config.peer_timeout,
        maintenance=config.maintenance, cluster_token=config.cluster_token,
    )
