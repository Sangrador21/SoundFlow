from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import queue
import subprocess
import threading
import time
import requests
import pytest
from werkzeug.serving import make_server
from soundflow.server_core import SoundFlowServer
from soundflow.network_client import SoundFlowHTTPClient
from soundflow.audio import ffmpeg_executable, BYTES_PER_SECOND
from tools.prepare_demo import tone
from tools.create_cert import create_certificate


class Node:
    def __init__(self, directory, node_id, *, ssl_context=None, verify=True):
        self.core = SoundFlowServer(directory, 'http://127.0.0.1:1', server_id=node_id,
                                    cpu_threshold=100, memory_threshold=100,
                                    wait_timeout=3, peer_timeout=0.2, verify=verify)
        self.http = make_server('127.0.0.1', 0, self.core.app, threaded=True, ssl_context=ssl_context)
        scheme = 'https' if ssl_context else 'http'
        self.url = f'{scheme}://127.0.0.1:{self.http.server_port}'
        self.core.base_url = self.url
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.core.close()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(2)


@pytest.fixture
def cluster(tmp_path):
    for name in ['S1', 'S2', 'S3']:
        (tmp_path / name).mkdir()
    tone(tmp_path / 'S1' / 'Only S1.wav', 440, 4)
    tone(tmp_path / 'S2' / 'Only S2.wav', 660, 4)
    # Misma canción con otro nombre: se deduplica por contenido.
    (tmp_path / 'S3' / 'Renamed.wav').write_bytes((tmp_path / 'S1' / 'Only S1.wav').read_bytes())
    nodes = [Node(tmp_path / name, name) for name in ['S1', 'S2', 'S3']]
    nodes[0].core.peers = [nodes[1].url]
    nodes[1].core.peers = [nodes[2].url]
    nodes[2].core.peers = [nodes[0].url]
    yield nodes
    for node in nodes:
        node.close()


def catalog(url, **kwargs):
    response = requests.get(url + '/api/catalog', timeout=5, **kwargs)
    response.raise_for_status()
    return response.json()


def acquire(url, song_id, start=0, **kwargs):
    response = requests.post(url + '/api/requests', json={'song_id': song_id, 'start': start}, timeout=5, **kwargs)
    response.raise_for_status()
    data = response.json()
    end = time.monotonic() + 5
    while data['state'] == 'waiting' and time.monotonic() < end:
        time.sleep(0.05)
        data = requests.get(url + '/api/requests/' + data['request_id'], timeout=5, **kwargs).json()
    assert data['state'] == 'ready', data
    return data


def test_distinct_catalogs_deduplication_and_no_discovery_cycles(cluster):
    data = catalog(cluster[0].url)
    assert len(data['nodes']) == 3
    assert len(data['songs']) == 2
    shared = next(song for song in data['songs'] if 'S1' in song['servers'])
    assert set(shared['servers']) == {'S1', 'S3'}
    assert all('/workspace' not in song['path'] for song in data['songs'])


def test_remote_audio_and_exact_seek(cluster):
    entry, remote, _ = cluster
    song = remote.core.library.all()[0]
    result = acquire(entry.url, song.id, start=1.25)
    stream = result['stream']
    assert stream['server_id'] == 'S2'
    response = requests.get(stream['audio_url'], timeout=5)
    response.raise_for_status()
    expected = subprocess.check_output([ffmpeg_executable(), '-v', 'error', '-ss', '1.25', '-i', song.path,
                                        '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', '-f', 's16le', 'pipe:1'])
    assert response.content == expected
    assert abs(len(response.content) / BYTES_PER_SECOND - 2.75) < 0.001
    assert requests.get(remote.url + '/api/streams/' + stream['stream_id']).json()['state'] == 'completed'


def test_no_fixed_transfer_count_limit(cluster):
    entry, remote, _ = cluster
    song = remote.core.library.all()[0]
    # Solo se reservan: doce sesiones siguen vivas simultáneamente, más que el antiguo ocho.
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: acquire(entry.url, song.id), range(12)))
    assert len({r['stream']['stream_id'] for r in results}) == 12
    assert remote.core.resource_status()['active_streams'] == 12
    for result in results:
        assert requests.delete(entry.url + '/api/requests/' + result['request_id']).status_code == 204
    assert remote.core.resource_status()['active_streams'] == 0


