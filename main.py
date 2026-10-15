from __future__ import annotations
import argparse
import multiprocessing as mp
from pathlib import Path
import uuid
from soundflow.app import SoundFlowApp


def main() -> None:
    mp.freeze_support()
    parser = argparse.ArgumentParser(description='SoundFlow P06 — Cliente de streaming HTTP/HTTPS')
    parser.add_argument('--server', default='http://127.0.0.1:5000', help='URL base del servidor de entrada')
    parser.add_argument('--fallback', action='append', default=[], help='URL alternativa si el servidor de entrada cae')
    parser.add_argument('--ca', help='CA/certificado PEM para verificar HTTPS local')
    args = parser.parse_args()
    cache = Path(__file__).resolve().parent / '.stream_cache' / uuid.uuid4().hex
    app = SoundFlowApp(args.server, cache, mp.get_context('spawn'),
                       verify=args.ca or True, fallbacks=args.fallback)
    app.run()


if __name__ == '__main__':
    main()
