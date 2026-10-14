from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from .models import Song
from .network_client import SoundFlowUDPClient
from .player_process import player_process_main
from .protocol import BUFFER_THRESHOLD
from .utils import format_seconds


class SoundFlowApp:
    def __init__(
        self,
        server_host: str,
        server_port: int,
        cache_dir: Path,
        mp_context: mp.context.BaseContext,
    ) -> None:
        self.server_host = server_host
        self.server_port = server_port
        self.cache_dir = Path(cache_dir)
        self.mp_context = mp_context

        # P1 se conserva internamente: proceso independiente para pygame.
        self.command_queue = mp_context.Queue()
        self.player_event_queue = mp_context.Queue()
        self.player_process = mp_context.Process(
            target=player_process_main,
            args=(self.command_queue, self.player_event_queue),
            name="soundflow-player",
            daemon=True,
        )
        self.player_process.start()

        # Comunicación thread-safe hacia Tkinter.
        self.ui_event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.shutdown_event = threading.Event()

        self.status_thread = threading.Thread(
            target=self._status_listener_loop,
            name="status-listener",
            daemon=True,
        )
        self.status_thread.start()

        # Cliente UDP: crea su propio hilo udp-receiver.
        self.network = SoundFlowUDPClient(
            server_host=server_host,
            server_port=server_port,
            cache_dir=self.cache_dir,
            event_queue=self.ui_event_queue,
        )

        self.root = tk.Tk()
        self.root.title("SoundFlow P4 — Múltiples clientes / múltiples servidores UDP")
        self.root.geometry("1080x720")
        self.root.minsize(920, 620)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.songs: list[Song] = []
        self.filtered_songs: list[Song] = []
        self.playlist: list[Song] = []
        self.current_index = -1

        self.is_paused = False
        self.is_playing = False
        self.waiting_for_stream = False
        self.current_position = 0.0
        self.current_duration = 0.0
        self.transfer_percent = 0.0

        self.status_var = tk.StringVar(value="Conectando con el servidor UDP...")
        self.track_var = tk.StringVar(value="Sin reproducción")
        self.artist_var = tk.StringVar(value="Solicita el catálogo al servidor")
        self.progress_text_var = tk.StringVar(value="00:00 / 00:00")
        self.search_var = tk.StringVar()
        self.volume_var = tk.DoubleVar(value=70.0)
        self.network_var = tk.StringVar(
            value=f"Servidor de entrada: {server_host}:{server_port} | esperando socket cliente..."
        )
        self.buffer_var = tk.StringVar(
            value=f"Buffer inicial: {BUFFER_THRESHOLD // 1024} KB | Transferencia: 0%"
        )
        self.concurrency_var = tk.StringVar(
            value=(
                f"GUI PID: {os.getpid()} | Threads: MainThread, status-listener, udp-receiver | "
                f"Player PID: {self.player_process.pid or 'iniciando...'}"
            )
        )

        self._configure_styles()
        self._build_ui()
        self.root.after(80, self._poll_background_queues)
        self.root.after(150, self._request_catalog)

    def run(self) -> None:
        self.root.mainloop()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("TkDefaultFont", 20, "bold"))
        style.configure("Track.TLabel", font=("TkDefaultFont", 16, "bold"))
        style.configure("Muted.TLabel", foreground="#666666")
        style.configure("Accent.TButton", padding=(12, 8))
        style.configure("Card.TLabelframe", padding=10)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="SoundFlow", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="P4 · Múltiples clientes / múltiples servidores · UDP",
            style="Muted.TLabel",
        ).pack(side="left", padx=(12, 0), pady=(8, 0))

        ttk.Button(
            header,
            text="Actualizar catálogo",
            command=self._request_catalog,
        ).pack(side="right")

        now_frame = ttk.LabelFrame(outer, text="Reproducción actual", style="Card.TLabelframe")
        now_frame.pack(fill="x", pady=(14, 10))
        ttk.Label(now_frame, textvariable=self.track_var, style="Track.TLabel").pack(anchor="w")
        ttk.Label(now_frame, textvariable=self.artist_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 8))

        progress_row = ttk.Frame(now_frame)
        progress_row.pack(fill="x")
        self.progress = ttk.Progressbar(progress_row, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        ttk.Label(progress_row, textvariable=self.progress_text_var, width=15, anchor="e").pack(side="right", padx=(10, 0))

        controls = ttk.Frame(now_frame)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Button(controls, text="⏮ Anterior", command=self._previous_track, style="Accent.TButton").pack(side="left")
        self.play_pause_button = ttk.Button(controls, text="▶ Reproducir", command=self._toggle_play_pause, style="Accent.TButton")
        self.play_pause_button.pack(side="left", padx=8)
        ttk.Button(controls, text="⏭ Siguiente", command=self._next_track, style="Accent.TButton").pack(side="left")
        ttk.Button(controls, text="⏹ Detener", command=self._stop_track).pack(side="left", padx=(8, 0))

        volume_frame = ttk.Frame(controls)
        volume_frame.pack(side="right")
        ttk.Label(volume_frame, text="Volumen").pack(side="left")
        ttk.Scale(
            volume_frame,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.volume_var,
            command=self._on_volume_change,
            length=170,
        ).pack(side="left", padx=(8, 0))

        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(content, text="Biblioteca del servidor", style="Card.TLabelframe")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        search_row = ttk.Frame(left)
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        search_row.columnconfigure(0, weight=1)
        search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        search_entry.grid(row=0, column=0, sticky="ew")
        search_entry.bind("<KeyRelease>", self._on_search_changed)
        ttk.Button(search_row, text="Agregar a cola", command=self._add_selected_to_playlist).grid(row=0, column=1, padx=(8, 0))

        library_frame = ttk.Frame(left)
        library_frame.grid(row=1, column=0, sticky="nsew")
        library_frame.rowconfigure(0, weight=1)
        library_frame.columnconfigure(0, weight=1)
        self.library_listbox = tk.Listbox(library_frame, activestyle="dotbox", exportselection=False, font=("TkDefaultFont", 11))
        self.library_listbox.grid(row=0, column=0, sticky="nsew")
        self.library_listbox.bind("<Double-Button-1>", lambda _e: self._play_selected_library_song())
        scroll = ttk.Scrollbar(library_frame, orient="vertical", command=self.library_listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.library_listbox.configure(yscrollcommand=scroll.set)

        right = ttk.LabelFrame(content, text="Cola de reproducción", style="Card.TLabelframe")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        playlist_frame = ttk.Frame(right)
        playlist_frame.grid(row=0, column=0, columnspan=3, sticky="nsew")
        playlist_frame.rowconfigure(0, weight=1)
        playlist_frame.columnconfigure(0, weight=1)
        self.playlist_listbox = tk.Listbox(playlist_frame, activestyle="dotbox", exportselection=False, font=("TkDefaultFont", 11))
        self.playlist_listbox.grid(row=0, column=0, sticky="nsew")
        self.playlist_listbox.bind("<Double-Button-1>", lambda _e: self._play_selected_playlist_song())
        pscroll = ttk.Scrollbar(playlist_frame, orient="vertical", command=self.playlist_listbox.yview)
        pscroll.grid(row=0, column=1, sticky="ns")
        self.playlist_listbox.configure(yscrollcommand=pscroll.set)

        ttk.Button(right, text="Quitar", command=self._remove_selected_from_playlist).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(right, text="Vaciar cola", command=self._clear_playlist).grid(row=1, column=1, sticky="w", pady=(8, 0), padx=(8, 0))
        ttk.Button(right, text="Cargar catálogo completo", command=self._replace_playlist_with_library).grid(row=1, column=2, sticky="e", pady=(8, 0))

        diagnostics = ttk.LabelFrame(outer, text="Monitor Cliente/Servidor", style="Card.TLabelframe")
        diagnostics.pack(fill="x", pady=(10, 0))
        ttk.Label(diagnostics, textvariable=self.network_var).pack(anchor="w")
        ttk.Label(diagnostics, textvariable=self.buffer_var).pack(anchor="w", pady=(2, 0))
        ttk.Label(diagnostics, textvariable=self.concurrency_var).pack(anchor="w", pady=(2, 0))
        ttk.Label(diagnostics, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

    # ------------------------------------------------------------------
    # Catálogo y cola
    # ------------------------------------------------------------------

    def _request_catalog(self) -> None:
        self.status_var.set("Solicitando catálogo al servidor...")
        self.network.request_catalog()

    def _apply_catalog(self, raw_songs: list[dict[str, Any]]) -> None:
        try:
            self.songs = [Song.from_dict(item) for item in raw_songs]
        except (KeyError, TypeError, ValueError) as exc:
            self.status_var.set(f"Catálogo inválido recibido: {exc}")
            return

        self.filtered_songs = list(self.songs)
        self._render_library()
        if self.songs and not self.playlist:
            self.playlist = list(self.songs)
            self._render_playlist()
        self.status_var.set(f"Catálogo recibido por UDP: {len(self.songs)} canción(es).")

    def _render_library(self) -> None:
        self.library_listbox.delete(0, tk.END)
        for song in self.filtered_songs:
            duration = format_seconds(song.duration) if song.duration else "--:--"
            self.library_listbox.insert(tk.END, f"{song.display_name}   [{duration}]")

    def _render_playlist(self) -> None:
        self.playlist_listbox.delete(0, tk.END)
        for idx, song in enumerate(self.playlist):
            prefix = "▶ " if idx == self.current_index and self.is_playing else "   "
            self.playlist_listbox.insert(tk.END, f"{prefix}{idx + 1:02d}. {song.display_name}")
        if 0 <= self.current_index < len(self.playlist):
            self.playlist_listbox.selection_clear(0, tk.END)
            self.playlist_listbox.selection_set(self.current_index)
            self.playlist_listbox.see(self.current_index)

    def _on_search_changed(self, _event: tk.Event | None = None) -> None:
        query_text = self.search_var.get().strip().casefold()
        if not query_text:
            self.filtered_songs = list(self.songs)
        else:
            self.filtered_songs = [
                song for song in self.songs
                if query_text in song.title.casefold()
                or query_text in song.artist.casefold()
                or query_text in song.filename.casefold()
            ]
        self._render_library()

    def _add_selected_to_playlist(self) -> None:
        selection = self.library_listbox.curselection()
        if not selection:
            return
        song = self.filtered_songs[selection[0]]
        self.playlist.append(song)
        self._render_playlist()
        self.status_var.set(f"Agregada a la cola: {song.display_name}")

    def _replace_playlist_with_library(self) -> None:
        if not self.songs:
            return
        self._stop_track()
        self.current_index = -1
        self.playlist = list(self.songs)
        self._render_playlist()
        self.status_var.set("La cola se reemplazó con el catálogo del servidor.")

    def _remove_selected_from_playlist(self) -> None:
        selection = self.playlist_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index == self.current_index and (self.is_playing or self.waiting_for_stream):
            self._stop_track()
        self.playlist.pop(index)
        if self.current_index > index:
            self.current_index -= 1
        elif self.current_index >= len(self.playlist):
            self.current_index = len(self.playlist) - 1
        self._render_playlist()

    def _clear_playlist(self) -> None:
        self._stop_track()
        self.playlist.clear()
        self.current_index = -1
        self._render_playlist()
        self.status_var.set("Cola vacía.")

    # ------------------------------------------------------------------
    # Streaming y reproducción
    # ------------------------------------------------------------------

    def _play_song_at_index(self, index: int) -> None:
        if not self.playlist:
            self.status_var.set("La cola de reproducción está vacía.")
            return
        if index < 0 or index >= len(self.playlist):
            return

        # Cancela stream/reproducción anterior y solicita uno nuevo al servidor.
        self.command_queue.put({"type": "stop"})
        self.network.cancel_stream()

        self.current_index = index
        song = self.playlist[index]
        self.current_position = 0.0
        self.current_duration = song.duration
        self.is_paused = False
        self.is_playing = False
        self.waiting_for_stream = True
        self.transfer_percent = 0.0

        self.track_var.set(song.title)
        self.artist_var.set(song.artist)
        self.play_pause_button.configure(text="Buffering...")
        self.buffer_var.set(f"Buffer inicial: {BUFFER_THRESHOLD // 1024} KB | Transferencia: 0%")
        self.status_var.set(f"Solicitando '{song.display_name}' al servidor por UDP...")
        self._update_progress_widgets()
        self._render_playlist()
        self.network.request_stream(song.to_dict())

    def _start_buffered_playback(self, song_data: dict[str, Any], temp_path: str) -> None:
        if not self.waiting_for_stream:
            return
        if not (0 <= self.current_index < len(self.playlist)):
            return

        current = self.playlist[self.current_index]
        if current.filename != Path(str(song_data.get("path", ""))).name:
            return

        playable = current.to_dict()
        playable["path"] = temp_path
        self.command_queue.put({"type": "play", "song": playable})
        self.waiting_for_stream = False
        self.is_playing = True
        self.is_paused = False
        self.play_pause_button.configure(text="⏸ Pausar")
        self._render_playlist()

    def _play_selected_library_song(self) -> None:
        selection = self.library_listbox.curselection()
        if not selection:
            return
        song = self.filtered_songs[selection[0]]
        self.playlist.append(song)
        self.current_index = len(self.playlist) - 1
        self._render_playlist()
        self._play_song_at_index(self.current_index)

    def _play_selected_playlist_song(self) -> None:
        selection = self.playlist_listbox.curselection()
        if selection:
            self._play_song_at_index(selection[0])

    def _toggle_play_pause(self) -> None:
        if not self.playlist:
            self.status_var.set("Agrega canciones a la cola primero.")
            return
        if self.waiting_for_stream:
            self.status_var.set("Esperando a alcanzar el buffer mínimo de reproducción.")
            return
        if self.current_index == -1:
            self._play_song_at_index(0)
            return
        if self.is_paused:
            self.command_queue.put({"type": "resume"})
            self.is_paused = False
            self.is_playing = True
            self.play_pause_button.configure(text="⏸ Pausar")
            return
        if self.is_playing:
            self.command_queue.put({"type": "pause"})
            self.is_paused = True
            self.play_pause_button.configure(text="▶ Continuar")
            return
        self._play_song_at_index(self.current_index)

    def _next_track(self) -> None:
        if not self.playlist:
            return
        next_index = 0 if self.current_index == -1 else self.current_index + 1
        if next_index >= len(self.playlist):
            next_index = 0
        self._play_song_at_index(next_index)

    def _previous_track(self) -> None:
        if not self.playlist:
            return
        previous_index = len(self.playlist) - 1 if self.current_index <= 0 else self.current_index - 1
        self._play_song_at_index(previous_index)

    def _stop_track(self) -> None:
        try:
            self.network.cancel_stream()
        except Exception:
            pass
        self.command_queue.put({"type": "stop"})
        self.waiting_for_stream = False
        self.is_playing = False
        self.is_paused = False
        self.current_position = 0.0
        self.transfer_percent = 0.0
        if hasattr(self, "play_pause_button"):
            self.play_pause_button.configure(text="▶ Reproducir")
            self.buffer_var.set(f"Buffer inicial: {BUFFER_THRESHOLD // 1024} KB | Transferencia: 0%")
            self._update_progress_widgets()
            self._render_playlist()

    def _on_volume_change(self, raw_value: str) -> None:
        try:
            value = min(100.0, max(0.0, float(raw_value)))
        except ValueError:
            return
        self.command_queue.put({"type": "volume", "value": value / 100.0})

    # ------------------------------------------------------------------
    # Eventos de red / proceso reproductor
    # ------------------------------------------------------------------

    def _status_listener_loop(self) -> None:
        while not self.shutdown_event.is_set():
            try:
                event = self.player_event_queue.get(timeout=0.20)
            except queue.Empty:
                continue
            except (EOFError, OSError):
                break
            self.ui_event_queue.put(event)

    def _poll_background_queues(self) -> None:
        try:
            while True:
                self._handle_event(self.ui_event_queue.get_nowait())
        except queue.Empty:
            pass
        if not self.shutdown_event.is_set():
            self.root.after(80, self._poll_background_queues)

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")

        if event_type == "network_ready":
            local = event.get("local", ("0.0.0.0", 0))
            server = event.get("server", (self.server_host, self.server_port))
            self.network_var.set(
                f"Cliente UDP: {local[0]}:{local[1]}  →  Servidor: {server[0]}:{server[1]} | SOCK_DGRAM"
            )

        elif event_type == "catalog":
            self._apply_catalog(list(event.get("songs", [])))

        elif event_type == "network_server_changed":
            server = event.get("server", (self.server_host, self.server_port))
            from_id = event.get("from_server_id", "servidor anterior")
            target_id = event.get("target_server_id", f"{server[0]}:{server[1]}")
            self.network_var.set(
                f"Cliente UDP: socket dinámico  →  Servidor activo: {server[0]}:{server[1]} "
                f"({target_id}) | balanceo desde {from_id}"
            )
            self.status_var.set(
                f"Servidor ocupado: solicitud reasignada a {target_id}."
            )

        elif event_type == "stream_started":
            size = int(event.get("file_size", 0))
            chunks = int(event.get("total_chunks", 0))
            server = event.get("server", (self.server_host, self.server_port))
            server_id = event.get("server_id") or f"{server[0]}:{server[1]}"
            self.network_var.set(
                f"Cliente UDP  →  Servidor activo: {server[0]}:{server[1]} ({server_id}) | SOCK_DGRAM"
            )
            self.status_var.set(
                f"Stream iniciado en {server_id}: {chunks} fragmentos, {size / 1024:.1f} KB."
            )

        elif event_type == "stream_progress":
            self.transfer_percent = float(event.get("percent", 0.0))
            received = int(event.get("received", 0))
            total = int(event.get("total", 0))
            self.buffer_var.set(
                f"Buffer inicial: {BUFFER_THRESHOLD // 1024} KB | "
                f"Recibido: {received / 1024:.1f}/{max(total, 1) / 1024:.1f} KB ({self.transfer_percent:.0f}%)"
            )

        elif event_type == "stream_ready":
            buffered = int(event.get("buffered", 0))
            threshold = int(event.get("threshold", 0))
            self.status_var.set(
                f"Umbral alcanzado ({buffered / 1024:.1f} KB; mínimo {threshold / 1024:.1f} KB). Iniciando audio..."
            )
            self._start_buffered_playback(dict(event.get("song", {})), str(event.get("path", "")))

        elif event_type == "stream_complete":
            self.transfer_percent = 100.0
            self.buffer_var.set(
                f"Buffer inicial: {BUFFER_THRESHOLD // 1024} KB | Transferencia completada: 100%"
            )
            if self.waiting_for_stream:
                self._start_buffered_playback(dict(event.get("song", {})), str(event.get("path", "")))
            else:
                self.status_var.set("Transferencia UDP completada; la reproducción continúa localmente.")

        elif event_type == "network_status":
            self.status_var.set(str(event.get("message", "")))

        elif event_type == "network_error":
            self.waiting_for_stream = False
            self.is_playing = False
            self.play_pause_button.configure(text="▶ Reproducir")
            messagebox.showerror("Error de red", str(event.get("message", "Error de comunicación UDP")))

        elif event_type == "player_ready":
            self.concurrency_var.set(
                f"GUI PID: {os.getpid()} | Threads: MainThread, status-listener, udp-receiver | "
                f"Player PID: {event.get('pid')} | Thread player: {event.get('thread')}"
            )

        elif event_type == "track_started":
            self.is_playing = True
            self.status_var.set("Reproduciendo audio recibido desde el servidor.")

        elif event_type == "progress":
            self.current_position = float(event.get("position", 0.0))
            duration = float(event.get("duration", 0.0))
            if duration > 0:
                self.current_duration = duration
            self._update_progress_widgets()

        elif event_type == "track_finished":
            self.is_playing = False
            self.is_paused = False
            self.status_var.set("Canción finalizada. Solicitando siguiente...")
            self._next_track()

        elif event_type == "paused":
            self.status_var.set("Audio pausado.")

        elif event_type == "resumed":
            self.status_var.set("Audio reanudado.")

        elif event_type == "stopped":
            if not self.waiting_for_stream:
                self.status_var.set("Reproducción detenida.")

        elif event_type == "error":
            self.is_playing = False
            self.is_paused = False
            self.play_pause_button.configure(text="▶ Reproducir")
            messagebox.showerror("Error de reproducción", str(event.get("message", "Error desconocido")))

    def _update_progress_widgets(self) -> None:
        duration = self.current_duration
        position = self.current_position
        percentage = min(100.0, max(0.0, (position / duration) * 100.0)) if duration > 0 else 0.0
        self.progress.configure(value=percentage)
        self.progress_text_var.set(f"{format_seconds(position)} / {format_seconds(duration)}")

    # ------------------------------------------------------------------
    # Cierre ordenado
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        self.shutdown_event.set()
        try:
            self.network.close()
        except Exception:
            pass
        try:
            self.command_queue.put({"type": "shutdown"})
        except Exception:
            pass

        if self.player_process.is_alive():
            self.player_process.join(timeout=2.0)
        if self.player_process.is_alive():
            self.player_process.terminate()
            self.player_process.join(timeout=1.0)

        self.status_thread.join(timeout=0.5)
        try:
            self.command_queue.close()
            self.player_event_queue.close()
        except Exception:
            pass
        self.root.destroy()
