"""Entrada local de un microservicio. El lanzador tools/run_microservices.py inicia los cinco."""
import argparse
import logging
import os

from microservices.settings import create_service


def main():
    parser = argparse.ArgumentParser(description='SoundFlow P08 — microservicios')
    parser.add_argument('--service', choices=['gateway', 'catalog', 'playback', 'media'], required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--cert')
    parser.add_argument('--key')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or bool(args.cert) != bool(args.key):
        parser.error('Revisa puerto, --cert y --key.')
    os.environ['SOUNDFLOW_SERVICE'] = args.service
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    try:
        service = create_service()
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    try:
        service.app.run(host=args.host, port=args.port, threaded=True, use_reloader=False,
                        ssl_context=(args.cert, args.key) if args.cert else None)
    finally:
        service.close()


if __name__ == '__main__':
    main()
