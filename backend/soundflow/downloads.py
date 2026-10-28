"""Copias comprimidas completas para las canciones recientes de la PWA.

Reutiliza una reserva normal: respeta los mismos nodos, recursos y cancelación.
No publica rutas de disco ni crea un segundo catálogo.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import subprocess
import tempfile
import time
from typing import TYPE_CHECKING

from flask import Response, jsonify
from mutagen import File as MutagenFile

if TYPE_CHECKING:
    from .server_core import SoundFlowServer

MAX_DOWNLOAD_BYTES = 24 * 1024 * 1024
log = logging.getLogger('soundflow.downloads')


def download_response(server: SoundFlowServer, stream_id: str):
    with server.lock:
        session = server.sessions.get(stream_id)
        if session is None:
            return jsonify(error='Sesión desconocida.'), 404
        if session.state != 'reserved':
            return jsonify(error='La sesión ya se usó, canceló o expiró.'), 410
        if session.start != 0:
            return jsonify(error='La copia sin conexión requiere una reserva desde el inicio.'), 400
        song = server.library.get(session.song_id)
        if song is None:
            return jsonify(error='La canción ya no está disponible.'), 404
        session.state = 'streaming'

    temporary = None
    handle = None
    process = None
    completed = False
    closed = False

    def cleanup():
        nonlocal closed
        if closed:
            return
        closed = True
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait()
                except OSError:
                    pass
        if handle:
            handle.close()
        if temporary:
            temporary.cleanup()
        with server.lock:
            if session.state == 'streaming':
                session.state = 'completed' if completed else 'failed'
            session.finished = time.monotonic()
        server.wake.set()

    try:
        path = Path(song.path)
        if path.suffix.lower() != '.mp3':
            temporary = tempfile.TemporaryDirectory(prefix='soundflow-mp3-')
            output = Path(temporary.name) / 'audio.mp3'
            # Límite de salida y tiempo para que la copia local tenga un coste acotado.
            args = [server.ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-i', str(path), '-vn', '-ac', '2', '-ar', '44100',
                    '-c:a', 'libmp3lame', '-b:a', '128k', '-fs', str(MAX_DOWNLOAD_BYTES + 1), str(output)]
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors)
                with server.lock:
                    session.process = process
                    if session.cancelled.is_set():
                        process.terminate()
                code = process.wait(timeout=60)
                if code:
                    raise RuntimeError('No se pudo preparar la copia MP3.')
            path = output
            encoded = MutagenFile(path)
            if not encoded or float(encoded.info.length) + 0.2 < song.duration:
                cleanup()
                return jsonify(error='La copia excede el tamaño disponible o no pudo completarse.'), 413
        handle = path.open('rb')
        size = path.stat().st_size
        if not size or size > MAX_DOWNLOAD_BYTES:
            cleanup()
            return jsonify(error='La copia supera el tamaño permitido de 24 MiB.'), 413
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(128 * 1024), b''):
            digest.update(chunk)
        handle.seek(0)
        if session.cancelled.is_set():
            cleanup()
            return jsonify(error='Descarga cancelada.'), 410
    except (OSError, RuntimeError, subprocess.SubprocessError):
        log.exception('No se pudo preparar la descarga %s', stream_id[:8])
        cleanup()
        return jsonify(error='No se pudo preparar la copia sin conexión.'), 503

    def generate():
        nonlocal completed
        count = 0
        try:
            while not session.cancelled.is_set():
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                yield chunk
            completed = not session.cancelled.is_set() and count == size
        finally:
            cleanup()

    response = Response(generate(), mimetype='audio/mpeg', headers={
        'Content-Length': str(size), 'Cache-Control': 'no-store',
        'X-Download-SHA256': digest.hexdigest(), 'X-Download-Bytes': str(size),
        'X-Server-ID': server.server_id, 'X-Accel-Buffering': 'no',
    })
    response.call_on_close(cleanup)
    return response
