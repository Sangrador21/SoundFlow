from __future__ import annotations
import argparse
import logging
import os
from pathlib import Path
from soundflow.server_core import SoundFlowServer
from soundflow.http_utils import normalize_url
from soundflow.config import Settings


def main() -> None:
    config = Settings.from_env()
    parser = argparse.ArgumentParser(description='SoundFlow P06 — API REST HTTP/HTTPS')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '5000')))
    parser.add_argument('--server-id', default=config.server_id)
    parser.add_argument('--music', default=str(config.music_dir))
    parser.add_argument('--base-url', help='URL alcanzable por los clientes y los otros nodos')
    parser.add_argument('--peer', action='append', default=None, help='URL base de un nodo; se puede repetir')
    parser.add_argument('--cpu-threshold', type=float, default=config.cpu_threshold)
    parser.add_argument('--memory-threshold', type=float, default=config.memory_threshold)
    parser.add_argument('--wait-timeout', type=float, default=config.wait_timeout)
    parser.add_argument('--peer-timeout', type=float, default=config.peer_timeout)
    parser.add_argument('--maintenance', action='store_true', default=config.maintenance, help='No atiende audio localmente, pero coordina solicitudes')
    parser.add_argument('--cert', help='Certificado PEM para servir HTTPS local')
    parser.add_argument('--key', help='Clave PEM del certificado')
    parser.add_argument('--ca', default=config.ca, help='CA/certificado PEM para verificar HTTPS de los pares')
    args = parser.parse_args()
    if bool(args.cert) != bool(args.key):
        parser.error('--cert y --key deben utilizarse juntos')
    if not (0 < args.cpu_threshold <= 100 and 0 < args.memory_threshold <= 100):
        parser.error('Los umbrales deben estar entre 0 y 100')
    if not 1 <= args.port <= 65535 or args.wait_timeout <= 0 or args.peer_timeout <= 0:
        parser.error('Puerto o tiempo de espera inválido')
    scheme = 'https' if args.cert else 'http'
    advertised = args.host if args.host not in {'0.0.0.0', '::'} else '127.0.0.1'
    try:
        base_url = normalize_url(args.base_url or f'{scheme}://{advertised}:{args.port}')
        server = SoundFlowServer(Path(args.music), base_url, server_id=args.server_id,
                                 peers=args.peer if args.peer is not None else config.peers, verify=args.ca or True,
                                 cpu_threshold=args.cpu_threshold, memory_threshold=args.memory_threshold,
                                 wait_timeout=args.wait_timeout, peer_timeout=args.peer_timeout,
                                 maintenance=args.maintenance, cluster_token=config.cluster_token,
                                 allowed_origins=config.allowed_origins)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    logging.info('SoundFlow P06 [%s] %s · biblioteca=%s · sin máximo fijo de transferencias',
                 args.server_id, base_url, Path(args.music).resolve())
    try:
        server.app.run(host=args.host, port=args.port, threaded=True, debug=False,
                       use_reloader=False, ssl_context=(args.cert, args.key) if args.cert else None)
    finally:
        server.close()


if __name__ == '__main__':
    main()
