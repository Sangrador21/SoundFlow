"""Pruebas de acciones de interfaz sin necesitar un servidor gráfico."""
from collections import deque
from unittest.mock import Mock
import queue
import pytest
from soundflow.app import SoundFlowApp
from soundflow.models import Song


@pytest.fixture
def app():
    instance = SoundFlowApp.__new__(SoundFlowApp)
    instance.current = None
    instance.upcoming = []
    instance.history = []
    instance.filtered = [Song('one.wav', 'Uno', 'Prueba', 12, 'a' * 64),
                         Song('two.wav', 'Dos', 'Prueba', 12, 'b' * 64)]
    instance.playback_id = ''
    instance.command_queue = queue.Queue()
    instance.network = Mock()
    instance.player = Mock()
    instance.player.is_alive.return_value = True
    instance.player_error = ''
    instance.network.request_stream.return_value = 'new-request'
    instance.playing = instance.paused = instance.waiting = instance.audio_ready = False
    instance.position = 0
    instance.dragging = False
    instance.queue_shown = False
    for name in ['title_var', 'artist_var', 'status_var', 'buffer_var', 'play_button',
                 'seek_scale', 'seek_var', 'time_var', 'queue_list', 'queue_button',
                 'queue_panel', 'content', 'library_tree']:
        setattr(instance, name, Mock())
    return instance


def test_select_catalog_plays_without_requiring_playlist(app):
    app.library_tree.selection.return_value = ('0',)
    app._catalog_selected()
    assert app.current == app.filtered[0]
    assert app.upcoming == []
    assert app.waiting is True
    app.network.request_stream.assert_called_once_with(app.current.to_dict(), start=0)
    assert app.queue_shown is False


def test_add_multiple_tracks_opens_queue_and_clear_keeps_current(app):
    app.current = app.filtered[0]
    app.library_tree.selection.return_value = ('0', '1')
    app._add()
    assert len(app.upcoming) == 2 and app.queue_shown is True
    app._clear()
    assert app.upcoming == [] and app.current == app.filtered[0]
    assert app.queue_shown is False
    app.network.cancel_stream.assert_not_called()
    assert app.command_queue.empty()


def test_seek_sends_time_and_discards_old_ready_event(app):
    app.current = app.filtered[0]
    app.playback_id = 'old-request'
    app.seek_var.get.return_value = 5.75
    app._seek_release()
    app.network.request_stream.assert_called_once_with(app.current.to_dict(), start=5.75)
    assert app.position == 5.75
    assert app.playback_id == 'new-request'
    # Ignora datos recibidos tarde de la pista que se canceló.
    app._event({'type': 'stream_ready', 'playback_id': 'old-request', 'path': 'old.pcm'})
    assert app.waiting is True and app.audio_ready is False
    assert app.command_queue.get_nowait()['type'] == 'stop'
    assert app.command_queue.empty()


def test_finished_track_consumes_upcoming_once_and_does_not_loop(app):
    app.current = app.filtered[0]
    app.upcoming = [app.filtered[1]]
    app.playback_id = 'first'
    app._event({'type': 'track_finished', 'playback_id': 'first'})
    assert app.current == app.filtered[1] and not app.upcoming
    assert app.history == [app.filtered[0]]
    app.waiting = False
    app.playing = True
    app._event({'type': 'track_finished', 'playback_id': 'new-request'})
    assert app.playing is False and app.waiting is False
    # No segunda descarga automática cuando ya se terminó la cola.
    assert app.network.request_stream.call_count == 1


def test_initial_audio_error_is_visible_after_selecting_song(app):
    app.playback_id = 'selected-song'
    app.waiting = True
    app._event({'type': 'error', 'playback_id': '', 'message': "No module named 'pygame.mixer'"})
    assert 'pygame.mixer' in app.player_error
    assert not app.playing and not app.waiting
    app.network.cancel_stream.assert_called_once()
    app.play_button.configure.assert_called_with(text='Audio no disponible', state='disabled')
    app._event({'type': 'stream_ready', 'playback_id': 'selected-song', 'path': 'late.pcm'})
    assert app.audio_ready is False
    app._start(app.filtered[0])
    app.network.request_stream.assert_not_called()


def test_received_buffer_does_not_mean_audio_has_started(app):
    app.current = app.filtered[0]
    app.playback_id = 'playing'
    app._event({'type': 'stream_ready', 'playback_id': 'playing', 'path': 'audio.pcm',
                'start': 0, 'complete': True})
    assert not app.playing and app.waiting
    app._event({'type': 'track_started', 'playback_id': 'playing', 'position': 0})
    assert app.playing and not app.waiting
