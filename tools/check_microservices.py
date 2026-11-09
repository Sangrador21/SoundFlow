"""P08: prueba el cliente real contra gateway, catálogo, reproducción y dos medios Gunicorn."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    npm = shutil.which('npm')
    if not npm:
        raise SystemExit('Instala Node.js y ejecuta npm ci dentro de frontend antes de esta prueba.')
    subprocess.run([sys.executable, 'tools/build_catalog.py'], cwd=PROJECT_ROOT, check=True)
    sockets = [socket.socket() for _ in range(5)]
    for handle in sockets:
        handle.bind(('127.0.0.1', 0))
    ports = [handle.getsockname()[1] for handle in sockets]
    for handle in sockets:
        handle.close()
    urls = [f'http://127.0.0.1:{port}' for port in ports]
    processes = []
    with tempfile.TemporaryDirectory(prefix='soundflow-p08-') as directory, tempfile.TemporaryFile() as log:
        state = Path(directory)
        try:
            import json
            for i, role in enumerate(['media', 'media', 'catalog', 'playback', 'gateway']):
                env = {**os.environ, 'PORT': str(ports[i]), 'SOUNDFLOW_SERVICE': role,
                       'SOUNDFLOW_BASE_URL': urls[i],
                       'SOUNDFLOW_MEDIA_NODES': json.dumps({'S1': urls[0], 'S2': urls[1]}),
                       'SOUNDFLOW_CATALOG_URL': urls[2], 'SOUNDFLOW_PLAYBACK_URL': urls[3],
                       'SOUNDFLOW_RPC_TIMEOUT': '2', 'SOUNDFLOW_TICKETS_DB': str(state / 'tickets.sqlite3'),
                       'SOUNDFLOW_CPU_THRESHOLD': '100', 'SOUNDFLOW_MEMORY_THRESHOLD': '100',
                       'SOUNDFLOW_CLUSTER_TOKEN': 'integration-only-token',
                       'SOUNDFLOW_CORS_ORIGINS': 'http://localhost:5173'}
                if role == 'media':
                    env.update(SOUNDFLOW_NODE_ID=f'S{i+1}',
                               SOUNDFLOW_MUSIC_DIR=str(PROJECT_ROOT / '.local_music' / f'S{i+1}'))
                processes.append(subprocess.Popen([sys.executable, '-m', 'gunicorn', '--chdir', 'backend',
                    '--config', str(PROJECT_ROOT / 'backend/gunicorn.conf.py'), 'microservices.wsgi:app'],
                    cwd=PROJECT_ROOT, env=env, stdout=log, stderr=log))
            deadline = time.monotonic() + 20
            for url in urls:
                while True:
                    try:
                        requests.get(url + '/api/health', timeout=1).raise_for_status()
                        break
                    except requests.RequestException:
                        if time.monotonic() > deadline:
                            raise RuntimeError('No iniciaron los procesos de prueba.')
                        time.sleep(0.1)
            subprocess.run([npm, 'test', '--', 'src/test/live-cluster.test.ts', 'src/test/live-microservices.test.ts'],
                cwd=PROJECT_ROOT / 'frontend', env={**os.environ, 'SOUNDFLOW_LIVE_URLS': ','.join([urls[4], urls[4]]), 'SOUNDFLOW_GATEWAY_URL': urls[4]}, check=True)
            print('Integración P08 + cinco procesos Gunicorn: OK')
        except Exception:
            log.seek(0)
            print(log.read().decode(errors='replace')[-6000:])
            raise
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    main()