def test_fifo_waits_then_dispatches_and_cancel_removes_ticket(cluster):
    entry, remote, _ = cluster
    song = remote.core.library.all()[0]
    remote.core.maintenance = True
    tickets = [requests.post(entry.url + '/api/requests', json={'song_id': song.id}).json() for _ in range(3)]
    assert [t['position'] for t in tickets] == [1, 2, 3]
    requests.delete(entry.url + '/api/requests/' + tickets[1]['request_id'])
    third = requests.get(entry.url + '/api/requests/' + tickets[2]['request_id']).json()
    assert third['position'] == 2
    remote.core.maintenance = False
    entry.core.wake.set()
    end = time.monotonic() + 4
    while time.monotonic() < end:
        first = requests.get(entry.url + '/api/requests/' + tickets[0]['request_id']).json()
        third = requests.get(entry.url + '/api/requests/' + tickets[2]['request_id']).json()
        if first['state'] == third['state'] == 'ready':
            break
        time.sleep(0.05)
    assert first['state'] == third['state'] == 'ready'
    first_session = remote.core.sessions[first['stream']['stream_id']]
    third_session = remote.core.sessions[third['stream']['stream_id']]
    assert first_session.created <= third_session.created


def test_real_resource_gate_not_count(cluster, monkeypatch):
    node = cluster[0]
    song = node.core.library.all()[0]
    # Presión real se evalúa por el porcentaje reportado; no por número de sesiones.
    with node.core.lock:
        node.core.cpu_percent = 99
        node.core.cpu_threshold = 95
    result, code = node.core._reserve(song.id, 0)
    assert code == 503
    with node.core.lock:
        node.core.cpu_percent = 10
    assert node.core._reserve(song.id, 0)[1] == 201


def test_bad_input_missing_song_and_expired_wait(cluster):
    entry, remote, _ = cluster
    assert requests.post(entry.url + '/api/requests', json={'song_id': '../../etc/passwd'}).status_code == 400
    song = remote.core.library.all()[0]
    for start in [-1, 'abc', True, 'NaN', 999]:
        assert requests.post(entry.url + '/api/requests', json={'song_id': song.id, 'start': start}).status_code == 400
    assert requests.post(entry.url + '/api/requests', json={'song_id': '0' * 64}).status_code == 404
    remote.core.maintenance = True
    entry.core.wait_timeout = 0.2
    result = requests.post(entry.url + '/api/requests', json={'song_id': song.id}).json()
    time.sleep(0.25)
    entry.core.dispatch_once()
    data = requests.get(entry.url + '/api/requests/' + result['request_id']).json()
    assert data['state'] == 'failed' and data['error_code'] == 504


def test_stale_catalog_and_wait_when_holder_offline(cluster):
    entry, remote, other = cluster
    song = remote.core.library.all()[0]
    catalog(entry.url)  # Retiene la última información del nodo.
    original = entry.core.peers[:]
    entry.core.peers = ['http://127.0.0.1:1']
    entry.core.node_cache['http://127.0.0.1:1'] = remote.core.node_info()
    data = catalog(entry.url)
    unavailable = next(s for s in data['songs'] if s['id'] == song.id)
    assert unavailable['available'] is False
    response = requests.post(entry.url + '/api/requests', json={'song_id': song.id})
    assert response.status_code == 202 and response.json()['state'] == 'waiting'
    entry.core.peers = original
    entry.core.wake.set()


def test_client_download_is_progressive_and_falls_back(cluster, tmp_path):
    _, remote, _ = cluster
    song = remote.core.library.all()[0].to_dict()
    events = queue.Queue()
    client = SoundFlowHTTPClient('http://127.0.0.1:1', tmp_path / 'cache', events,
                                 fallbacks=[remote.url], wait_timeout=10)
    identifier = client.request_stream(song, start=1)
    observed = []
    end = time.monotonic() + 12
    try:
        while time.monotonic() < end:
            event = events.get(timeout=5)
            if event.get('playback_id') == identifier:
                observed.append(event)
                if event['type'] in {'stream_complete', 'network_error'}:
                    break
        kinds = [e['type'] for e in observed]
        assert 'network_error' not in kinds, observed
        assert kinds.index('stream_ready') < kinds.index('stream_complete')
        ready = next(e for e in observed if e['type'] == 'stream_ready')
        assert ready['complete'] is False
        assert abs(Path(ready['path']).stat().st_size / BYTES_PER_SECOND - 3) < 0.001
    finally:
        client.close()


