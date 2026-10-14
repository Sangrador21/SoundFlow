from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
import socket
import threading
import uuid
from typing import Any

from .protocol import BUFFER_THRESHOLD, decode_json, encode_json, unpack_audio_chunk


ServerAddress = tuple[str, int]


@dataclass
class _TransferState:
    session_id: str
    session_bytes: bytes
    request_id: str
    server: ServerAddress
    song: dict[str, Any]
    path: Path
    file_size: int
    total_chunks: int
    file_handle: Any
    expected_seq: int = 0
    received_bytes: int = 0
    ready_emitted: bool = False


class SoundFlowUDPClient:

    MAX_REDIRECTS = 8

    def __init__(
        self,
        server_host: str,
        server_port: int,
        cache_dir: Path,
        event_queue: queue.Queue[dict[str, Any]],
    ) -> None:
        self.server_lock = threading.RLock()
        self.send_lock = threading.Lock()
        self.request_lock = threading.RLock()
        self.server = self._resolve_server(server_host, server_port)
        self.entry_server = self.server

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.event_queue = event_queue

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("0.0.0.0", 0))
        self.socket.settimeout(0.25)

        self.shutdown_event = threading.Event()
        self.transfer_lock = threading.Lock()
        self.transfer: _TransferState | None = None

        self.pending_request_id: str | None = None
        self.pending_song: dict[str, Any] | None = None
        self.visited_server_ids: list[str] = []
        self.redirect_count = 0

        self.thread = threading.Thread(
            target=self._receive_loop,
            name="udp-receiver",
            daemon=True,
        )
        self.thread.start()

    @property
    def local_address(self) -> tuple[str, int]:
        host, port = self.socket.getsockname()
        return str(host), int(port)

    @property
    def current_server(self) -> ServerAddress:
        with self.server_lock:
            return self.server

    def request_catalog(self) -> None:
        self._send_json({"type": "catalog_request"})

    def request_stream(self, song: dict[str, Any]) -> None:
        self.cancel_stream()

        request_id = str(uuid.uuid4())
        with self.request_lock:
            self.pending_request_id = request_id
            self.pending_song = dict(song)
            self.visited_server_ids = []
            self.redirect_count = 0

        self._send_pending_stream_request()
        self.event_queue.put(
            {
                "type": "network_status",
                "message": f"Solicitando: {song.get('title', song.get('path', 'canción'))}",
            }
        )

    def cancel_stream(self) -> None:
        with self.transfer_lock:
            state = self.transfer
            session_id = state.session_id if state else None
            stream_server = state.server if state else None
            self._close_transfer_locked(remove_partial=True)

        with self.request_lock:
            request_id = self.pending_request_id
            self.pending_request_id = None
            self.pending_song = None
            self.visited_server_ids = []
            self.redirect_count = 0

        if session_id and stream_server:
            self._send_json(
                {"type": "cancel_stream", "session_id": session_id},
                server=stream_server,
            )
        if request_id:
            self._send_json({"type": "cancel_request", "request_id": request_id})

    def close(self) -> None:
        self.cancel_stream()
        self._send_json({"type": "disconnect"})
        self.shutdown_event.set()
        self.thread.join(timeout=1.0)
        try:
            self.socket.close()
        except OSError:
            pass

    def _send_pending_stream_request(self) -> None:
        with self.request_lock:
            request_id = self.pending_request_id
            song = dict(self.pending_song) if self.pending_song else None
            visited = list(self.visited_server_ids)
        if not request_id or not song:
            return

        self._send_json(
            {
                "type": "stream_request",
                "request_id": request_id,
                "song_id": str(song.get("path", "")),
                "visited_server_ids": visited,
            }
        )

    def _send_json(
        self,
        message: dict[str, Any],
        *,
        server: ServerAddress | None = None,
    ) -> None:
        destination = server or self.current_server
        try:
            with self.send_lock:
                self.socket.sendto(encode_json(message), destination)
        except OSError as exc:
            self.event_queue.put({"type": "network_error", "message": str(exc)})

    def _receive_loop(self) -> None:
        self.event_queue.put(
            {
                "type": "network_ready",
                "server": self.current_server,
                "local": self.local_address,
            }
        )
        while not self.shutdown_event.is_set():
            try:
                data, address = self.socket.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            if not self._is_allowed_sender(address):
                continue

            chunk = unpack_audio_chunk(data)
            if chunk is not None:
                self._handle_audio_chunk(address, *chunk)
                continue

            message = decode_json(data)
            if message is not None:
                self._handle_control(message, address)

    def _is_allowed_sender(self, address: ServerAddress) -> bool:
        allowed = {self.current_server}
        with self.transfer_lock:
            if self.transfer is not None:
                allowed.add(self.transfer.server)
        return address in allowed

    def _handle_control(self, message: dict[str, Any], source: ServerAddress) -> None:
        msg_type = message.get("type")

        if msg_type == "catalog":
            self.event_queue.put(
                {
                    "type": "catalog",
                    "songs": message.get("songs", []),
                    "server_id": message.get("server_id"),
                }
            )

        elif msg_type == "redirect":
            self._handle_redirect(message, source)

        elif msg_type == "stream_queued":
            request_id = str(message.get("request_id", ""))
            with self.request_lock:
                if request_id != self.pending_request_id:
                    return
            self.event_queue.put(
                {
                    "type": "network_status",
                    "message": str(
                        message.get(
                            "message",
                            "Solicitud en espera de capacidad disponible.",
                        )
                    ),
                }
            )

        elif msg_type == "stream_start":
            self._begin_transfer(message, source)

        elif msg_type == "stream_cancelled":
            self.event_queue.put(
                {
                    "type": "network_status",
                    "message": "Transferencia cancelada por el servidor.",
                }
            )

        elif msg_type == "error":
            request_id = str(message.get("request_id", ""))
            with self.request_lock:
                if request_id and self.pending_request_id and request_id != self.pending_request_id:
                    return
                if request_id == self.pending_request_id:
                    self.pending_request_id = None
                    self.pending_song = None
            self.event_queue.put(
                {
                    "type": "network_error",
                    "message": str(message.get("message", "Error del servidor")),
                }
            )

        elif msg_type == "pong":
            self.event_queue.put(
                {
                    "type": "network_status",
                    "message": (
                        f"Servidor {message.get('server_id', source)} disponible "
                        f"({message.get('active_streams', '?')}/{message.get('capacity', '?')} streams)."
                    ),
                }
            )

    def _handle_redirect(self, message: dict[str, Any], source: ServerAddress) -> None:
        request_id = str(message.get("request_id", ""))
        with self.request_lock:
            if request_id != self.pending_request_id or self.pending_song is None:
                return
            if self.redirect_count >= self.MAX_REDIRECTS:
                self.pending_request_id = None
                self.pending_song = None
                self.event_queue.put(
                    {
                        "type": "network_error",
                        "message": "Se alcanzó el máximo de redirecciones entre servidores.",
                    }
                )
                return

            try:
                target = self._resolve_server(str(message["host"]), int(message["port"]))
            except (KeyError, TypeError, ValueError, OSError):
                self.event_queue.put(
                    {"type": "network_error", "message": "Redirección de servidor inválida."}
                )
                return

            visited = message.get("visited_server_ids", [])
            self.visited_server_ids = [str(item) for item in visited if isinstance(item, str)]
            self.redirect_count += 1

        with self.server_lock:
            self.server = target

        self.event_queue.put(
            {
                "type": "network_server_changed",
                "server": target,
                "from_server_id": message.get("from_server_id"),
                "target_server_id": message.get("target_server_id"),
                "reason": message.get("reason"),
            }
        )
        self._send_pending_stream_request()

    def _begin_transfer(self, message: dict[str, Any], source: ServerAddress) -> None:
        request_id = str(message.get("request_id", ""))
        with self.request_lock:
            if request_id and self.pending_request_id and request_id != self.pending_request_id:
                return
            self.pending_request_id = None
            self.pending_song = None
            self.visited_server_ids = []
            self.redirect_count = 0

        session_id = str(message["session_id"])
        song = dict(message["song"])
        total_chunks = int(message["total_chunks"])
        file_size = int(message["file_size"])
        suffix = Path(str(song.get("path", "audio.mp3"))).suffix or ".bin"
        safe_name = f"stream_{session_id}{suffix}"
        path = self.cache_dir / safe_name

        with self.transfer_lock:
            self._close_transfer_locked(remove_partial=True)
            handle = path.open("wb")
            self.transfer = _TransferState(
                session_id=session_id,
                session_bytes=uuid.UUID(session_id).bytes,
                request_id=request_id,
                server=source,
                song=song,
                path=path,
                file_size=file_size,
                total_chunks=total_chunks,
                file_handle=handle,
            )

        self.event_queue.put(
            {
                "type": "stream_started",
                "server": source,
                "server_id": message.get("server_id"),
                "song": song,
                "file_size": file_size,
                "total_chunks": total_chunks,
                "path": str(path),
            }
        )

    def _handle_audio_chunk(
        self,
        source: ServerAddress,
        session_bytes: bytes,
        seq: int,
        total: int,
        payload: bytes,
    ) -> None:
        with self.transfer_lock:
            state = self.transfer
            if state is None or state.session_bytes != session_bytes or state.server != source:
                return

            if seq == state.expected_seq:
                state.file_handle.write(payload)
                state.file_handle.flush()
                state.received_bytes += len(payload)
                state.expected_seq += 1
            elif seq < state.expected_seq:
                # ACK perdido: el servidor retransmitió un paquete ya escrito.
                pass
            else:
                # Stop-and-Wait: no se aceptan fragmentos futuros.
                return

            self._send_json(
                {"type": "ack", "session_id": state.session_id, "seq": seq},
                server=state.server,
            )

            percent = (
                state.received_bytes / state.file_size * 100.0
                if state.file_size
                else 100.0
            )
            self.event_queue.put(
                {
                    "type": "stream_progress",
                    "received": state.received_bytes,
                    "total": state.file_size,
                    "percent": min(100.0, percent),
                }
            )

            threshold = min(BUFFER_THRESHOLD, state.file_size)
            if not state.ready_emitted and state.received_bytes >= threshold:
                state.ready_emitted = True
                self.event_queue.put(
                    {
                        "type": "stream_ready",
                        "song": state.song,
                        "path": str(state.path),
                        "buffered": state.received_bytes,
                        "threshold": threshold,
                    }
                )

            if state.expected_seq >= state.total_chunks:
                state.file_handle.close()
                if not state.ready_emitted:
                    state.ready_emitted = True
                    self.event_queue.put(
                        {
                            "type": "stream_ready",
                            "song": state.song,
                            "path": str(state.path),
                            "buffered": state.received_bytes,
                            "threshold": threshold,
                        }
                    )
                self.event_queue.put(
                    {
                        "type": "stream_complete",
                        "song": state.song,
                        "path": str(state.path),
                        "bytes": state.received_bytes,
                    }
                )
                self.transfer = None

    def _close_transfer_locked(self, remove_partial: bool) -> None:
        state = self.transfer
        self.transfer = None
        if state is None:
            return
        try:
            state.file_handle.close()
        except Exception:
            pass
        if remove_partial:
            try:
                state.path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _resolve_server(host: str, port: int) -> ServerAddress:
        return socket.gethostbyname(host), int(port)
