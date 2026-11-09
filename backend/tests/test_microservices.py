"""Contratos y fallos con cinco aplicaciones independientes comunicadas por HTTP real."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import subprocess
import threading
import time
import uuid

import pytest
import requests
from werkzeug.serving import make_server

from microservices.catalog import CatalogService
from microservices.common import Rpc
from microservices.gateway import GatewayService
from microservices.media import MediaService
from microservices.playback import PlaybackService
from microservices.settings import ServiceSettings
from microservices.tickets import TicketStore
from soundflow.audio import ffmpeg_executable
from tools.prepare_demo import tone

TOKEN = 'local-test-token'
AUTH = {'X-Cluster-Token': TOKEN}


class HttpService:
    def __init__(self, core):
        self.core = core
        self.http = make_server('127.0.0.1', 0, core.app, threaded=True)
        self.url = f'http://127.0.0.1:{self.http.server_port}'
        if hasattr(core, 'base_url'):
            core.base_url = self.url
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.stopped = False

    def stop_http(self):
        if not self.stopped:
            self.http.shutdown()
            self.http.server_close()
            self.thread.join(2)
            self.stopped = True

    def close(self):
        self.stop_http()
        self.core.close()


@pytest.fixture
def micro(tmp_path):
    for name in ['S1', 'S2']:
        tone(tmp_path / name / f'only-{name}.wav', 440 if name == 'S1' else 660, 2)
    tone(tmp_path / 'S1' / 'shared.wav', 880, 2)
    (tmp_path / 'S2' / 'shared.wav').write_bytes((tmp_path / 'S1' / 'shared.wav').read_bytes())
    media = [HttpService(MediaService(tmp_path / node, 'http://127.0.0.1:1', server_id=node,
                token=TOKEN, origins=['http://localhost:5173'], cpu_threshold=100, memory_threshold=100))
             for node in ['S1', 'S2']]
    nodes = {f'S{i+1}': service.url for i, service in enumerate(media)}
    rpc = Rpc(TOKEN, 0.3)
    catalog = HttpService(CatalogService(nodes, rpc))
    playback = HttpService(PlaybackService(catalog.url, nodes, rpc, tmp_path / 'tickets.sqlite3', wait_timeout=3))
    gateway = HttpService(GatewayService(catalog.url, playback.url, rpc, 'http://127.0.0.1:1', ['http://localhost:5173']))
    yield {'media': media, 'catalog': catalog, 'playback': playback, 'gateway': gateway, 'nodes': nodes}
    for service in [gateway, playback, catalog, *media]:
        service.close()


def request_song(micro, song, start=0):
    result = requests.post(micro['gateway'].url + '/api/requests', json={'song_id': song, 'start': start}, timeout=3)
    assert result.status_code == 202, result.text
    return result.json()


def wait_ticket(micro, ticket, state='ready'):
    end = time.monotonic() + 4
    url = micro['gateway'].url + '/api/requests/' + ticket['request_id']
    while time.monotonic() < end:
        result = requests.get(url, timeout=3).json()
        if result['state'] == state:
            return result
        time.sleep(0.03)
    raise AssertionError(result)


def song_on(micro, node, filename):
    return next(song for song in micro['media'][node].core.library.all() if song.filename == filename)


def test_micro_catalog_deduplication_gateway_contract_and_trace(micro):
    response = requests.get(micro['gateway'].url + '/api/catalog', headers={'X-Request-ID': 'test-trace-123'}, timeout=3)
    assert response.status_code == 200
    assert response.headers['X-Request-ID'] == 'test-trace-123'
    assert response.headers['X-Service-Version'] == '0.8.0'
    data = response.json()
    assert len(data['songs']) == 3
    assert [node['song_count'] for node in data['nodes']] == [2, 2]
    assert data['entrypoints'] == [micro['gateway'].url]
    assert sorted(next(song for song in data['songs'] if song['filename'] == 'shared.wav')['servers']) == ['S1', 'S2']
    assert 'transport_url' not in response.text and TOKEN not in response.text
    services = requests.get(micro['gateway'].url + '/api/services', timeout=3)
    assert services.status_code == 200
    assert all(item['status'] == 'ok' for item in services.json()['services'])


def test_micro_boundaries_and_internal_auth(micro):
    assert requests.get(micro['catalog'].url + '/internal/v1/catalog').status_code == 403
    assert requests.get(micro['media'][0].url + '/internal/v1/node').status_code == 403
    assert requests.post(micro['playback'].url + '/internal/v1/requests', json={}).status_code == 403
    assert requests.post(micro['media'][0].url + '/api/requests', json={}).status_code == 404
    assert requests.get(micro['gateway'].url + '/api/streams/unknown/audio').status_code == 404
    assert not hasattr(micro['catalog'].core, 'sessions')
    assert not hasattr(micro['playback'].core, 'library')


def test_micro_remote_audio_exact_seek_and_cors(micro):
    song = song_on(micro, 1, 'only-S2.wav')
    ticket = wait_ticket(micro, request_song(micro, song.id, 0.37))
    stream = ticket['stream']
    assert stream['server_id'] == 'S2'
    response = requests.get(stream['audio_url'], headers={'Origin': 'http://localhost:5173'}, timeout=5)
    reference = subprocess.check_output([ffmpeg_executable(), '-v', 'error', '-i', song.path,
        '-af', 'aresample=44100,aformat=sample_fmts=s16:channel_layouts=stereo,atrim=start_sample=16317,asetpts=PTS-STARTPTS',
        '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', '-f', 's16le', 'pipe:1'])
    assert response.status_code == 200 and response.content == reference
    assert response.headers['Access-Control-Allow-Origin'] == 'http://localhost:5173'
    assert 'X-Sample-Rate' in response.headers['Access-Control-Expose-Headers']


def test_micro_offline_download_complete_hash_and_session(micro):
    song = song_on(micro, 1, 'only-S2.wav')
    stream = wait_ticket(micro, request_song(micro, song.id))['stream']
    response = requests.get(stream['server_url'] + '/api/streams/' + stream['stream_id'] + '/download',
                            headers={'Origin': 'http://localhost:5173'}, timeout=5)
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('audio/mpeg')
    assert len(response.content) == int(response.headers['X-Download-Bytes'])
    assert hashlib.sha256(response.content).hexdigest() == response.headers['X-Download-SHA256']
    assert 'X-Download-SHA256' in response.headers['Access-Control-Expose-Headers']
    assert requests.get(stream['server_url'] + '/api/streams/' + stream['stream_id']).json()['state'] == 'completed'


def test_micro_more_than_eight_sessions_and_cancel_release(micro):
    song = song_on(micro, 1, 'only-S2.wav')
    with ThreadPoolExecutor(max_workers=12) as pool:
        tickets = list(pool.map(lambda _: request_song(micro, song.id), range(12)))
    ready = [wait_ticket(micro, ticket) for ticket in tickets]
    assert len({ticket['stream']['stream_id'] for ticket in ready}) == 12
    assert micro['media'][1].core.resource_status()['active_streams'] == 12
    for ticket in tickets:
        assert requests.delete(micro['gateway'].url + '/api/requests/' + ticket['request_id']).status_code == 204
    assert micro['media'][1].core.resource_status()['active_streams'] == 0


def test_micro_fifo_wait_cancel_and_resume(micro):
    remote = micro['media'][1].core
    remote.maintenance = True
    song = song_on(micro, 1, 'only-S2.wav')
    tickets = [request_song(micro, song.id) for _ in range(3)]
    assert [wait_ticket(micro, item, 'waiting')['position'] for item in tickets] == [1, 2, 3]
    requests.delete(micro['gateway'].url + '/api/requests/' + tickets[1]['request_id'])
    assert wait_ticket(micro, tickets[2], 'waiting')['position'] == 2
    remote.maintenance = False
    micro['playback'].core.wake.set()
    first, third = [wait_ticket(micro, tickets[i]) for i in [0, 2]]
    assert remote.sessions[first['stream']['stream_id']].created <= remote.sessions[third['stream']['stream_id']].created


def test_micro_invalid_missing_and_expired_requests(micro):
    url = micro['gateway'].url + '/api/requests'
    song = song_on(micro, 1, 'only-S2.wav')
    for start in [-1, True, 'NaN', 'abc', 1e308]:
        assert requests.post(url, json={'song_id': song.id, 'start': start}).status_code == 400
    missing = wait_ticket(micro, request_song(micro, '0'*64), 'failed')
    assert missing['error_code'] == 404
    beyond = wait_ticket(micro, request_song(micro, song.id, 999), 'failed')
    assert beyond['error_code'] == 400
    micro['media'][1].core.maintenance = True
    micro['playback'].core.wait_timeout = 0.1
    expired = wait_ticket(micro, request_song(micro, song.id), 'failed')
    assert expired['error_code'] == 504


def test_micro_catalog_failure_isolated_from_active_media(micro):
    song = song_on(micro, 0, 'only-S1.wav')
    stream = wait_ticket(micro, request_song(micro, song.id))['stream']
    micro['catalog'].stop_http()
    assert requests.get(micro['gateway'].url + '/api/catalog').status_code == 503
    assert requests.get(micro['gateway'].url + '/api/services').status_code == 503
    response = requests.get(stream['audio_url'], timeout=5)
    assert response.status_code == 200 and response.content


def test_micro_node_failure_keeps_reference_and_uses_shared_replica(micro):
    requests.get(micro['gateway'].url + '/api/catalog')
    micro['media'][1].stop_http()
    data = requests.get(micro['gateway'].url + '/api/catalog').json()
    assert data['offline'] == ['S2'] and len(data['nodes']) == 1
    assert next(song for song in data['songs'] if song['filename'] == 'only-S2.wav')['available'] is False
    shared = song_on(micro, 0, 'shared.wav')
    assert wait_ticket(micro, request_song(micro, shared.id))['stream']['server_id'] == 'S1'


def test_micro_reservations_are_idempotent_and_use_resources(micro):
    node = micro['media'][0]
    song = song_on(micro, 0, 'only-S1.wav')
    body = {'song_id': song.id, 'start': 0, 'reservation_id': uuid.uuid4().hex}
    responses = [requests.post(node.url + '/internal/v1/streams', json=body, headers=AUTH) for _ in range(2)]
    assert responses[0].json()['stream_id'] == responses[1].json()['stream_id']
    assert node.core.resource_status()['active_streams'] == 1
    node.core.maintenance = True
    body['reservation_id'] = uuid.uuid4().hex
    assert requests.post(node.url + '/internal/v1/streams', json=body, headers=AUTH).status_code == 503


def test_micro_ticket_store_reopens_pending_fifo_without_shared_database(tmp_path):
    path = tmp_path / 'playback.sqlite3'
    first = TicketStore(path)
    one, two = [first.create(str(i)*64, 0, 'trace') for i in [1, 2]]
    first.close()
    second = TicketStore(path)
    try:
        assert second.head()['id'] == one
        assert second.position(second.get(two)) == 2
        assert second.change(one, 'cancelled', 'Cancelado')
        assert second.head()['id'] == two
    finally:
        second.close()


def test_micro_settings_fail_fast_on_missing_token_and_role(monkeypatch):
    monkeypatch.setenv('SOUNDFLOW_SERVICE', 'gateway')
    monkeypatch.setenv('SOUNDFLOW_CLUSTER_TOKEN', '')
    with pytest.raises(ValueError, match='TOKEN'):
        ServiceSettings.from_env()
    monkeypatch.setenv('SOUNDFLOW_CLUSTER_TOKEN', TOKEN)
    monkeypatch.setenv('SOUNDFLOW_SERVICE', 'monolith')
    with pytest.raises(ValueError, match='SERVICE'):
        ServiceSettings.from_env()
