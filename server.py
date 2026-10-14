from __future__ import annotations

import argparse
from pathlib import Path

from soundflow.server_core import SoundFlowServer


def parse_peer(value: str) -> tuple[str, int]:
    value = value.strip()
    if ":" not in value:
        raise argparse.ArgumentTypeError("El peer debe escribirse como HOST:PUERTO")
    host, raw_port = value.rsplit(":", 1)
    if not host:
        raise argparse.ArgumentTypeError("El peer necesita una dirección IP o hostname")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("El puerto del peer debe ser numérico") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("El puerto del peer debe estar entre 1 y 65535")
    return host, port


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SoundFlow P4 - Servidor UDP multi-cliente / multi-servidor"
    )
    parser.add_argument("--host", default="0.0.0.0", help="IP de escucha (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Puerto UDP (default: 5000)")
    parser.add_argument("--music", default=None, help="Carpeta de música del servidor")
    parser.add_argument(
        "--max-streams",
        type=int,
        default=8,
        help=(
            "Capacidad local de transferencias simultáneas. No limita el clúster: "
            "el exceso se redistribuye o se coloca en FIFO (default: 8)"
        ),
    )
    parser.add_argument(
        "--server-id",
        default=None,
        help="Identificador legible del servidor, por ejemplo S1 o S2",
    )
    parser.add_argument(
        "--advertise-host",
        default=None,
        help=(
            "IP/hostname que este servidor anunciará a los clientes. "
            "En LAN usa la IP real de la máquina."
        ),
    )
    parser.add_argument(
        "--peer",
        action="append",
        type=parse_peer,
        default=[],
        metavar="HOST:PUERTO",
        help="Servidor par. Puede repetirse varias veces: --peer IP:5001 --peer IP:5002",
    )
    parser.add_argument(
        "--probe-timeout",
        type=float,
        default=0.60,
        help="Tiempo para recopilar respuestas de capacidad de los peers (default: 0.60 s)",
    )
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent
    music_dir = Path(args.music).expanduser().resolve() if args.music else root_dir / "music"

    server = SoundFlowServer(
        args.host,
        args.port,
        music_dir,
        max_streams=args.max_streams,
        server_id=args.server_id,
        advertise_host=args.advertise_host,
        peers=args.peer,
        probe_timeout=args.probe_timeout,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
