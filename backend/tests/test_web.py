from pathlib import Path
import json

import pytest

from soundflow.config import Settings
from soundflow.resources import ResourceMonitor
from soundflow.server_core import SoundFlowServer
from tools.build_catalog import build_catalog
from tools.prepare_demo import tone


def test_cors_allows_configured_page_and_exposes_pcm_headers(tmp_path):
    tone(tmp_path / 'music' / 'a.wav', 440, 0.2)
    node = SoundFlowServer(tmp_path / 'music', 'https://node.example', allowed_origins=['https://owner.github.io'])
    client = node.app.test_client()
    origin = {'Origin': 'https://owner.github.io'}
    try:
        preflight = client.options('/api/requests', headers={**origin,
            'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Content-Type'})
        assert preflight.headers['Access-Control-Allow-Origin'] == origin['Origin']
        assert 'POST' in preflight.headers['Access-Control-Allow-Methods']
        denied = client.get('/api/catalog', headers={'Origin': 'https://unrelated.example'})
        assert 'Access-Control-Allow-Origin' not in denied.headers
        song = node.library.all()[0]
        ticket = client.post('/api/requests', json={'song_id': song.id}, headers=origin).json
        stream = ticket['stream']
        response = client.get(f"/api/streams/{stream['stream_id']}/audio", headers=origin)
        assert response.headers['Access-Control-Allow-Origin'] == origin['Origin']
        assert 'X-Sample-Rate' in response.headers['Access-Control-Expose-Headers']
        assert response.headers['X-Audio-Format'] == 's16le'
        assert response.data
        response.close()
    finally:
        node.close()


def test_internal_token_stays_between_nodes(tmp_path):
    tone(tmp_path / 'a.wav', 440, 0.1)
    node = SoundFlowServer(tmp_path, 'https://node.example', cluster_token='cluster-secret')
    client = node.app.test_client()
    try:
        song = node.library.all()[0]
        assert client.post('/api/internal/streams', json={'song_id': song.id}).status_code == 403
        response = client.post('/api/internal/streams', json={'song_id': song.id}, headers={'X-Cluster-Token': 'cluster-secret'})
        assert response.status_code == 201
        assert 'cluster-secret' not in client.get('/api/node').text
        assert 'cluster-secret' not in client.get('/api/catalog').text
    finally:
        node.close()


def test_render_settings_use_public_https_url(monkeypatch):
    monkeypatch.delenv('SOUNDFLOW_BASE_URL', raising=False)
    monkeypatch.setenv('RENDER_EXTERNAL_URL', 'https://node.onrender.com')
    monkeypatch.setenv('SOUNDFLOW_NODE_ID', 'S2')
    monkeypatch.setenv('SOUNDFLOW_PEERS', 'https://peer.onrender.com')
    monkeypatch.setenv('SOUNDFLOW_CORS_ORIGINS', 'https://owner.github.io')
    config = Settings.from_env()
    assert config.base_url == 'https://node.onrender.com'
    assert config.peers == ['https://peer.onrender.com']
    assert config.music_dir.name == 'S2'
    monkeypatch.setenv('SOUNDFLOW_CORS_ORIGINS', '*')
    with pytest.raises(ValueError):
        Settings.from_env()


def test_container_memory_and_cpu_quota(tmp_path, monkeypatch):
    (tmp_path / 'memory.max').write_text('1000')
    (tmp_path / 'memory.current').write_text('420')
    (tmp_path / 'cpu.max').write_text('50000 100000')
    (tmp_path / 'cpu.stat').write_text('usage_usec 100000\nnr_periods 1')
    monitor = ResourceMonitor(tmp_path)
    times = iter([1.0, 2.0])
    monkeypatch.setattr('soundflow.resources.time.monotonic', lambda: next(times))
    assert monitor.sample()[1] == 42
    (tmp_path / 'cpu.stat').write_text('usage_usec 350000\nnr_periods 2')
    cpu, memory = monitor.sample()
    assert cpu == 50 and memory == 42


def test_catalog_builder_only_copies_assigned_files_and_updates_owned_output(tmp_path):
    source = tmp_path / 'source'
    for name in ['one.wav', 'two.wav', 'shared.wav']:
        tone(source / name, 440, 0.05)
    s1, s2 = tmp_path / 'S1.json', tmp_path / 'S2.json'
    s1.write_text(json.dumps(['one.wav', 'shared.wav']))
    s2.write_text(json.dumps(['two.wav', 'shared.wav']))
    first, second = tmp_path / 's1', tmp_path / 's2'
    build_catalog(source, s1, first)
    build_catalog(source, s2, second)
    assert sorted(p.name for p in first.glob('*.wav')) == ['one.wav', 'shared.wav']
    assert sorted(p.name for p in second.glob('*.wav')) == ['shared.wav', 'two.wav']
    assert (first / 'shared.wav').read_bytes() == (second / 'shared.wav').read_bytes()
    s1.write_text(json.dumps(['one.wav']))
    build_catalog(source, s1, first)
    assert not (first / 'shared.wav').exists()
    assert (source / 'shared.wav').exists()
    (first / 'personal.txt').write_text('keep')
    with pytest.raises(ValueError):
        build_catalog(source, s1, first)
    assert (first / 'personal.txt').exists()


def test_catalog_manifest_rejects_paths(tmp_path):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(['../song.mp3']))
    with pytest.raises(ValueError):
        build_catalog(tmp_path, path, tmp_path / 'out')
