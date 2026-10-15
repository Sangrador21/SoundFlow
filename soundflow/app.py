from __future__ import annotations
import multiprocessing as mp
import os
from pathlib import Path
import queue
import shutil
import threading
import tkinter as tk
from tkinter import ttk
from typing import Any
from .models import Song
from .network_client import SoundFlowHTTPClient
from .player_process import player_process_main
from .audio import BYTES_PER_SECOND
from .utils import format_seconds


class SoundFlowApp:
    def __init__(self, base_url: str, cache_dir: Path, mp_context: mp.context.BaseContext,
                 *, verify: bool | str = True, fallbacks: list[str] | None = None) -> None:
        self.cache_dir = Path(cache_dir)
        self.shutdown = threading.Event()
        self.ui_events: queue.Queue = queue.Queue()
        self.command_queue = mp_context.Queue()
        self.player_events = mp_context.Queue()
        self.player = mp_context.Process(target=player_process_main,
                                         args=(self.command_queue, self.player_events),
                                         name='soundflow-player', daemon=True)
        self.player.start()
        self.listener = threading.Thread(target=self._listen, name='player-events', daemon=True)
        self.listener.start()
        self.network = SoundFlowHTTPClient(base_url, cache_dir, self.ui_events,
                                           verify=verify, fallbacks=fallbacks)
        self.songs: list[Song] = []
        self.filtered: list[Song] = []
        self.upcoming: list[Song] = []
        self.history: list[Song] = []
        self.current: Song | None = None
        self.playback_id = ''
        self.playing = self.paused = self.waiting = False
        self.position = 0.0
        self.dragging = False
        self.audio_ready = False
        self.player_error = ''
        self.queue_shown = False
        self.root = tk.Tk()
        self.root.title('SoundFlow P06 · Streaming HTTP/HTTPS')
        self.root.geometry('1100x740')
        self.root.minsize(920, 650)
        self.root.protocol('WM_DELETE_WINDOW', self._close)
        self.title_var = tk.StringVar(value='Elige una canción')
        self.artist_var = tk.StringVar(value='Selecciona en el catálogo para reproducir')
        self.status_var = tk.StringVar(value='Cargando catálogo…')
        self.time_var = tk.StringVar(value='00:00 / 00:00')
        self.buffer_var = tk.StringVar(value='Audio listo para recibir')
        self.server_var = tk.StringVar(value='Entrada: ' + base_url)
        self.search_var = tk.StringVar()
        self.seek_var = tk.DoubleVar(value=0)
        self.volume_var = tk.DoubleVar(value=70)
        self.details_var = tk.BooleanVar(value=False)
        self._styles()
        self._build()
        self.root.after(60, self._poll)
        self.root.after(100, self.network.request_catalog)

    def _styles(self) -> None:
        style = ttk.Style(self.root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        self.root.configure(background='#101820')
        style.configure('.', background='#101820', foreground='#e7eef3', font=('TkDefaultFont', 11))
        style.configure('TFrame', background='#101820')
        style.configure('TLabel', background='#101820')
        style.configure('Title.TLabel', font=('TkDefaultFont', 25, 'bold'), foreground='#5bddc0')
        style.configure('Track.TLabel', font=('TkDefaultFont', 18, 'bold'))
        style.configure('Muted.TLabel', foreground='#adc0cf')
        style.configure('TButton', background='#233340', padding=(12, 9), foreground='#e7eef3')
        style.map('TButton', background=[('active', '#345362')])
        style.configure('Accent.TButton', background='#126f60', foreground='white')
        style.configure('Treeview', background='#182630', fieldbackground='#182630', foreground='#edf2f5',
                        rowheight=34, borderwidth=0)
        style.configure('Treeview.Heading', background='#233340', foreground='#adc0cf', padding=8)
        style.map('Treeview', background=[('selected', '#24554e')], foreground=[('selected', 'white')])
        style.configure('TEntry', fieldbackground='#233340', foreground='white', padding=8)
        style.configure('TScale', background='#101820', troughcolor='#233340')
        style.configure('TCheckbutton', background='#101820', foreground='#adc0cf')
        style.map('TCheckbutton', background=[('active', '#101820')])

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill='both', expand=True)
        header = ttk.Frame(outer)
        header.pack(fill='x')
        ttk.Label(header, text='SoundFlow', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='P06 · Servicios web', style='Muted.TLabel').pack(side='left', padx=18)
        self.queue_button = ttk.Button(header, text='Cola (0)', command=self._toggle_queue)
        self.queue_button.pack(side='right')
        ttk.Button(header, text='Actualizar catálogo', command=self._refresh).pack(side='right', padx=8)
        ttk.Separator(outer).pack(fill='x', pady=15)
        ttk.Label(outer, textvariable=self.title_var, style='Track.TLabel').pack(anchor='w')
        ttk.Label(outer, textvariable=self.artist_var, style='Muted.TLabel').pack(anchor='w', pady=(5, 10))
        progress = ttk.Frame(outer)
        progress.pack(fill='x')
        self.seek_scale = ttk.Scale(progress, from_=0, to=1, variable=self.seek_var)
        self.seek_scale.pack(side='left', fill='x', expand=True)
        self.seek_scale.bind('<ButtonPress-1>', lambda _: setattr(self, 'dragging', True))
        self.seek_scale.bind('<ButtonRelease-1>', self._seek_release)
        self.seek_scale.bind('<KeyRelease>', self._seek_keyboard)
        self.seek_scale.state(['disabled'])
        ttk.Label(progress, textvariable=self.time_var, width=17, anchor='e').pack(side='right', padx=(12, 0))
        controls = ttk.Frame(outer)
        controls.pack(fill='x', pady=(8, 15))
        ttk.Button(controls, text='Anterior', command=self._previous).pack(side='left')
        self.play_button = ttk.Button(controls, text='Reproducir', command=self._toggle_play, style='Accent.TButton')
        self.play_button.pack(side='left', padx=8)
        ttk.Button(controls, text='Siguiente', command=self._next).pack(side='left')
        ttk.Button(controls, text='Detener', command=self._stop).pack(side='left', padx=8)
        ttk.Scale(controls, from_=0, to=100, variable=self.volume_var,
                  command=self._volume, length=140).pack(side='right')
        ttk.Label(controls, text='Volumen', style='Muted.TLabel').pack(side='right', padx=10)
        self.content = ttk.Frame(outer)
        self.content.pack(fill='both', expand=True)
        self.content.columnconfigure(0, weight=3)
        self.content.columnconfigure(1, weight=0)
        self.content.rowconfigure(0, weight=1)
        catalog = ttk.Frame(self.content)
        catalog.grid(row=0, column=0, sticky='nsew')
        catalog.columnconfigure(0, weight=1)
        catalog.rowconfigure(2, weight=1)
        ttk.Label(catalog, text='Catálogo del clúster', style='Track.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 8))
        search_row = ttk.Frame(catalog)
        search_row.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        search_row.columnconfigure(0, weight=1)
        entry = ttk.Entry(search_row, textvariable=self.search_var)
        entry.grid(row=0, column=0, sticky='ew')
        entry.bind('<KeyRelease>', self._filter)
        ttk.Button(search_row, text='Agregar a cola', command=self._add).grid(row=0, column=1, padx=(8, 0))
        table = ttk.Frame(catalog)
        table.grid(row=2, column=0, sticky='nsew')
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.library_tree = ttk.Treeview(table, columns=('title', 'artist', 'duration'), show='headings', selectmode='extended')
        for column, label, width in [('title', 'Canción', 340), ('artist', 'Artista', 190), ('duration', 'Tiempo', 70)]:
            self.library_tree.heading(column, text=label)
            self.library_tree.column(column, width=width, minwidth=50, stretch=column != 'duration')
        self.library_tree.grid(row=0, column=0, sticky='nsew')
        self.library_tree.bind('<<TreeviewSelect>>', self._catalog_selected)
        self.library_tree.bind('<Return>', lambda _: self._play_selected())
        scrollbar = ttk.Scrollbar(table, command=self.library_tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.library_tree.configure(yscrollcommand=scrollbar.set)
        ttk.Label(catalog, text='Selecciona para escuchar · Ctrl/⌘ para seleccionar varias y agregarlas a la cola',
                  style='Muted.TLabel', wraplength=640).grid(row=3, column=0, sticky='w', pady=(8, 0))
        self.queue_panel = ttk.Frame(self.content, padding=(18, 0, 0, 0))
        self.queue_panel.grid(row=0, column=1, sticky='nsew')
        self.queue_panel.rowconfigure(1, weight=1)
        self.queue_panel.columnconfigure(0, weight=1)
        ttk.Label(self.queue_panel, text='A continuación', style='Track.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 10))
        self.queue_list = tk.Listbox(self.queue_panel, background='#182630', foreground='#edf2f5',
                                    selectbackground='#24554e', selectforeground='white',
                                    borderwidth=0, highlightthickness=0, exportselection=False,
                                    font=('TkDefaultFont', 11), width=30)
        self.queue_list.grid(row=1, column=0, sticky='nsew')
        self.queue_list.bind('<Double-Button-1>', lambda _: self._play_queue_selected())
        qbuttons = ttk.Frame(self.queue_panel)
        qbuttons.grid(row=2, column=0, sticky='ew', pady=8)
        ttk.Button(qbuttons, text='Quitar', command=self._remove).pack(side='left')
        ttk.Button(qbuttons, text='Vaciar', command=self._clear).pack(side='left', padx=8)
        self.queue_panel.grid_remove()
        ttk.Separator(outer).pack(fill='x', pady=(14, 9))
        ttk.Label(outer, textvariable=self.status_var, style='Muted.TLabel', wraplength=1000).pack(anchor='w')
        ttk.Label(outer, textvariable=self.buffer_var, style='Muted.TLabel').pack(anchor='w', pady=4)
        ttk.Checkbutton(outer, text='Detalles de conexión', variable=self.details_var, command=self._toggle_details).pack(anchor='w')
        self.details = ttk.Frame(outer)
        ttk.Label(self.details, textvariable=self.server_var, style='Muted.TLabel', wraplength=1000).pack(anchor='w')
        ttk.Label(self.details, text=f'GUI PID {os.getpid()} · Proceso de audio {self.player.pid} · Peticiones HTTP en hilos',
                  style='Muted.TLabel').pack(anchor='w')

    def _toggle_details(self):
        if self.details_var.get():
            self.details.pack(fill='x', pady=5)
        else:
            self.details.pack_forget()

    def _refresh(self):
        self.status_var.set('Consultando catálogos de los servidores…')
        self.network.request_catalog()

    def _filter(self, _event=None):
        query = self.search_var.get().strip().casefold()
        self.filtered = [song for song in self.songs if not query or query in
                         f'{song.title} {song.artist} {song.filename}'.casefold()]
        self.library_tree.delete(*self.library_tree.get_children())
        for index, song in enumerate(self.filtered):
            self.library_tree.insert('', 'end', iid=str(index), values=(song.title, song.artist, format_seconds(song.duration)))

    def _selected_songs(self) -> list[Song]:
        return [self.filtered[int(i)] for i in self.library_tree.selection() if int(i) < len(self.filtered)]

    def _catalog_selected(self, _event=None):
        selected = self._selected_songs()
        if len(selected) == 1 and (self.current is None or selected[0].id != self.current.id
                                   or (not self.playing and not self.waiting)):
            self._start(selected[0])

    def _play_selected(self):
        selected = self._selected_songs()
        if selected:
            self._start(selected[0])

    def _show_queue(self, show: bool):
        self.queue_shown = show
        if show:
            self.content.columnconfigure(1, weight=1)
            self.queue_panel.grid()
        else:
            self.queue_panel.grid_remove()
            self.content.columnconfigure(1, weight=0)

    def _toggle_queue(self):
        self._show_queue(not self.queue_shown)

    def _render_queue(self):
        self.queue_list.delete(0, tk.END)
        for index, song in enumerate(self.upcoming):
            self.queue_list.insert(tk.END, f'{index + 1}. {song.display_name}')
        self.queue_button.configure(text=f'Cola ({len(self.upcoming)})')
        if not self.upcoming:
            self._show_queue(False)

    def _add(self):
        songs = self._selected_songs()
        if not songs:
            return
        self.upcoming.extend(songs)
        self._render_queue()
        self._show_queue(True)
        self.status_var.set(f'{len(songs)} canción(es) agregada(s) a continuación.')
        if self.current is None:
            self._next()

    def _remove(self):
        selection = self.queue_list.curselection()
        if selection:
            self.upcoming.pop(selection[0])
            self._render_queue()

    def _clear(self):
        self.upcoming.clear()
        self._render_queue()
        self.status_var.set('Cola vacía. La canción actual continúa.')

    def _play_queue_selected(self):
        selection = self.queue_list.curselection()
        if selection:
            song = self.upcoming.pop(selection[0])
            self._render_queue()
            self._start(song)

    def _command(self, kind, **data):
        self.command_queue.put({'type': kind, 'playback_id': self.playback_id, **data})

    def _start(self, song: Song, start: float = 0, remember: bool = True):
        if self.player_error:
            self.status_var.set('Audio no disponible: ' + self.player_error)
            return
        if not self.player.is_alive():
            self._player_failed('El proceso de audio terminó. Revisa la terminal del cliente y reinícialo después de corregir el entorno.')
            return
        if remember and self.current and self.current.id != song.id:
            self.history.append(self.current)
        self._command('stop')
        self.current = song
        self.position = start
        self.playing = self.paused = self.audio_ready = False
        self.waiting = True
        self.title_var.set(song.title)
        self.artist_var.set(song.artist)
        self.status_var.set(f'Solicitando audio desde {format_seconds(start)}…')
        self.buffer_var.set('Preparando búfer…')
        self.play_button.configure(text='Cargando…')
        self.seek_scale.configure(to=max(song.duration, 1))
        self.seek_scale.state(['!disabled'] if song.duration > 0 else ['disabled'])
        self.seek_var.set(start)
        self._update_time()
        self.playback_id = self.network.request_stream(song.to_dict(), start=start)

    def _seek_release(self, _event=None):
        target = float(self.seek_var.get())
        self.dragging = False
        if self.current and self.current.duration > 0:
            self._start(self.current, min(max(0, target), max(0, self.current.duration - 0.1)), remember=False)

    def _seek_keyboard(self, event):
        if event.keysym in {'Left', 'Right', 'Home', 'End'}:
            self._seek_release()

    def _toggle_play(self):
        if self.waiting:
            self.status_var.set('Esperando audio. Puedes detener o elegir otra canción.')
        elif self.paused:
            self._command('resume')
            self.paused = False
            self.play_button.configure(text='Pausar')
        elif self.playing:
            self._command('pause')
            self.paused = True
            self.play_button.configure(text='Continuar')
        elif self.current:
            self._start(self.current, remember=False)
        else:
            self._play_selected()

    def _next(self):
        if self.upcoming:
            song = self.upcoming.pop(0)
            self._render_queue()
            self._start(song)
        else:
            self.status_var.set('No hay más canciones en la cola.')

    def _previous(self):
        if self.current and self.position > 3:
            self._start(self.current, remember=False)
        elif self.history:
            previous = self.history.pop()
            if self.current:
                self.upcoming.insert(0, self.current)
                self._render_queue()
                self._show_queue(True)
            self._start(previous, remember=False)
        elif self.current:
            self._start(self.current, remember=False)

    def _stop(self):
        self.network.cancel_stream()
        self._command('stop')
        self.playback_id = ''  # Invalida eventos tardíos de la pista cancelada.
        self.playing = self.paused = self.waiting = self.audio_ready = False
        self.position = 0
        self.play_button.configure(text='Reproducir')
        self.seek_var.set(0)
        self.status_var.set('Reproducción detenida.')
        self.buffer_var.set('Audio detenido')
        self._update_time()

    def _volume(self, value):
        self.command_queue.put({'type': 'volume', 'value': float(value) / 100})

    def _listen(self):
        while not self.shutdown.is_set():
            try:
                self.ui_events.put(self.player_events.get(timeout=0.2))
            except queue.Empty:
                continue
            except (EOFError, OSError):
                break

    def _poll(self):
        for _ in range(250):
            try:
                self._event(self.ui_events.get_nowait())
            except queue.Empty:
                break
        if not self.shutdown.is_set():
            if not self.player.is_alive() and not self.player_error:
                self._player_failed(f'El proceso de audio terminó (código {self.player.exitcode}). Revisa la terminal del cliente.')
            self.root.after(60, self._poll)

    def _player_failed(self, message: str):
        self.player_error = message
        self.network.cancel_stream()
        self._command('stop')
        self.playing = self.paused = self.waiting = self.audio_ready = False
        self.play_button.configure(text='Audio no disponible', state='disabled')
        self.status_var.set('Audio no disponible: ' + message)

    def _event(self, event: dict[str, Any]):
        kind = event['type']
        # Los fallos de inicialización pertenecen al proceso, no a una canción.
        # Deben mostrarse incluso si el usuario ya seleccionó una pista.
        if kind == 'error' and not event.get('playback_id'):
            self._player_failed(event['message'])
            return
        if 'playback_id' in event and event['playback_id'] != self.playback_id:
            return
        if self.player_error and kind in {'stream_ready', 'stream_complete', 'track_started',
                                          'progress', 'track_finished', 'buffering', 'buffering_end'}:
            return
        if kind == 'catalog':
            self.songs = [Song.from_dict(item) for item in event['songs']]
            self._filter()
            if not self.player_error:
                self.status_var.set(f"{len(self.songs)} canciones · {len(event['nodes'])} servidores disponibles"
                                    + (f" · {len(event['offline'])} sin conexión" if event['offline'] else ''))
        elif kind == 'catalog_error':
            self.status_var.set(event['message'])
        elif kind == 'stream_started':
            self.server_var.set(f"Entrada: {self.network.base_url} · Audio: {event['server']} ({event['server_id']})")
        elif kind == 'stream_waiting':
            pos = event.get('position', 0)
            self.status_var.set(event['message'] + (f' Posición FIFO: {pos}.' if pos else ''))
        elif kind == 'stream_ready':
            self.audio_ready = True
            self.waiting = True
            self.playing = False
            self.play_button.configure(text='Iniciando audio…')
            self._command('play', path=event['path'], start=event['start'], duration=self.current.duration,
                          complete=event['complete'])
        elif kind == 'stream_progress':
            seconds = event['received'] / BYTES_PER_SECOND
            self.buffer_var.set(f"Audio recibido: {seconds:.1f} s · Disponible hasta {format_seconds(event['buffered_until'])}")
        elif kind == 'stream_complete':
            self._command('download_complete')
            self.buffer_var.set(f"Audio recibido completo · Disponible hasta {format_seconds(event['buffered_until'])}")
        elif kind in {'network_error', 'error'}:
            self._command('stop')
            self.playing = self.paused = self.waiting = False
            self.play_button.configure(text='Reintentar')
            self.status_var.set('No se pudo reproducir: ' + event['message'])
        elif kind == 'track_started':
            self.waiting = self.paused = False
            self.playing = True
            self.play_button.configure(text='Pausar')
            self.status_var.set('Reproduciendo desde ' + format_seconds(event['position']))
        elif kind == 'progress':
            self.position = event['position']
            if not self.dragging:
                self.seek_var.set(self.position)
                self._update_time()
        elif kind == 'buffering':
            self.status_var.set('Esperando más audio para continuar…')
        elif kind == 'buffering_end':
            self.status_var.set('Reproducción reanudada.')
        elif kind == 'track_finished':
            self.playing = self.paused = False
            self.play_button.configure(text='Reproducir')
            if self.upcoming:
                self._next()
            else:
                self.status_var.set('Canción finalizada.')
        elif kind == 'paused':
            self.status_var.set('Audio pausado.')
        elif kind == 'resumed':
            self.status_var.set('Reproduciendo.')

    def _update_time(self):
        self.time_var.set(f'{format_seconds(self.position)} / {format_seconds(self.current.duration if self.current else 0)}')

    def _close(self):
        if self.shutdown.is_set():
            return
        self.shutdown.set()
        self._command('shutdown')
        self.player.join(timeout=2)
        if self.player.is_alive():
            self.player.terminate()
            self.player.join(timeout=1)
        self.network.close()
        self.listener.join(timeout=0.5)
        self.command_queue.close()
        self.player_events.close()
        shutil.rmtree(self.cache_dir, ignore_errors=True)
        self.root.destroy()

    def run(self):
        self.root.mainloop()
