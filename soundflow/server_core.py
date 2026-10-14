from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import math
import queue
import socket
import threading
import time
import uuid
from typing import Any

from .library import MusicLibrary
from .protocol import CHUNK_SIZE, decode_json, encode_json, pack_audio_chunk


ClientAddress = tuple[str, int]


@dataclass
class StreamSession:
    """Estado independiente de una transferencia cliente-servidor."""

    session_id: str
    request_id: str
    client: ClientAddress
    path: Path
    ack_queue: queue.Queue[int]
    cancel_event: threading.Event
    created_at: float


@dataclass
class QueuedRequest:
    """Petición en espera cuando el clúster no tiene capacidad inmediata."""

    request_id: str
    song_id: str
    client: ClientAddress
    visited_server_ids: tuple[str, ...]
    created_at: float


@dataclass
class CapacityProbe:
    """Respuestas de capacidad recibidas desde los servidores pares."""

    expected: set[ClientAddress]
    responses: dict[ClientAddress, dict[str, Any]] = field(default_factory=dict)
    event: threading.Event = field(default_factory=threading.Event)


class SoundFlowServer:

    CLUSTER_CAPACITY_REQUEST = "cluster_capacity_request"
    CLUSTER_CAPACITY_RESPONSE = "cluster_capacity_response"

    def __init__(
        self,
        host: str,
        port: int,
        music_dir: Path,
        max_streams: int = 8,
        *,
        server_id: str | None = None,
        advertise_host: str | None = None,
        peers: list[ClientAddress] | None = None,
        probe_timeout: float = 0.60,
    ) -> None:
        if max_streams < 1:
            raise ValueError("max_streams debe ser al menos 1")

        self.host = host
        self.port = port
        self.music_dir = Path(music_dir)
        self.max_streams = max_streams
        self.probe_timeout = max(0.10, float(probe_timeout))

        if advertise_host:
            self.advertise_host = advertise_host
        elif host not in {"0.0.0.0", "::"}:
            self.advertise_host = host
        else:
            # Para pruebas locales. En otra computadora se debe pasar --advertise-host con la IP LAN alcanzable por los clientes.
            self.advertise_host = "127.0.0.1"

        self.server_id = server_id or f"{self.advertise_host}:{port}"
        self.peer_addresses = self._normalize_peers(peers or [])

        self.library = MusicLibrary(self.music_dir)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.socket.settimeout(0.25)

        self.shutdown_event = threading.Event()

        # Sincronización heredada de P3.
        self.state_lock = threading.RLock()
        self.queue_condition = threading.Condition(self.state_lock)
        self.send_lock = threading.Lock()
        self.stream_slots = threading.BoundedSemaphore(max_streams)

        # Estado por sesión / cliente.
        self.sessions: dict[str, StreamSession] = {}
        self.current_session_by_client: dict[ClientAddress, str] = {}
        self.latest_request_by_client: dict[ClientAddress, str] = {}
        self.known_clients: set[ClientAddress] = set()
        self.stream_threads: set[threading.Thread] = set()
        self.dispatch_threads: set[threading.Thread] = set()
        self.active_stream_count = 0

        # Cola FIFO de solicitudes que no pudieron ser asignadas de inmediato.
        self.pending_queue: deque[str] = deque()
        self.queued_requests: dict[str, QueuedRequest] = {}
        self.queued_request_by_client: dict[ClientAddress, str] = {}

        # Sondeos servidor-servidor. El receptor UDP llena estas respuestas y despierta al hilo que pidió capacidad.
        self.capacity_probes: dict[str, CapacityProbe] = {}

        self.queue_dispatcher = threading.Thread(
            target=self._queue_dispatch_loop,
            name=f"queue-dispatcher-{self.server_id}",
            daemon=True,
        )

    # ------------------------------------------------------------------
    # Ciclo principal
    # ------------------------------------------------------------------

    def serve_forever(self) -> None:
        songs = self.library.scan()
        self.queue_dispatcher.start()

        print(f"SoundFlow Server P4 [{self.server_id}] escuchando UDP en {self.host}:{self.port}")
        print(f"Dirección anunciada a clientes: {self.advertise_host}:{self.port}")
        print(f"Biblioteca: {self.music_dir.resolve()} ({len(songs)} canción(es))")
        print(f"Capacidad local: {self.max_streams} streams simultáneos")
        if self.peer_addresses:
            peers = ", ".join(f"{host}:{port}" for host, port in self.peer_addresses)
            print(f"Servidores pares: {peers}")
        else:
            print("Servidores pares: ninguno (funciona como un único servidor)")
        print(
            "Modelo: receptor UDP + thread-per-stream + Semaphore + RLock + "
            "Queue/Event + balanceo entre servidores + cola FIFO"
        )
        print("Ctrl+C para detener.\n")

        try:
            while not self.shutdown_event.is_set():
                try:
                    data, address = self.socket.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    break

                message = decode_json(data)
                if message is None:
                    continue

                msg_type = str(message.get("type", ""))
                if msg_type.startswith("cluster_"):
                    self._handle_cluster_message(message, address)
                    continue

                with self.state_lock:
                    self.known_clients.add(address)

                self._handle_client_message(message, address)
        except KeyboardInterrupt:
            print("\nCerrando servidor...")
        finally:
            self.close()

    def close(self) -> None:
        if self.shutdown_event.is_set():
            return

        self.shutdown_event.set()
        with self.queue_condition:
            sessions = list(self.sessions.values())
            stream_threads = list(self.stream_threads)
            dispatch_threads = list(self.dispatch_threads)
            probes = list(self.capacity_probes.values())
            self.queue_condition.notify_all()

        for session in sessions:
            session.cancel_event.set()
        for probe in probes:
            probe.event.set()

        try:
            self.socket.close()
        except OSError:
            pass

        for thread in stream_threads + dispatch_threads:
            if thread is not threading.current_thread():
                thread.join(timeout=1.0)

        if self.queue_dispatcher.is_alive() and self.queue_dispatcher is not threading.current_thread():
            self.queue_dispatcher.join(timeout=1.0)

    # ------------------------------------------------------------------
    # Mensajes de clientes
    # ------------------------------------------------------------------

    def _handle_client_message(self, message: dict[str, Any], client: ClientAddress) -> None:
        msg_type = message.get("type")

        if msg_type == "catalog_request":
            self._handle_catalog_request(client)

        elif msg_type == "stream_request":
            song_id = Path(str(message.get("song_id", ""))).name
            request_id = str(message.get("request_id") or uuid.uuid4())
            raw_visited = message.get("visited_server_ids", [])
            visited = tuple(str(item) for item in raw_visited if isinstance(item, str))
            self._handle_stream_request(song_id, request_id, visited, client)

        elif msg_type == "ack":
            self._handle_ack(message, client)

        elif msg_type == "cancel_stream":
            session_id = str(message.get("session_id", ""))
            self._cancel_session(session_id, client)

        elif msg_type == "cancel_request":
            request_id = str(message.get("request_id", ""))
            self._cancel_pending_request(request_id, client)

        elif msg_type == "disconnect":
            self._disconnect_client(client)

        elif msg_type == "ping":
            self._send_json(
                {
                    "type": "pong",
                    "server_id": self.server_id,
                    "active_streams": self._active_stream_count(),
                    "capacity": self.max_streams,
                },
                client,
            )

    def _handle_catalog_request(self, client: ClientAddress) -> None:
        songs = self.library.all()
        payload = []
        for song in songs:
            item = song.to_dict()
            item["path"] = song.filename
            payload.append(item)

        self._send_json(
            {
                "type": "catalog",
                "songs": payload,
                "server_id": self.server_id,
            },
            client,
        )
        print(
            f"{self._client_label(client)} catálogo solicitado a {self.server_id} "
            f"({len(payload)} canciones) | clientes conocidos={self._known_client_count()}"
        )

    def _handle_stream_request(self, song_id: str, request_id: str, visited_server_ids: tuple[str, ...], client: ClientAddress,) -> None:
        if not self._song_exists(song_id):
            self._send_json(
                {
                    "type": "error",
                    "request_id": request_id,
                    "message": f"No existe '{song_id}' en el servidor {self.server_id}.",
                },
                client,
            )
            return

        # Una nueva solicitud del mismo cliente sustituye su espera anterior y cancela únicamente su transferencia activa previa.
        with self.queue_condition:
            old_request = self.latest_request_by_client.get(client)
            self.latest_request_by_client[client] = request_id
            if old_request and old_request != request_id:
                self._remove_queued_request_locked(old_request)

            old_session_id = self.current_session_by_client.get(client)
            old_session = self.sessions.get(old_session_id) if old_session_id else None
            if old_session is not None:
                old_session.cancel_event.set()

        visited = tuple(dict.fromkeys((*visited_server_ids, self.server_id)))

        # Reserva atómica del semáforo: evita que dos solicitudes observen el mismo hueco y lo ocupen simultáneamente.
        if self._try_reserve_stream_slot():
            self._start_stream_reserved(song_id, request_id, visited, client)
            return

        # No se bloquea el receptor mientras se consulta a otros servidores.
        thread = threading.Thread(
            target=self._dispatch_or_queue_worker,
            args=(song_id, request_id, visited, client),
            name=f"dispatch-{client[1]}-{request_id[:8]}",
            daemon=True,
        )
        with self.state_lock:
            self.dispatch_threads.add(thread)
        thread.start()

    def _handle_ack(self, message: dict[str, Any], client: ClientAddress) -> None:
        session_id = str(message.get("session_id", ""))
        try:
            seq = int(message.get("seq"))
        except (TypeError, ValueError):
            return

        with self.state_lock:
            session = self.sessions.get(session_id)

        if session is None or session.client != client:
            return

        session.ack_queue.put(seq)

    def _cancel_session(self, session_id: str, client: ClientAddress) -> None:
        with self.state_lock:
            session = self.sessions.get(session_id)

        if session is not None and session.client == client:
            session.cancel_event.set()

    def _cancel_pending_request(self, request_id: str, client: ClientAddress) -> None:
        with self.queue_condition:
            if self.latest_request_by_client.get(client) == request_id:
                self.latest_request_by_client.pop(client, None)
            queued = self.queued_requests.get(request_id)
            if queued is not None and queued.client == client:
                self._remove_queued_request_locked(request_id)
            self.queue_condition.notify_all()

    def _disconnect_client(self, client: ClientAddress) -> None:
        with self.queue_condition:
            session_id = self.current_session_by_client.get(client)
            session = self.sessions.get(session_id) if session_id else None
            request_id = self.latest_request_by_client.pop(client, None)
            if request_id:
                self._remove_queued_request_locked(request_id)
            self.known_clients.discard(client)
            self.queue_condition.notify_all()

        if session is not None:
            session.cancel_event.set()

        print(f"{self._client_label(client)} cliente desconectado de {self.server_id}")

    # ------------------------------------------------------------------
    # Balanceo entre servidores
    # ------------------------------------------------------------------

    def _dispatch_or_queue_worker(self, song_id: str, request_id: str, visited_server_ids: tuple[str, ...], client: ClientAddress,) -> None:
        try:
            if not self._is_current_request(client, request_id):
                return

            target = self._probe_peers_for_capacity(song_id, set(visited_server_ids))
            if target is not None and self._is_current_request(client, request_id):
                self._send_redirect(request_id, visited_server_ids, target, client)
                return

            if self._is_current_request(client, request_id):
                self._enqueue_request(song_id, request_id, visited_server_ids, client)
        finally:
            current = threading.current_thread()
            with self.state_lock:
                self.dispatch_threads.discard(current)

    def _probe_peers_for_capacity(self, song_id: str, excluded_server_ids: set[str],) -> dict[str, Any] | None:
        if not self.peer_addresses or self.shutdown_event.is_set():
            return None

        probe_id = str(uuid.uuid4())
        probe = CapacityProbe(expected=set(self.peer_addresses))
        with self.state_lock:
            self.capacity_probes[probe_id] = probe

        message = {
            "type": self.CLUSTER_CAPACITY_REQUEST,
            "probe_id": probe_id,
            "requester_id": self.server_id,
            "song_id": song_id,
        }
        for peer in self.peer_addresses:
            self._send_json(message, peer)

        probe.event.wait(timeout=self.probe_timeout)

        with self.state_lock:
            finished = self.capacity_probes.pop(probe_id, probe)
            responses = list(finished.responses.items())

        candidates: list[dict[str, Any]] = []
        for source, response in responses:
            server_id = str(response.get("server_id", ""))
            if not server_id or server_id in excluded_server_ids:
                continue
            if not bool(response.get("has_song", False)):
                continue
            try:
                available = int(response.get("available", 0))
                active = int(response.get("active_streams", 0))
                capacity = max(1, int(response.get("capacity", 1)))
                queued = max(0, int(response.get("queued", 0)))
                target_port = int(response.get("port", source[1]))
            except (TypeError, ValueError):
                continue
            if available <= 0:
                continue

            candidates.append(
                {
                    "server_id": server_id,
                    "host": str(response.get("advertise_host") or source[0]),
                    "port": target_port,
                    "active_streams": active,
                    "capacity": capacity,
                    "available": available,
                    "queued": queued,
                    "utilization": active / capacity,
                }
            )

        if not candidates:
            return None

        # Least-loaded: menor utilización, luego menor cola y finalmente menor cantidad de streams activos para tener un desempate determinista.
        return min(
            candidates,
            key=lambda item: (
                float(item["utilization"]),
                int(item["queued"]),
                int(item["active_streams"]),
                str(item["server_id"]),
            ),
        )

    def _handle_cluster_message(self, message: dict[str, Any], source: ClientAddress) -> None:
        if source not in self.peer_addresses:
            return

        msg_type = message.get("type")
        if msg_type == self.CLUSTER_CAPACITY_REQUEST:
            probe_id = str(message.get("probe_id", ""))
            song_id = Path(str(message.get("song_id", ""))).name
            if not probe_id:
                return

            active = self._active_stream_count()
            with self.state_lock:
                queued = len(self.queued_requests)
            self._send_json(
                {
                    "type": self.CLUSTER_CAPACITY_RESPONSE,
                    "probe_id": probe_id,
                    "server_id": self.server_id,
                    "advertise_host": self.advertise_host,
                    "port": self.port,
                    "active_streams": active,
                    "capacity": self.max_streams,
                    "available": max(0, self.max_streams - active),
                    "queued": queued,
                    "has_song": self._song_exists(song_id),
                },
                source,
            )

        elif msg_type == self.CLUSTER_CAPACITY_RESPONSE:
            probe_id = str(message.get("probe_id", ""))
            with self.state_lock:
                probe = self.capacity_probes.get(probe_id)
                if probe is None or source not in probe.expected:
                    return
                probe.responses[source] = dict(message)
                if probe.expected.issubset(probe.responses.keys()):
                    probe.event.set()

    def _send_redirect(self, request_id: str, visited_server_ids: tuple[str, ...], target: dict[str, Any], client: ClientAddress, ) -> None:
        self._send_json(
            {
                "type": "redirect",
                "request_id": request_id,
                "from_server_id": self.server_id,
                "target_server_id": target["server_id"],
                "host": target["host"],
                "port": target["port"],
                "visited_server_ids": list(visited_server_ids),
                "reason": "Servidor local sin capacidad; se seleccionó un servidor con menor carga.",
            },
            client,
        )
        with self.queue_condition:
            if self.latest_request_by_client.get(client) == request_id:
                self.latest_request_by_client.pop(client, None)
            self._remove_queued_request_locked(request_id)
            self.queue_condition.notify_all()

        print(
            f"{self._client_label(client)} request={request_id[:8]} redirigida "
            f"{self.server_id} -> {target['server_id']} "
            f"(carga {target['active_streams']}/{target['capacity']})"
        )

    # ------------------------------------------------------------------
    # Cola FIFO de solicitudes pendientes
    # ------------------------------------------------------------------

    def _enqueue_request( song_id: str, request_id: str, visited_server_ids: tuple[str, ...], client: ClientAddress, ) -> None:
        request = QueuedRequest(
            request_id=request_id,
            song_id=song_id,
            client=client,
            visited_server_ids=visited_server_ids,
            created_at=time.monotonic(),
        )

        with self.queue_condition:
            if self.latest_request_by_client.get(client) != request_id:
                return

            old = self.queued_request_by_client.get(client)
            if old and old != request_id:
                self._remove_queued_request_locked(old)

            if request_id not in self.queued_requests:
                self.queued_requests[request_id] = request
                self.queued_request_by_client[client] = request_id
                self.pending_queue.append(request_id)

            position = self._queue_position_locked(request_id)
            self.queue_condition.notify_all()

        self._send_json(
            {
                "type": "stream_queued",
                "request_id": request_id,
                "server_id": self.server_id,
                "position": position,
                "message": (
                    "Todos los servidores están ocupados temporalmente; "
                    f"solicitud en cola FIFO (posición {position})."
                ),
            },
            client,
        )
        print(
            f"{self._client_label(client)} request={request_id[:8]} en cola FIFO "
            f"de {self.server_id} | posición={position}"
        )

    def _queue_dispatch_loop(self) -> None:
        while not self.shutdown_event.is_set():
            with self.queue_condition:
                request = self._peek_next_queued_locked()
                if request is None:
                    self.queue_condition.wait(timeout=0.50)
                    continue

            if not self._is_current_request(request.client, request.request_id):
                with self.queue_condition:
                    self._remove_queued_request_locked(request.request_id)
                continue

            # Primero se respeta capacidad local: si se liberó un slot, la solicitud más antigua entra inmediatamente.
            if self._try_reserve_stream_slot():
                if self._claim_queued_request(request.request_id):
                    self._start_stream_reserved(
                        request.song_id,
                        request.request_id,
                        request.visited_server_ids,
                        request.client,
                    )
                else:
                    self._release_stream_slot()
                continue

            # Si seguimos llenos, el servidor vuelve a actuar como solicitante de recursos y pregunta por capacidad para la cabeza de la cola.
            target = self._probe_peers_for_capacity(
                request.song_id,
                set(request.visited_server_ids),
            )
            if target is not None and self._claim_queued_request(request.request_id):
                if self._is_current_request(request.client, request.request_id):
                    self._send_redirect(
                        request.request_id,
                        request.visited_server_ids,
                        target,
                        request.client,
                    )
                continue

            with self.queue_condition:
                self.queue_condition.wait(timeout=0.50)

    def _peek_next_queued_locked(self) -> QueuedRequest | None:
        while self.pending_queue:
            request_id = self.pending_queue[0]
            request = self.queued_requests.get(request_id)
            if request is not None:
                return request
            self.pending_queue.popleft()
        return None

    def _claim_queued_request(self, request_id: str) -> bool:
        with self.queue_condition:
            request = self.queued_requests.get(request_id)
            if request is None:
                return False
            self._remove_queued_request_locked(request_id)
            return True

    def _remove_queued_request_locked(self, request_id: str) -> None:
        request = self.queued_requests.pop(request_id, None)
        if request is None:
            return
        if self.queued_request_by_client.get(request.client) == request_id:
            self.queued_request_by_client.pop(request.client, None)
        # El id se elimina perezosamente del deque en _peek_next_queued_locked.

    def _queue_position_locked(self, request_id: str) -> int:
        position = 0
        for queued_id in self.pending_queue:
            if queued_id not in self.queued_requests:
                continue
            position += 1
            if queued_id == request_id:
                return position
        return max(1, position)

    # ------------------------------------------------------------------
    # Streaming concurrente local
    # ------------------------------------------------------------------

    def _start_stream_reserved( self, song_id: str, request_id: str, visited_server_ids: tuple[str, ...], client: ClientAddress, ) -> None:
        # El slot ya fue reservado antes de entrar aquí.
        if not self._is_current_request(client, request_id):
            self._release_stream_slot()
            return

        path = (self.music_dir / song_id).resolve()
        try:
            path.relative_to(self.music_dir.resolve())
        except ValueError:
            self._release_stream_slot()
            self._send_json(
                {"type": "error", "request_id": request_id, "message": "Canción inválida."},
                client,
            )
            return

        songs = {song.filename: song for song in self.library.all()}
        song = songs.get(song_id)
        if song is None or not path.is_file():
            self._release_stream_slot()
            self._send_json(
                {
                    "type": "error",
                    "request_id": request_id,
                    "message": f"No existe '{song_id}' en el servidor.",
                },
                client,
            )
            return

        session_id = str(uuid.uuid4())
        session = StreamSession(
            session_id=session_id,
            request_id=request_id,
            client=client,
            path=path,
            ack_queue=queue.Queue(),
            cancel_event=threading.Event(),
            created_at=time.monotonic(),
        )

        with self.queue_condition:
            if self.latest_request_by_client.get(client) != request_id:
                self._release_stream_slot()
                return

            old_session_id = self.current_session_by_client.get(client)
            old_session = self.sessions.get(old_session_id) if old_session_id else None
            if old_session is not None:
                old_session.cancel_event.set()

            self.sessions[session_id] = session
            self.current_session_by_client[client] = session_id
            self._remove_queued_request_locked(request_id)

        file_size = path.stat().st_size
        total_chunks = max(1, math.ceil(file_size / CHUNK_SIZE))
        song_payload = song.to_dict()
        song_payload["path"] = song.filename

        self._send_json(
            {
                "type": "stream_start",
                "request_id": request_id,
                "session_id": session_id,
                "server_id": self.server_id,
                "song": song_payload,
                "file_size": file_size,
                "total_chunks": total_chunks,
                "chunk_size": CHUNK_SIZE,
            },
            client,
        )

        thread = threading.Thread(
            target=self._stream_worker,
            args=(session, total_chunks),
            name=f"stream-{client[1]}-{session_id[:8]}",
            daemon=True,
        )

        with self.state_lock:
            self.stream_threads.add(thread)
            active_sessions = len(self.sessions)
            local_load = self.active_stream_count

        print(
            f"{self._client_label(client)} request={request_id[:8]} sesión={session_id[:8]} "
            f"atendida por {self.server_id}: '{song.filename}' "
            f"({file_size} bytes, {total_chunks} fragmentos) | "
            f"carga local={local_load}/{self.max_streams} | sesiones={active_sessions}"
        )
        thread.start()

    def _stream_worker(self, session: StreamSession, total_chunks: int) -> None:
        session_id = session.session_id
        client = session.client
        path = session.path
        session_bytes = uuid.UUID(session_id).bytes
        max_retries = 10
        timeout = 0.50

        try:
            print(
                f"{self._client_label(client)} sesión={session_id[:8]} "
                f"worker={threading.current_thread().name} inició transferencia en {self.server_id}"
            )

            with path.open("rb") as source:
                for seq in range(total_chunks):
                    if self.shutdown_event.is_set() or session.cancel_event.is_set():
                        self._send_json(
                            {
                                "type": "stream_cancelled",
                                "request_id": session.request_id,
                                "session_id": session_id,
                                "server_id": self.server_id,
                            },
                            client,
                        )
                        return

                    payload = source.read(CHUNK_SIZE)
                    packet = pack_audio_chunk(session_bytes, seq, total_chunks, payload)
                    acknowledged = False

                    for attempt in range(1, max_retries + 1):
                        if self.shutdown_event.is_set() or session.cancel_event.is_set():
                            return

                        self._send_packet(packet, client)

                        deadline = time.monotonic() + timeout
                        while time.monotonic() < deadline:
                            remaining = deadline - time.monotonic()
                            try:
                                ack_seq = session.ack_queue.get(timeout=max(0.001, remaining))
                            except queue.Empty:
                                break

                            if ack_seq == seq:
                                acknowledged = True
                                break

                        if acknowledged:
                            break

                        print(
                            f"  {self._client_label(client)} sesión={session_id[:8]} "
                            f"timeout seq={seq}, reintento {attempt}/{max_retries}"
                        )

                    if not acknowledged:
                        self._send_json(
                            {
                                "type": "error",
                                "request_id": session.request_id,
                                "message": (
                                    "Transferencia abortada: no llegó ACK del "
                                    f"fragmento {seq}."
                                ),
                            },
                            client,
                        )
                        return

            elapsed = time.monotonic() - session.created_at
            print(
                f"{self._client_label(client)} sesión={session_id[:8]} "
                f"transferencia completa en {self.server_id}: {path.name} ({elapsed:.2f}s)"
            )

        except OSError as exc:
            self._send_json(
                {
                    "type": "error",
                    "request_id": session.request_id,
                    "message": f"Error leyendo la canción: {exc}",
                },
                client,
            )
        finally:
            current_thread = threading.current_thread()
            with self.queue_condition:
                self.sessions.pop(session_id, None)
                if self.current_session_by_client.get(client) == session_id:
                    self.current_session_by_client.pop(client, None)
                if self.latest_request_by_client.get(client) == session.request_id:
                    self.latest_request_by_client.pop(client, None)
                self.stream_threads.discard(current_thread)
                active_sessions = len(self.sessions)

            self._release_stream_slot()
            print(
                f"{self._client_label(client)} sesión={session_id[:8]} cerrada en {self.server_id} "
                f"| sesiones activas={active_sessions} | carga={self._active_stream_count()}/{self.max_streams}"
            )

    # ------------------------------------------------------------------
    # Capacidad, socket compartido y utilidades
    # ------------------------------------------------------------------

    def _try_reserve_stream_slot(self) -> bool:
        acquired = self.stream_slots.acquire(blocking=False)
        if not acquired:
            return False
        with self.state_lock:
            self.active_stream_count += 1
        return True

    def _release_stream_slot(self) -> None:
        try:
            self.stream_slots.release()
        except ValueError:
            return
        with self.queue_condition:
            self.active_stream_count = max(0, self.active_stream_count - 1)
            self.queue_condition.notify_all()

    def _active_stream_count(self) -> int:
        with self.state_lock:
            return self.active_stream_count

    def _is_current_request(self, client: ClientAddress, request_id: str) -> bool:
        with self.state_lock:
            return self.latest_request_by_client.get(client) == request_id

    def _song_exists(self, song_id: str) -> bool:
        if not song_id:
            return False
        songs = {song.filename for song in self.library.all()}
        return song_id in songs and (self.music_dir / song_id).is_file()

    def _send_packet(self, data: bytes, destination: ClientAddress) -> None:
        try:
            with self.send_lock:
                self.socket.sendto(data, destination)
        except OSError:
            pass

    def _send_json(self, message: dict[str, Any], destination: ClientAddress) -> None:
        self._send_packet(encode_json(message), destination)

    def _known_client_count(self) -> int:
        with self.state_lock:
            return len(self.known_clients)

    def _normalize_peers(self, peers: list[ClientAddress]) -> list[ClientAddress]:
        normalized: list[ClientAddress] = []
        seen: set[ClientAddress] = set()
        try:
            self_address = (socket.gethostbyname(self.advertise_host), int(self.port))
        except OSError:
            self_address = None

        for host, port in peers:
            try:
                address = (socket.gethostbyname(host), int(port))
            except (OSError, ValueError):
                continue
            if address == self_address or address in seen:
                continue
            seen.add(address)
            normalized.append(address)
        return normalized

    @staticmethod
    def _client_label(client: ClientAddress) -> str:
        return f"[{client[0]}:{client[1]}]"
