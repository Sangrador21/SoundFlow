from __future__ import annotations
import multiprocessing as mp
import time
from soundflow.audio import BYTES_PER_SECOND
from soundflow.player_process import player_process_main


def wait_event(events, kind, timeout=5, identifier=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event = events.get(timeout=max(0.1, deadline - time.monotonic()))
        if event['type'] == 'error':
            raise AssertionError(event)
        if event['type'] == kind and (identifier is None or event.get('playback_id') == identifier):
            return event
    raise AssertionError(f'No llegó {kind}')


def test_incremental_audio_pause_underflow_and_finish(tmp_path, monkeypatch):
    monkeypatch.setenv('SDL_AUDIODRIVER', 'dummy')
    context = mp.get_context('spawn')
    commands, events = context.Queue(), context.Queue()
    process = context.Process(target=player_process_main, args=(commands, events))
    process.start()
    path = tmp_path / 'buffer.pcm'
    path.write_bytes(b'\0' * int(0.5 * BYTES_PER_SECOND))
    try:
        wait_event(events, 'player_ready')
        commands.put({'type': 'play', 'playback_id': 'A', 'path': str(path), 'start': 10,
                      'duration': 20, 'complete': False})
        wait_event(events, 'track_started', identifier='A')
        wait_event(events, 'buffering', identifier='A')
        commands.put({'type': 'pause', 'playback_id': 'A'})
        wait_event(events, 'paused', identifier='A')
        with path.open('ab') as handle:
            handle.write(b'\0' * int(0.75 * BYTES_PER_SECOND))
        commands.put({'type': 'download_complete', 'playback_id': 'A'})
        time.sleep(0.1)
        commands.put({'type': 'resume', 'playback_id': 'A'})
        wait_event(events, 'resumed', identifier='A')
        wait_event(events, 'buffering_end', identifier='A')
        result = wait_event(events, 'progress', identifier='A')
        assert result['position'] >= 10.5
        wait_event(events, 'track_finished', identifier='A')
        commands.put({'type': 'play', 'playback_id': 'B', 'path': str(path), 'start': 3,
                      'duration': 20, 'complete': True})
        wait_event(events, 'track_started', identifier='B')
        commands.put({'type': 'stop', 'playback_id': 'A'})
        wait_event(events, 'track_finished', identifier='B')
    finally:
        commands.put({'type': 'shutdown'})
        process.join(3)
        if process.is_alive():
            process.terminate()
            process.join()
        assert process.exitcode == 0
