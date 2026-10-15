"""Proceso de audio: consume PCM incremental sin confundir EOF temporal con final.

Adelantar se implementa creando otra solicitud HTTP desde el segundo indicado;
el proceso recibe un nuevo playback_id y un búfer que empieza en ese instante.
"""
from __future__ import annotations
import os
import queue
import time
from typing import Any
import pygame
from .audio import SAMPLE_RATE, CHANNELS, FRAME_BYTES


def player_process_main(command_queue, event_queue) -> None:
    def emit(kind: str, **data):
        event_queue.put({'type': kind, 'pid': os.getpid(), 'playback_id': playback_id, **data})

    playback_id = ''
    try:
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=CHANNELS,
                          buffer=1024, allowedchanges=0)
        channel = pygame.mixer.Channel(0)
    except Exception as exc:
        emit('error', message=f'No fue posible inicializar el audio: {exc}')
        return

    handle = None
    volume = 0.7
    channel.set_volume(volume)
    active = paused = complete = stalled = False
    base = duration = played = 0.0
    current = next_sound = None
    current_length = next_length = 0.0
    began = paused_at = 0.0
    last_progress = 0.0
    piece_size = int(SAMPLE_RATE * 0.25) * FRAME_BYTES
    emit('player_ready')

    def stop():
        nonlocal handle, active, current, next_sound, played, paused, stalled
        channel.stop()
        if handle:
            handle.close()
        handle = None
        active = paused = stalled = False
        current = next_sound = None
        played = 0

    def read_piece():
        if not handle:
            return None, 0.0
        data = handle.read(piece_size)
        # El escritor siempre publica muestras completas.
        if not data:
            return None, 0.0
        return pygame.mixer.Sound(buffer=data), len(data) / (SAMPLE_RATE * FRAME_BYTES)

    try:
        running = True
        while running:
            for _ in range(100):
                try:
                    command: dict[str, Any] = command_queue.get_nowait()
                except queue.Empty:
                    break
                kind = command.get('type')
                if kind == 'shutdown':
                    running = False
                    break
                if kind == 'volume':
                    volume = min(1.0, max(0.0, float(command['value'])))
                    channel.set_volume(volume)
                    continue
                if kind == 'play':
                    stop()
                    playback_id = command['playback_id']
                    try:
                        handle = open(command['path'], 'rb')
                        base, duration = float(command['start']), float(command['duration'])
                        complete = bool(command.get('complete', False))
                        active = True
                        current_length = next_length = 0
                        emit('track_started', position=base, duration=duration)
                    except OSError as exc:
                        emit('error', message=str(exc))
                    continue
                if command.get('playback_id') != playback_id:
                    continue
                if kind == 'stop':
                    stop()
                    emit('stopped')
                elif kind == 'download_complete':
                    complete = True
                elif kind == 'pause' and active and not paused:
                    channel.pause()
                    paused_at = time.monotonic()
                    paused = True
                    emit('paused')
                elif kind == 'resume' and active and paused:
                    channel.unpause()
                    began += time.monotonic() - paused_at
                    paused = False
                    emit('resumed')

            now = time.monotonic()
            if active and not paused:
                actual = channel.get_sound()
                if current is not None and actual is not current:
                    played += current_length
                    current = next_sound if actual is next_sound else None
                    current_length = next_length if current is not None else 0.0
                    next_sound, next_length = None, 0.0
                    began = now
                if current is None:
                    current, current_length = read_piece()
                    if current is not None:
                        channel.play(current)
                        began = now
                        if stalled:
                            emit('buffering_end')
                        stalled = False
                    elif complete:
                        active = False
                        emit('progress', position=base + played, duration=duration)
                        emit('track_finished')
                    elif not stalled:
                        stalled = True
                        emit('buffering')
                if current is not None and next_sound is None:
                    next_sound, next_length = read_piece()
                    if next_sound is not None:
                        channel.queue(next_sound)
                if active and now - last_progress >= 0.2:
                    partial = min(current_length, max(0, now - began)) if current is not None else 0
                    emit('progress', position=base + played + partial, duration=duration)
                    last_progress = now
            time.sleep(0.01)
    except Exception as exc:
        emit('error', message=f'Error de reproducción: {exc}')
    finally:
        stop()
        pygame.mixer.quit()
        emit('player_stopped')
