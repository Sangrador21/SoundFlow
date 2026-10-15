"""Cliente REST en hilos: catálogo, FIFO, cancelación y audio PCM progresivo."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import queue
import threading
import time
import uuid
import requests
from .audio import BYTES_PER_SECOND, FRAME_BYTES, CHUNK_BYTES, BUFFER_SECONDS
from .http_utils import normalize_url


@dataclass
class Transfer:
    id: str
    song: dict
    start: float
    path: Path
    cancel: threading.Event = field(default_factory=threading.Event)
    coordinator: str = ''
    ticket_id: str = ''
    response: requests.Response | None = None
    done: bool = False


class SoundFlowHTTPClient:
    def __init__(self, base_url: str, cache_dir: Path, event_queue: queue.Queue,
                 *, verify: bool | str = True, fallbacks: list[str] | None = None,
                 wait_timeout: float = 90) -> None:
        self.base_url = normalize_url(base_url)
        self.urls = list(dict.fromkeys([self.base_url] + [normalize_url(v) for v in fallbacks or []]))
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.event_queue, self.verify, self.wait_timeout = event_queue, verify, wait_timeout
        self.lock = threading.RLock()
        self.transfer: Transfer | None = None
        self.closed = threading.Event()
        self.threads: list[threading.Thread] = []
        self.catalog_sequence = 0
        self.event_queue.put({'type': 'network_ready', 'server': self.base_url})

    def _spawn(self, target, *args) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True, name='http-' + target.__name__)
        with self.lock:
            self.threads = [t for t in self.threads if t.is_alive()]
            self.threads.append(thread)
        thread.start()

    def _http(self, method, url, **kwargs):
        return requests.request(method, url, verify=self.verify, timeout=(2, 10), **kwargs)

    def _emit(self, state: Transfer, kind: str, **data) -> None:
        if not state.cancel.is_set() and not self.closed.is_set():
            self.event_queue.put({'type': kind, 'playback_id': state.id, **data})

    def request_catalog(self) -> None:
        with self.lock:
            self.catalog_sequence += 1
            sequence = self.catalog_sequence
        self._spawn(self._catalog, sequence)

    def _catalog(self, sequence: int) -> None:
        errors = []
        with self.lock:
            urls = list(self.urls)
        for url in urls:
            try:
                response = self._http('GET', url + '/api/catalog')
                response.raise_for_status()
                data = response.json()
                with self.lock:
                    for node in data.get('nodes', []):
                        known = normalize_url(node['base_url'])
                        if known not in self.urls:
                            self.urls.append(known)
                    current = sequence == self.catalog_sequence
                if current and not self.closed.is_set():
                    self.event_queue.put({'type': 'catalog', **data, 'server': url})
                return
            except (requests.RequestException, ValueError, KeyError) as exc:
                errors.append(f'{url}: {exc}')
        if not self.closed.is_set():
            self.event_queue.put({'type': 'catalog_error', 'message': 'No se pudo cargar el catálogo. ' + '\n'.join(errors)})

    def request_stream(self, song: dict, start: float = 0.0) -> str:
        self.cancel_stream()
        playback_id = uuid.uuid4().hex
        state = Transfer(playback_id, dict(song), start, self.cache_dir / f'{playback_id}.pcm')
        with self.lock:
            self.transfer = state
        self._spawn(self._download, state)
        return playback_id

    def _cancel_ticket(self, state: Transfer) -> None:
        if state.ticket_id and state.coordinator:
            try:
                self._http('DELETE', state.coordinator + '/api/requests/' + state.ticket_id)
            except requests.RequestException:
                pass
            state.ticket_id = ''

    def cancel_stream(self) -> None:
        with self.lock:
            state = self.transfer
            self.transfer = None
        if state:
            state.cancel.set()
            # La respuesta se cierra en su hilo lector; evita deadlock de urllib3.
            self._spawn(self._cancel_ticket, state)

    def _acquire(self, state: Transfer, start: float, deadline: float) -> dict | None:
        while time.monotonic() < deadline and not state.cancel.is_set():
            with self.lock:
                urls = list(self.urls)
            for url in urls:
                if state.cancel.is_set():
                    return None
                try:
                    response = self._http('POST', url + '/api/requests', json={'song_id': state.song['id'], 'start': start})
                    data = response.json()
                    if response.status_code not in {201, 202}:
                        message = data.get('message', data.get('error', 'Solicitud rechazada.'))
                        if response.status_code in {400, 404}:
                            raise ValueError(message)
                        continue
                    state.coordinator, state.ticket_id = url, data['request_id']
                    while not state.cancel.is_set() and time.monotonic() < deadline:
                        if data['state'] == 'ready':
                            return data['stream']
                        if data['state'] in {'failed', 'cancelled'}:
                            raise ValueError(data.get('message', 'Solicitud cancelada.'))
                        self._emit(state, 'stream_waiting', position=data.get('position', 0),
                                   message=data.get('message', 'Esperando servidor.'))
                        if state.cancel.wait(0.5):
                            return None
                        response = self._http('GET', url + '/api/requests/' + state.ticket_id)
                        response.raise_for_status()
                        data = response.json()
                except requests.RequestException:
                    self._cancel_ticket(state)
                    continue
            self._emit(state, 'stream_waiting', position=0, message='Servidor de entrada desconectado; buscando alternativa.')
            state.cancel.wait(1)
        if not state.cancel.is_set():
            raise TimeoutError('Se agotó el tiempo de espera para atender la canción.')
        return None

    def _download(self, state: Transfer) -> None:
        received, ready, last_emit = 0, False, 0.0
        duration = float(state.song.get('duration', 0))
        estimated = max(0, int((duration - state.start) * BYTES_PER_SECOND))
        threshold = min(int(BUFFER_SECONDS * BYTES_PER_SECOND), estimated) if estimated else int(BUFFER_SECONDS * BYTES_PER_SECOND)
        deadline = time.monotonic() + self.wait_timeout
        try:
            with state.path.open('wb') as handle:
                while not state.cancel.is_set():
                    stream = self._acquire(state, state.start + received / BYTES_PER_SECOND, deadline)
                    if stream is None:
                        return
                    self._emit(state, 'stream_started', server=stream['server_url'], server_id=stream['server_id'],
                               start=state.start, song=state.song)
                    tail = b''
                    try:
                        with self._http('GET', stream['audio_url'], stream=True) as response:
                            state.response = response
                            response.raise_for_status()
                            if (response.headers.get('X-Audio-Format') != 's16le'
                                    or response.headers.get('X-Sample-Rate') != '44100'
                                    or response.headers.get('X-Channels') != '2'):
                                raise ValueError('Formato de audio incompatible.')
                            for data in response.iter_content(chunk_size=CHUNK_BYTES):
                                if state.cancel.is_set():
                                    return
                                # Mantiene muestras completas al reanudar en otro nodo.
                                data = tail + data
                                end = len(data) - len(data) % FRAME_BYTES
                                tail = data[end:]
                                if not end:
                                    continue
                                handle.write(data[:end])
                                handle.flush()
                                received += end
                                now = time.monotonic()
                                if now - last_emit >= 0.1:
                                    self._emit(state, 'stream_progress', received=received, total=estimated,
                                               buffered_until=state.start + received / BYTES_PER_SECOND)
                                    last_emit = now
                                if not ready and received >= threshold:
                                    ready = True
                                    self._emit(state, 'stream_ready', path=str(state.path), song=state.song,
                                               start=state.start, complete=False)
                            if tail:
                                raise ValueError('La transferencia terminó en una muestra incompleta.')
                        state.response = None
                        check = self._http('GET', stream['server_url'] + '/api/streams/' + stream['stream_id'])
                        check.raise_for_status()
                        if check.json()['state'] != 'completed':
                            raise requests.ConnectionError('El servidor no confirmó el final del audio.')
                        if received == 0:
                            raise ValueError('El archivo no contiene audio reproducible.')
                        state.done = True
                        if not ready:
                            self._emit(state, 'stream_ready', path=str(state.path), song=state.song, start=state.start, complete=True)
                        self._emit(state, 'stream_complete', received=received,
                                   buffered_until=state.start + received / BYTES_PER_SECOND)
                        return
                    except requests.RequestException:
                        state.response = None
                        self._cancel_ticket(state)
                        if state.cancel.is_set():
                            return
                        # Reanuda desde las muestras recibidas, sin duplicar ni borrar el búfer.
                        self._emit(state, 'stream_waiting', position=0,
                                   message='Transferencia interrumpida; buscando servidor para continuar.')
                        if time.monotonic() >= deadline:
                            raise TimeoutError('No se pudo recuperar la transferencia.')
                        state.cancel.wait(1)
        except (requests.RequestException, ValueError, KeyError, OSError, TimeoutError) as exc:
            self._emit(state, 'network_error', message=str(exc))
        finally:
            state.response = None
            self._cancel_ticket(state)

    def close(self) -> None:
        self.closed.set()
        self.cancel_stream()
        with self.lock:
            threads = list(self.threads)
        # Da tiempo a DELETE sin bloquear el cierre de la interfaz indefinidamente.
        end = time.monotonic() + 2
        for thread in threads:
            thread.join(timeout=max(0, end - time.monotonic()))
        for path in self.cache_dir.glob('*.pcm'):
            try:
                path.unlink()
            except OSError:
                pass
