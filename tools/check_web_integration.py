"""Prueba el cliente TypeScript contra dos procesos Gunicorn locales reales."""
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
    sockets = [socket.socket(), socket.socket()]
    for handle in sockets:
        handle.bind(('127.0.0.1', 0))
    ports = [handle.getsockname()[1] for handle in sockets]
    for handle in sockets:
        handle.close()
    urls = [f'http://127.0.0.1:{port}' for port in ports]
    processes = []
    with tempfile.TemporaryFile() as log:
        try:
            for i, node in enumerate(['S1', 'S2']):
                env = {**os.environ, 'PORT': str(ports[i]), 'SOUNDFLOW_NODE_ID': node,
                       'SOUNDFLOW_MUSIC_DIR': str(PROJECT_ROOT / '.local_music' / node),
                       'SOUNDFLOW_BASE_URL': urls[i], 'SOUNDFLOW_PEERS': urls[1-i],
                       'SOUNDFLOW_CPU_THRESHOLD': '100', 'SOUNDFLOW_MEMORY_THRESHOLD': '100',
                       'SOUNDFLOW_CLUSTER_TOKEN': 'integration-only-token',
                       'SOUNDFLOW_CORS_ORIGINS': 'http://localhost:5173'}
                processes.append(subprocess.Popen([sys.executable, '-m', 'gunicorn', '--chdir', 'backend',
                    '--config', str(PROJECT_ROOT / 'backend/gunicorn.conf.py'), 'wsgi:app'], cwd=PROJECT_ROOT, env=env, stdout=log, stderr=log))
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
            subprocess.run([npm, 'test', '--', 'src/test/live-cluster.test.ts'],
                cwd=PROJECT_ROOT / 'frontend', env={**os.environ, 'SOUNDFLOW_LIVE_URLS': ','.join(urls)}, check=True)
            print('Integración web + dos nodos Gunicorn: OK')
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
