"""Inicia cinco procesos locales, prepara S1/S2 y los detiene juntos con Ctrl+C."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway-port', type=int, default=8000)
    parser.add_argument('--catalog-port', type=int, default=8001)
    parser.add_argument('--playback-port', type=int, default=8002)
    parser.add_argument('--s1-port', type=int, default=5000)
    parser.add_argument('--s2-port', type=int, default=5001)
    args = parser.parse_args()
    ports = [args.s1_port, args.s2_port, args.catalog_port, args.playback_port, args.gateway_port]
    if len(set(ports)) != 5 or any(not 1 <= p <= 65535 for p in ports):
        parser.error('Configura cinco puertos distintos entre 1 y 65535.')
    handles = []
    try:
        for port in ports:
            handle = socket.socket()
            handles.append(handle)
            handle.bind(('127.0.0.1', port))
    except OSError as exc:
        parser.error(f'Un puerto está ocupado. Detén los servidores P07 antes de iniciar: {exc}')
    finally:
        for handle in handles:
            handle.close()
    subprocess.run([sys.executable, 'tools/build_catalog.py'], cwd=ROOT, check=True)
    urls = [f'http://127.0.0.1:{port}' for port in ports]
    token = os.getenv('SOUNDFLOW_CLUSTER_TOKEN') or secrets.token_urlsafe(32)
    base_env = {**os.environ, 'SOUNDFLOW_CLUSTER_TOKEN': token,
                'SOUNDFLOW_MEDIA_NODES': json.dumps({'S1': urls[0], 'S2': urls[1]}),
                'SOUNDFLOW_CATALOG_URL': urls[2], 'SOUNDFLOW_PLAYBACK_URL': urls[3],
                'SOUNDFLOW_RPC_TIMEOUT': '3',
                'SOUNDFLOW_CORS_ORIGINS': 'http://localhost:5173,http://127.0.0.1:5173'}
    processes = []
    try:
        for index, role in enumerate(['media', 'media', 'catalog', 'playback', 'gateway']):
            env = {**base_env, 'SOUNDFLOW_BASE_URL': urls[index]}
            if role == 'media':
                env.update(SOUNDFLOW_NODE_ID=f'S{index+1}', SOUNDFLOW_MUSIC_DIR=str(ROOT / '.local_music' / f'S{index+1}'))
            processes.append(subprocess.Popen([sys.executable, 'backend/service.py', '--service', role,
                                               '--port', str(ports[index])], cwd=ROOT, env=env))
        deadline = time.monotonic() + 30
        for url in urls:
            while True:
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError('Un microservicio terminó; revisa la salida anterior.')
                try:
                    with urllib.request.urlopen(url + '/api/health', timeout=1) as response:
                        if json.load(response).get('version') == '0.8.0':
                            break
                except (OSError, ValueError):
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError('Los microservicios no iniciaron dentro del plazo.')
                time.sleep(0.1)
        print(f'\nSoundFlow P08 listo. Configura SOLO el gateway: {urls[4]}', flush=True)
        print('Diagnóstico: ' + urls[4] + '/api/services\nCtrl+C detiene los cinco procesos.', flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
