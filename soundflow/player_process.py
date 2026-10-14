from __future__ import annotations

import os
import queue
import threading
import time
from multiprocessing.queues import Queue
from typing import Any

import pygame


def _safe_put(event_queue: Queue, event: dict[str, Any]) -> None:
    try:
        event_queue.put(event)
    except Exception:
        pass


def player_process_main(command_queue: Queue, event_queue: Queue) -> None:
    """
    Proceso independiente encargado del audio.

    IPC:
      - command_queue: GUI -> reproductor
      - event_queue: reproductor -> GUI

    Además crea un hilo monitor dentro del propio proceso para reportar periódicamente el progreso de reproducción.
    """
    pid = os.getpid()
    shutdown_event = threading.Event()
    state_lock = threading.Lock()

    state: dict[str, Any] = {
        "current": None,
        "paused": False,
        "playing": False,
        "volume": 0.70,
    }

    try:
        pygame.mixer.init()
    except Exception as exc:
        _safe_put(
            event_queue,
            {
                "type": "error",
                "message": f"No fue posible inicializar el audio: {exc}",
                "pid": pid,
            },
        )
        return

    pygame.mixer.music.set_volume(state["volume"])

    def monitor_playback() -> None:
        """Hilo que monitorea progreso y finalización de la canción."""
        last_progress_emit = 0.0
        finished_reported = False

        while not shutdown_event.is_set():
            now = time.monotonic()

            with state_lock:
                current = state["current"]
                paused = bool(state["paused"])
                playing = bool(state["playing"])

            if current is not None and playing:
                busy = bool(pygame.mixer.music.get_busy())

                if not paused and busy:
                    finished_reported = False
                    if now - last_progress_emit >= 0.25:
                        pos_ms = pygame.mixer.music.get_pos()
                        position = max(0.0, pos_ms / 1000.0) if pos_ms >= 0 else 0.0

                        _safe_put(
                            event_queue,
                            {
                                "type": "progress",
                                "position": position,
                                "duration": float(current.get("duration", 0.0) or 0.0),
                                "pid": pid,
                                "thread": threading.current_thread().name,
                            },
                        )
                        last_progress_emit = now

                elif not paused and not busy and not finished_reported:
                    # SDL_mixer puede tardar un pequeño instante en marcar busy=True
                    # justo después de play(); evitamos declarar final inmediato.
                    time.sleep(0.08)
                    if not pygame.mixer.music.get_busy():
                        finished_reported = True
                        with state_lock:
                            state["playing"] = False

                        _safe_put(
                            event_queue,
                            {
                                "type": "track_finished",
                                "song": current,
                                "pid": pid,
                                "thread": threading.current_thread().name,
                            },
                        )

            time.sleep(0.05)

    monitor_thread = threading.Thread(
        target=monitor_playback,
        name="player-monitor",
        daemon=True,
    )
    monitor_thread.start()

    _safe_put(
        event_queue,
        {
            "type": "player_ready",
            "pid": pid,
            "thread": monitor_thread.name,
        },
    )

    try:
        while not shutdown_event.is_set():
            try:
                command = command_queue.get(timeout=0.20)
            except queue.Empty:
                continue

            command_type = command.get("type")

            if command_type == "play":
                song = command.get("song")
                if not song:
                    continue

                path = song.get("path")
                if not path or not os.path.exists(path):
                    _safe_put(
                        event_queue,
                        {
                            "type": "error",
                            "message": f"El archivo no existe: {path}",
                            "pid": pid,
                        },
                    )
                    continue

                try:
                    pygame.mixer.music.stop()
                    pygame.mixer.music.load(path)
                    pygame.mixer.music.set_volume(float(state["volume"]))
                    pygame.mixer.music.play()

                    with state_lock:
                        state["current"] = song
                        state["paused"] = False
                        state["playing"] = True

                    _safe_put(
                        event_queue,
                        {
                            "type": "track_started",
                            "song": song,
                            "pid": pid,
                        },
                    )
                except Exception as exc:
                    _safe_put(
                        event_queue,
                        {
                            "type": "error",
                            "message": f"No se pudo reproducir '{path}': {exc}",
                            "pid": pid,
                        },
                    )

            elif command_type == "pause":
                pygame.mixer.music.pause()
                with state_lock:
                    state["paused"] = True

                _safe_put(event_queue, {"type": "paused", "pid": pid})

            elif command_type == "resume":
                pygame.mixer.music.unpause()
                with state_lock:
                    state["paused"] = False
                    if state["current"] is not None:
                        state["playing"] = True

                _safe_put(event_queue, {"type": "resumed", "pid": pid})

            elif command_type == "stop":
                pygame.mixer.music.stop()
                with state_lock:
                    state["playing"] = False
                    state["paused"] = False

                _safe_put(event_queue, {"type": "stopped", "pid": pid})

            elif command_type == "volume":
                value = float(command.get("value", 0.70))
                value = min(1.0, max(0.0, value))
                pygame.mixer.music.set_volume(value)

                with state_lock:
                    state["volume"] = value

                _safe_put(
                    event_queue,
                    {"type": "volume_changed", "value": value, "pid": pid},
                )

            elif command_type == "shutdown":
                shutdown_event.set()

    finally:
        shutdown_event.set()
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except Exception:
            pass

        monitor_thread.join(timeout=1.0)

        _safe_put(
            event_queue,
            {
                "type": "player_stopped",
                "pid": pid,
            },
        )