def test_https_verified_audio_and_peer_discovery(tmp_path):
    certificates = tmp_path / 'certs'
    create_certificate(certificates, [])
    music = tmp_path / 'music'
    tone(music / 'secure.wav', 440, 1.5)
    node = Node(music, 'TLS', ssl_context=(str(certificates / 'server.pem'), str(certificates / 'server-key.pem')),
                verify=str(certificates / 'ca.pem'))
    entry = Node(tmp_path / 'empty', 'ENTRY', verify=str(certificates / 'ca.pem'))
    entry.core.peers = [node.url]
    try:
        song = catalog(entry.url)['songs'][0]
        result = acquire(entry.url, song['id'])
        assert result['stream']['server_id'] == 'TLS'
        response = requests.get(result['stream']['audio_url'], verify=str(certificates / 'ca.pem'), timeout=5)
        assert response.status_code == 200
        assert len(response.content) == int(1.5 * BYTES_PER_SECOND)
        with pytest.raises(requests.exceptions.SSLError):
            requests.get(node.url + '/api/health', timeout=3)
    finally:
        entry.close()
        node.close()


@pytest.mark.parametrize('extension,codec', [('mp3', 'libmp3lame'), ('ogg', 'libvorbis'), ('flac', 'flac')])
def test_compressed_formats_support_time_seek(tmp_path, extension, codec):
    music = tmp_path / 'formats'
    tone(music / 'input.wav', 440, 2)
    source = music / ('test.' + extension)
    subprocess.run([ffmpeg_executable(), '-y', '-v', 'error', '-i', str(music / 'input.wav'),
                    '-c:a', codec, str(source)], check=True)
    node = Node(music, 'FORMAT')
    try:
        song = next(s for s in node.core.library.all() if s.filename.endswith(extension))
        assert song.duration > 1
        result = acquire(node.url, song.id, start=0.75)
        response = requests.get(result['stream']['audio_url'], timeout=5)
        response.raise_for_status()
        expected = subprocess.check_output([ffmpeg_executable(), '-v', 'error', '-ss', '0.75', '-i', str(source),
                                            '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', '-f', 's16le', 'pipe:1'])
        assert response.content == expected
    finally:
        node.close()


def test_client_recovers_interrupted_transfer_without_duplicate_samples(cluster, tmp_path, monkeypatch):
    node = cluster[0]
    song = node.core.library.all()[0]
    events = queue.Queue()
    client = SoundFlowHTTPClient(node.url, tmp_path / 'resume', events, wait_timeout=10)
    original = client._http
    interrupted = False

    def flaky_http(method, url, **kwargs):
        nonlocal interrupted
        response = original(method, url, **kwargs)
        if method == 'GET' and url.endswith('/audio') and not interrupted:
            interrupted = True
            original_iter = response.iter_content

            def broken_iter(*args, **kwargs):
                for chunk in original_iter(*args, **kwargs):
                    yield chunk
                    raise requests.ConnectionError('Fallo de transporte simulado después del primer bloque')
            response.iter_content = broken_iter
        return response

    monkeypatch.setattr(client, '_http', flaky_http)
    identifier = client.request_stream(song.to_dict())
    seen = []
    try:
        while True:
            event = events.get(timeout=12)
            if event.get('playback_id') == identifier:
                seen.append(event)
                if event['type'] in {'network_error', 'stream_complete'}:
                    break
        assert seen[-1]['type'] == 'stream_complete', seen
        assert sum(e['type'] == 'stream_started' for e in seen) == 2
        ready = next(e for e in seen if e['type'] == 'stream_ready')
        expected = subprocess.check_output([ffmpeg_executable(), '-v', 'error', '-i', song.path,
                                            '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', '-f', 's16le', 'pipe:1'])
        assert Path(ready['path']).read_bytes() == expected
    finally:
        client.close()
