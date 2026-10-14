from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path

from soundflow.app import SoundFlowApp


def main() -> None:
    mp.freeze_support()
    parser = argparse.ArgumentParser(description="SoundFlow P4 - Cliente UDP multi-servidor")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="IP del servidor de entrada (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Puerto UDP del servidor de entrada (default: 5000)",
    )
    args = parser.parse_args()

    ctx = mp.get_context("spawn")
    root_dir = Path(__file__).resolve().parent
    cache_dir = root_dir / ".stream_cache"

    app = SoundFlowApp(
        server_host=args.host,
        server_port=args.port,
        cache_dir=cache_dir,
        mp_context=ctx,
    )
    app.run()


if __name__ == "__main__":
    main()
