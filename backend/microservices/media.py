"""Servicio de medios: biblioteca local, recursos, reservas y bytes de audio."""
from __future__ import annotations
from dataclasses import dataclass, field
import logging
import math
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import uuid

from flask import Response, jsonify, request

from soundflow.audio import SAMPLE_RATE, CHANNELS, BYTES_PER_SECOND, CHUNK_BYTES, ffmpeg_executable
from soundflow.library import MusicLibrary
from soundflow.resources import ResourceMonitor
from soundflow.downloads import download_response
from .common import VERSION, internal, new_app, parse_song

log = logging.getLogger('soundflow.media')

@dataclass
class StreamSession:
    id: str
    song_id: str
    start: float
    created: float = field(default_factory=time.monotonic)
    state: str = 'reserved'
    cancelled: threading.Event = field(default_factory=threading.Event)
    process: subprocess.Popen | None = None
    finished: float = 0.0


class MediaService:
    def __init__(self, music_dir: Path, base_url: str, *, server_id='S1', token,
                 origins=(), cpu_threshold=95, memory_threshold=95, maintenance=False):
        self.base_url, self.server_id = base_url, server_id
        self.ffmpeg = ffmpeg_executable()
        self.library = MusicLibrary(music_dir)
        self.library.scan()
        self.lock = threading.RLock()
        self.sessions = {}
        self.cpu_threshold, self.memory_threshold = cpu_threshold, memory_threshold
        self.maintenance = maintenance
        self.resource_monitor = ResourceMonitor()
        self.cpu_percent = self.memory_percent = 0.0
        self.stop_event, self.wake = threading.Event(), threading.Event()
        self.app = new_app('media', origins)
        protect = internal(token)

        @self.app.get('/api/health')
        def health():
            return jsonify(status='ok', service='media', server_id=self.server_id,
                           version=VERSION, features=['pcm', 'offline-download'], **self.resource_status())

        @self.app.get('/internal/v1/node')
        @protect
        def node():
            return jsonify(server_id=self.server_id, base_url=self.base_url,
                           resources=self.resource_status(), songs=self.library.public_catalog())

        @self.app.post('/internal/v1/streams')
        @protect
        def reserve():
            song, start = parse_song()
            reservation = request.json.get('reservation_id', '')
            if not isinstance(reservation, str) or not re.fullmatch(r'[a-f0-9]{32}', reservation):
                raise ValueError('reservation_id debe ser un UUID hexadecimal.')
            with self.lock:
                previous = self.sessions.get(reservation)
                if previous:
                    if previous.song_id != song or previous.start != round(start*SAMPLE_RATE)/SAMPLE_RATE:
                        return jsonify(error='La reserva pertenece a otra solicitud.'), 409
                    if previous.state != 'reserved':
                        return jsonify(error='La reserva ya no está disponible.'), 410
                    return jsonify(self.assignment(previous)), 201
                data, code = self._reserve(song, start)
                if code == 201:
                    session = self.sessions.pop(data['stream_id'])
                    session.id = reservation
                    self.sessions[reservation] = session
                    data = self.assignment(session)
            return jsonify(data), code

        @self.app.get('/api/streams/<stream_id>/audio')
        def audio(stream_id):
            return self._audio_response(stream_id)

        @self.app.get('/api/streams/<stream_id>/download')
        def download(stream_id):
            return download_response(self, stream_id)

        @self.app.get('/api/streams/<stream_id>')
        def status(stream_id):
            with self.lock:
                session = self.sessions.get(stream_id)
                if not session:
                    return jsonify(error='Sesión desconocida.'), 404
                return jsonify(state=session.state, stream_id=session.id)

        @self.app.delete('/internal/v1/streams/<stream_id>')
        @protect
        def cancel(stream_id):
            self.cancel_session(stream_id)
            return '', 204

        self.worker = threading.Thread(target=self._maintenance_loop, daemon=True, name='media-resources')
        self.worker.start()

    def assignment(self, session):
        song = self.library.get(session.song_id)
        return {'stream_id': session.id, 'server_id': self.server_id,
                'server_url': self.base_url, 'audio_url': self.base_url + f'/api/streams/{session.id}/audio',
                'song_id': song.id, 'start': session.start, 'duration': song.duration,
                'sample_rate': SAMPLE_RATE, 'channels': CHANNELS, 'sample_bytes': 2}

    def _maintenance_loop(self):
        while not self.stop_event.is_set():
            cpu, memory = self.resource_monitor.sample()
            with self.lock:
                self.cpu_percent, self.memory_percent = cpu, memory
                now = time.monotonic()
                for session in self.sessions.values():
                    if session.state == 'reserved' and now - session.created > 30:
                        session.state, session.finished = 'expired', now
                for sid in [sid for sid, s in self.sessions.items() if s.finished and now-s.finished > 120]:
                    del self.sessions[sid]
            self.wake.wait(1)
            self.wake.clear()

    def resource_status(self) -> dict:
        with self.lock:
            active = sum(s.state in {'reserved', 'streaming'} for s in self.sessions.values())
            cpu, memory = self.cpu_percent, self.memory_percent
            accepting = not self.maintenance and cpu < self.cpu_threshold and memory < self.memory_threshold
        return {'accepting': accepting, 'active_streams': active,
                'cpu_percent': round(cpu, 1), 'memory_percent': round(memory, 1),
                'cpu_threshold': self.cpu_threshold, 'memory_threshold': self.memory_threshold,
                'maintenance': self.maintenance}

    def _reserve(self, song_id: str, start: float) -> tuple[dict, int]:
        song = self.library.get(song_id)
        if song is None:
            return {'error': 'Este nodo no tiene la canción.'}, 404
        if song.duration > 0 and start >= song.duration:
            return {'error': 'El segundo solicitado excede la duración.'}, 400
        samples = start * SAMPLE_RATE
        if not math.isfinite(samples) or samples >= 2**63:
            return {'error': 'La posición solicitada está fuera de rango.'}, 400
        start = round(samples) / SAMPLE_RATE
        with self.lock:
            if not self.resource_status()['accepting']:
                return {'error': 'Nodo temporalmente ocupado por recursos o mantenimiento.'}, 503
            session = StreamSession(uuid.uuid4().hex, song_id, start)
            self.sessions[session.id] = session
        result = {'stream_id': session.id, 'server_id': self.server_id, 'server_url': self.base_url,
                  'audio_url': self.base_url + f'/api/streams/{session.id}/audio',
                  'song_id': song_id, 'start': start, 'duration': song.duration,
                  'sample_rate': SAMPLE_RATE, 'channels': CHANNELS, 'sample_bytes': 2}
        log.info('RESERVA %s canción=%s inicio=%.2fs nodo=%s', session.id[:8], song.title, start, self.server_id)
        return result, 201

    def cancel_session(self, stream_id: str) -> None:
        with self.lock:
            session = self.sessions.get(stream_id)
            if session is None:
                return
            if session.state not in {'reserved', 'streaming'}:
                return
            session.cancelled.set()
            session.state, session.finished = 'cancelled', time.monotonic()
            process = session.process
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        self.wake.set()

    def _audio_response(self, stream_id: str) -> Response | tuple:
        with self.lock:
            session = self.sessions.get(stream_id)
            if session is None:
                return jsonify(error='Sesión desconocida.'), 404
            if session.state != 'reserved':
                return jsonify(error='La sesión ya se usó, canceló o expiró.'), 410
            song = self.library.get(session.song_id)
            if song is None:
                session.state, session.finished = 'failed', time.monotonic()
                return jsonify(error='El archivo ya no está disponible.'), 404
            # Normaliza antes de recortar por muestra. Buscar directamente con -ss
            # en MP3 puede variar la muestra inicial y el estado del decodificador.
            # Este flujo produce el mismo PCM al continuar tras una interrupción.
            first_sample = round(session.start * SAMPLE_RATE)
            filters = (f'aresample={SAMPLE_RATE},'
                       'aformat=sample_fmts=s16:channel_layouts=stereo,'
                       f'atrim=start_sample={first_sample},asetpts=PTS-STARTPTS')
            args = [self.ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-i', song.path, '-vn', '-af', filters,
                    '-acodec', 'pcm_s16le', '-ar', str(SAMPLE_RATE), '-ac', str(CHANNELS),
                    '-f', 's16le', 'pipe:1']
            errors = tempfile.TemporaryFile()
            try:
                process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors)
            except OSError:
                errors.close()
                session.state, session.finished = 'failed', time.monotonic()
                return jsonify(error='No se pudo iniciar el decodificador.'), 503
            session.process, session.state = process, 'streaming'

        def cleanup() -> None:
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    process.kill()
                    process.wait()
            if process.stdout:
                process.stdout.close()
            if not errors.closed:
                errors.close()
            with self.lock:
                if session.state == 'streaming':
                    session.state = 'completed' if process.returncode == 0 else 'failed'
                session.finished = time.monotonic()
            self.wake.set()

        def generate():
            count = 0
            try:
                while not session.cancelled.is_set():
                    data = process.stdout.read(CHUNK_BYTES)
                    if not data:
                        break
                    count += len(data)
                    yield data
                code = process.wait(timeout=3)
                if code and not session.cancelled.is_set():
                    errors.seek(0)
                    message = errors.read(2048).decode(errors='replace')
                    log.error('FFmpeg falló: %s', message)
                    # Interrumpe HTTP: el cliente no confunde un archivo truncado con uno completo.
                    raise RuntimeError('El decodificador interrumpió el audio.')
                log.info('FIN stream=%s bytes=%s estado=%s', stream_id[:8], count, session.state)
            finally:
                cleanup()

        response = Response(generate(), mimetype='application/octet-stream', headers={
            'X-Audio-Format': 's16le', 'X-Sample-Rate': str(SAMPLE_RATE),
            'X-Channels': str(CHANNELS), 'X-Audio-Start': str(session.start),
            'X-Audio-Duration': str(song.duration), 'X-Server-ID': self.server_id,
            'X-Estimated-Bytes': str(max(0, int((song.duration - session.start) * BYTES_PER_SECOND))),
            'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
        response.call_on_close(cleanup)
        return response

    def close(self) -> None:
        self.stop_event.set()
        self.wake.set()
        with self.lock:
            ids = list(self.sessions)
        for stream_id in ids:
            self.cancel_session(stream_id)
        self.worker.join(timeout=3)
