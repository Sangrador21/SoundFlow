import hashlib
import subprocess

import pytest
import requests

from soundflow.audio import ffmpeg_executable, BYTES_PER_SECOND
from soundflow import downloads
from test_service import Node, acquire, cluster
from tools.prepare_demo import tone


def test_remote_compressed_copy_uses_normal_reservation_and_cors(cluster):
    entry, remote, _ = cluster
    song = remote.core.library.all()[0]
    stream = acquire(entry.url, song.id)['stream']
    assert stream['server_id'] == 'S2'
    response = requests.get(stream['server_url'] + f"/api/streams/{stream['stream_id']}/download",
                            headers={'Origin': 'http://localhost:5173'}, timeout=10)
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('audio/mpeg')
    assert int(response.headers['X-Download-Bytes']) == len(response.content)
    assert response.headers['X-Download-SHA256'] == hashlib.sha256(response.content).hexdigest()
    assert 'X-Download-SHA256' in response.headers['Access-Control-Expose-Headers']
    pcm = subprocess.check_output([ffmpeg_executable(), '-v', 'error', '-i', 'pipe:0',
                                   '-f', 's16le', '-ar', '44100', '-ac', '2', 'pipe:1'], input=response.content)
    assert abs(len(pcm) / BYTES_PER_SECOND - song.duration) < 0.1
    assert remote.core.sessions[stream['stream_id']].state == 'completed'
    assert requests.get(stream['server_url'] + f"/api/streams/{stream['stream_id']}/download").status_code == 410


def test_mp3_copy_preserves_original_bytes_and_rejects_partial_start(tmp_path):
    music = tmp_path / 'music'
    tone(music / 'source.wav', 440, 0.8)
    mp3 = music / 'source.mp3'
    subprocess.run([ffmpeg_executable(), '-v', 'error', '-i', str(music / 'source.wav'), str(mp3)], check=True)
    node = Node(music, 'COPY')
    try:
        song = next(song for song in node.core.library.all() if song.filename.endswith('.mp3'))
        stream = acquire(node.url, song.id)['stream']
        response = requests.get(node.url + f"/api/streams/{stream['stream_id']}/download")
        assert response.content == mp3.read_bytes()
        assert response.headers['X-Download-SHA256'] == song.id
        partial = acquire(node.url, song.id, start=0.2)['stream']
        assert requests.get(node.url + f"/api/streams/{partial['stream_id']}/download").status_code == 400
        node.core.cancel_session(partial['stream_id'])
        assert requests.get(node.url + f"/api/streams/{partial['stream_id']}/download").status_code == 410
        assert requests.get(node.url + '/api/streams/unknown/download').status_code == 404
    finally:
        node.close()


def test_download_size_failure_releases_reservation(tmp_path, monkeypatch):
    music = tmp_path / 'music'
    tone(music / 'source.wav', 440, 1)
    mp3 = music / 'source.mp3'
    subprocess.run([ffmpeg_executable(), '-v', 'error', '-i', str(music / 'source.wav'), str(mp3)], check=True)
    node = Node(music, 'LIMIT')
    try:
        song = next(song for song in node.core.library.all() if song.filename.endswith('.mp3'))
        stream = acquire(node.url, song.id)['stream']
        monkeypatch.setattr(downloads, 'MAX_DOWNLOAD_BYTES', 32)
        response = requests.get(node.url + f"/api/streams/{stream['stream_id']}/download")
        assert response.status_code == 413
        assert node.core.sessions[stream['stream_id']].state == 'failed'
        assert node.core.resource_status()['active_streams'] == 0
    finally:
        node.close()
