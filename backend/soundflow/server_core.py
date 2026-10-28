"""Servicio REST y coordinación de catálogos/transferencias entre nodos HTTP.

No hay límite por número de clientes. La admisión usa CPU/memoria actuales.
La cola FIFO contiene solicitudes pendientes, no canciones de la interfaz.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import hmac
import logging
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Any

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import psutil
import requests

from .audio import SAMPLE_RATE, CHANNELS, BYTES_PER_SECOND, CHUNK_BYTES, ffmpeg_executable
from .http_utils import normalize_url
from .library import MusicLibrary
from .resources import ResourceMonitor
from .downloads import download_response

log = logging.getLogger('soundflow.server')


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


@dataclass
class PendingRequest:
    id: str
    song_id: str
    start: float
    created: float = field(default_factory=time.monotonic)
    state: str = 'waiting'
    stream: dict | None = None
    reason: str = 'Buscando un servidor disponible con la canción.'
    error_code: int = 0


class SoundFlowServer:
    def __init__(self, music_dir: Path, base_url: str, *, server_id: str = 'S1',
                 peers: list[str] | None = None, verify: bool | str = True,
                 cpu_threshold: float = 95, memory_threshold: float = 95,
                 wait_timeout: float = 60, peer_timeout: float = 1,
                 maintenance: bool = False, cluster_token: str = '',
                 allowed_origins: list[str] | None = None) -> None:
        self.base_url = normalize_url(base_url)
        self.server_id = server_id
        self.peers = list(dict.fromkeys(normalize_url(p) for p in peers or []
                                       if normalize_url(p) != self.base_url))
        self.verify = verify
        self.cpu_threshold, self.memory_threshold = cpu_threshold, memory_threshold
        self.wait_timeout, self.peer_timeout = wait_timeout, peer_timeout
        self.maintenance, self.cluster_token = maintenance, cluster_token
        self.ffmpeg = ffmpeg_executable()
        self.library = MusicLibrary(music_dir)
        self.library.scan()
        self.lock = threading.RLock()
        self.dispatch_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.sessions: dict[str, StreamSession] = {}
        self.tickets: dict[str, PendingRequest] = {}
        self.pending: deque[str] = deque()
        self.node_cache: dict[str, dict] = {}
        self.resource_monitor = ResourceMonitor()
        self.cpu_percent = 0.0
        self.memory_percent = psutil.virtual_memory().percent
        self.app = Flask(__name__)
        self.app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
        CORS(self.app, resources={r'/api/*': {
            'origins': allowed_origins or ['http://localhost:5173', 'http://127.0.0.1:5173'],
            'methods': ['GET', 'POST', 'DELETE', 'OPTIONS'],
            'allow_headers': ['Content-Type'],
            'expose_headers': ['X-Audio-Format', 'X-Sample-Rate', 'X-Channels',
                               'X-Audio-Start', 'X-Audio-Duration', 'X-Server-ID', 'X-Estimated-Bytes',
                               'X-Download-SHA256', 'X-Download-Bytes'],
        }}, supports_credentials=False, max_age=600)
        self._routes()
        self.worker = threading.Thread(target=self._maintenance_loop, daemon=True,
                                       name=f'fifo-resources-{server_id}')
        self.worker.start()

    def resource_status(self) -> dict:
        with self.lock:
            active = sum(s.state in {'reserved', 'streaming'} for s in self.sessions.values())
            cpu, memory = self.cpu_percent, self.memory_percent
            accepting = not self.maintenance and cpu < self.cpu_threshold and memory < self.memory_threshold
        return {'accepting': accepting, 'active_streams': active,
                'cpu_percent': round(cpu, 1), 'memory_percent': round(memory, 1),
                'cpu_threshold': self.cpu_threshold, 'memory_threshold': self.memory_threshold,
                'maintenance': self.maintenance}

    def node_info(self) -> dict:
        return {'server_id': self.server_id, 'base_url': self.base_url, 'peers': self.peers,
                'resources': self.resource_status(), 'songs': self.library.public_catalog()}

    def _http(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = {'X-Cluster-Token': self.cluster_token} if self.cluster_token else {}
        return requests.request(method, url, timeout=(self.peer_timeout, self.peer_timeout),
                                verify=self.verify, headers=headers, **kwargs)

    def discover(self) -> tuple[list[dict], list[str]]:
        """BFS de nodos. /api/node es local: no hay llamadas recursivas ni ciclos."""
        local = self.node_info()
        nodes = [local]
        offline: list[str] = []
        todo = deque(self.peers)
        visited = {self.base_url}
        while todo and not self.stop_event.is_set():
            url = todo.popleft()
            if url in visited:
                continue
            visited.add(url)
            try:
                response = self._http('GET', url + '/api/node')
                response.raise_for_status()
                node = response.json()
                if not isinstance(node, dict) or not isinstance(node.get('songs'), list):
                    raise ValueError('Respuesta de nodo inválida')
                # Se usa la URL alcanzada; evita confiar en una dirección anunciada errónea.
                node['base_url'] = url
                nodes.append(node)
                with self.lock:
                    self.node_cache[url] = node
                for peer in node.get('peers', []):
                    normalized = normalize_url(peer)
                    if normalized not in visited:
                        todo.append(normalized)
            except (requests.RequestException, ValueError, KeyError, TypeError):
                offline.append(url)
                # Se conservan las conexiones conocidas de nodos que ahora estén caídos.
                with self.lock:
                    previous = self.node_cache.get(url, {})
                for peer in previous.get('peers', []):
                    try:
                        normalized = normalize_url(peer)
                        if normalized not in visited:
                            todo.append(normalized)
                    except ValueError:
                        pass
        return nodes, offline

    def catalog(self) -> dict:
        nodes, offline = self.discover()
        sources = [(node, True) for node in nodes]
        with self.lock:
            sources += [(self.node_cache[url], False) for url in offline if url in self.node_cache]
        songs: dict[str, dict] = {}
        for node, available in sources:
            for item in node['songs']:
                song_id = item.get('id')
                if not isinstance(song_id, str):
                    continue
                if song_id not in songs:
                    songs[song_id] = {**item, 'servers': [], 'available': False}
                song = songs[song_id]
                if node['server_id'] not in song['servers']:
                    song['servers'].append(node['server_id'])
                song['available'] |= available
        return {'songs': sorted(songs.values(), key=lambda s: s['title'].casefold()),
                'nodes': [{'server_id': n['server_id'], 'base_url': n['base_url'],
                           'resources': n['resources'], 'song_count': len(n['songs'])} for n in nodes],
                'offline': offline}

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

    def _attempt(self, ticket: PendingRequest) -> bool:
        nodes, offline = self.discover()
        holders = [node for node in nodes if any(s.get('id') == ticket.song_id for s in node['songs'])]
        candidates = sorted((n for n in holders if n['resources'].get('accepting')),
                            key=lambda n: (n['resources']['active_streams'],
                                           n['resources']['cpu_percent'], n['resources']['memory_percent']))
        transient = False
        for node in candidates:
            with self.lock:
                if ticket.state != 'waiting':
                    return True
            try:
                if node['base_url'] == self.base_url:
                    data, status = self._reserve(ticket.song_id, ticket.start)
                else:
                    response = self._http('POST', node['base_url'] + '/api/internal/streams',
                                          json={'song_id': ticket.song_id, 'start': ticket.start})
                    status, data = response.status_code, response.json()
                if status == 400:
                    with self.lock:
                        ticket.state, ticket.reason, ticket.error_code = 'failed', data.get('error', 'Solicitud inválida.'), 400
                    return True
                if status != 201:
                    transient = True
                    continue
                data['server_url'] = node['base_url']
                data['audio_url'] = node['base_url'] + f"/api/streams/{data['stream_id']}/audio"
                with self.lock:
                    cancelled = ticket.state != 'waiting'
                    if not cancelled:
                        ticket.state, ticket.stream = 'ready', data
                        ticket.reason = 'Solicitud asignada a ' + data['server_id']
                if cancelled:
                    self._cancel_assignment(data)
                else:
                    log.info('ASIGNACION solicitud=%s destino=%s', ticket.id[:8], data['server_id'])
                return True
            except (requests.RequestException, ValueError, KeyError):
                transient = True
        with self.lock:
            if ticket.state != 'waiting':
                return True
            if not holders and not offline and not transient:
                ticket.state, ticket.error_code = 'failed', 404
                ticket.reason = 'La canción no existe en los servidores disponibles.'
                return True
            ticket.reason = ('Los nodos con la canción están ocupados; esperando recursos.' if holders else
                             'No se puede contactar al servidor con la canción; esperando reconexión.')
        return False

    def dispatch_once(self) -> None:
        if not self.dispatch_lock.acquire(blocking=False):
            return
        try:
            # Orden global FIFO: una nueva solicitud no adelanta a la primera pendiente.
            while not self.stop_event.is_set():
                with self.lock:
                    while self.pending and self.tickets[self.pending[0]].state != 'waiting':
                        self.pending.popleft()
                    if not self.pending:
                        break
                    ticket = self.tickets[self.pending[0]]
                    if time.monotonic() - ticket.created >= self.wait_timeout:
                        ticket.state, ticket.error_code = 'failed', 504
                        ticket.reason = 'Se agotó el tiempo de espera. Puedes volver a intentar.'
                        continue
                if not self._attempt(ticket):
                    break
        finally:
            self.dispatch_lock.release()

    def _maintenance_loop(self) -> None:
        while not self.stop_event.is_set():
            cpu, memory = self.resource_monitor.sample()
            with self.lock:
                self.cpu_percent, self.memory_percent = cpu, memory
                now = time.monotonic()
                for session in self.sessions.values():
                    if session.state == 'reserved' and now - session.created > 30:
                        session.state, session.finished = 'expired', now
                for sid in [sid for sid, s in self.sessions.items() if s.finished and now - s.finished > 120]:
                    del self.sessions[sid]
                queued = set(self.pending)
                for tid in [tid for tid, t in self.tickets.items()
                            if tid not in queued and t.state != 'waiting' and now - t.created > 600]:
                    del self.tickets[tid]
            self.dispatch_once()
            self.wake.wait(1)
            self.wake.clear()

    def ticket_data(self, ticket: PendingRequest) -> dict:
        with self.lock:
            active = [tid for tid in self.pending if self.tickets[tid].state == 'waiting']
            position = active.index(ticket.id) + 1 if ticket.id in active else 0
            return {'request_id': ticket.id, 'state': ticket.state, 'song_id': ticket.song_id,
                    'position': position, 'message': ticket.reason, 'stream': ticket.stream,
                    'error_code': ticket.error_code, 'wait_timeout': self.wait_timeout}

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

    def _cancel_assignment(self, stream: dict) -> None:
        if stream['server_url'] == self.base_url:
            self.cancel_session(stream['stream_id'])
        else:
            try:
                self._http('DELETE', stream['server_url'] + f"/api/streams/{stream['stream_id']}")
            except requests.RequestException:
                pass

    @staticmethod
    def _parse_body() -> tuple[str, float]:
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise ValueError('Envía un objeto JSON con song_id y start opcional.')
        song_id = value.get('song_id')
        if not isinstance(song_id, str) or len(song_id) != 64 or any(c not in '0123456789abcdef' for c in song_id):
            raise ValueError('song_id debe ser un identificador del catálogo.')
        if isinstance(value.get('start', 0), bool):
            raise ValueError('start debe ser un número de segundos.')
        start = float(value.get('start', 0))
        if not math.isfinite(start) or start < 0:
            raise ValueError('start debe ser un número finito mayor o igual a cero.')
        return song_id, start

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

    def _routes(self) -> None:
        app = self.app

        @app.errorhandler(HTTPException)
        def http_error(exc):
            return jsonify(error=exc.description), exc.code

        @app.errorhandler(ValueError)
        @app.errorhandler(TypeError)
        def invalid(exc):
            return jsonify(error=str(exc)), 400

        @app.get('/api/health')
        def health():
            return jsonify(server_id=self.server_id, status='ok', **self.resource_status())

        @app.get('/api/node')
        def node():
            return jsonify(self.node_info())

        @app.get('/api/catalog')
        def catalog():
            return jsonify(self.catalog())

        @app.post('/api/requests')
        def create_request():
            song_id, start = self._parse_body()
            ticket = PendingRequest(uuid.uuid4().hex, song_id, start)
            with self.lock:
                self.tickets[ticket.id] = ticket
                self.pending.append(ticket.id)
            self.dispatch_once()
            self.wake.set()
            data = self.ticket_data(ticket)
            status = ticket.error_code if ticket.state == 'failed' else (201 if ticket.state == 'ready' else 202)
            log.info('SOLICITUD %s estado=%s posición=%s', ticket.id[:8], ticket.state, data['position'])
            return jsonify(data), status

        @app.get('/api/requests/<request_id>')
        def request_status(request_id):
            with self.lock:
                ticket = self.tickets.get(request_id)
                if ticket is None:
                    return jsonify(error='Solicitud desconocida.'), 404
                return jsonify(self.ticket_data(ticket))

        @app.delete('/api/requests/<request_id>')
        def cancel_request(request_id):
            with self.lock:
                ticket = self.tickets.get(request_id)
                if ticket is None:
                    return jsonify(error='Solicitud desconocida.'), 404
                ticket.state = 'cancelled'
                stream = ticket.stream
            if stream:
                self._cancel_assignment(stream)
            self.wake.set()
            return '', 204

        @app.post('/api/internal/streams')
        def reserve_internal():
            if self.cluster_token and not hmac.compare_digest(request.headers.get('X-Cluster-Token', ''), self.cluster_token):
                return jsonify(error='Token del clúster inválido.'), 403
            song_id, start = self._parse_body()
            result, status = self._reserve(song_id, start)
            return jsonify(result), status

        @app.get('/api/streams/<stream_id>/audio')
        def audio(stream_id):
            return self._audio_response(stream_id)

        @app.get('/api/streams/<stream_id>/download')
        def download(stream_id):
            return download_response(self, stream_id)

        @app.get('/api/streams/<stream_id>')
        def stream_status(stream_id):
            with self.lock:
                session = self.sessions.get(stream_id)
                if session is None:
                    return jsonify(error='Sesión desconocida.'), 404
                return jsonify(state=session.state, stream_id=session.id)

        @app.delete('/api/streams/<stream_id>')
        def cancel_stream(stream_id):
            self.cancel_session(stream_id)
            return '', 204

    def close(self) -> None:
        self.stop_event.set()
        self.wake.set()
        with self.lock:
            ids = list(self.sessions)
        for stream_id in ids:
            self.cancel_session(stream_id)
        self.worker.join(timeout=3)
