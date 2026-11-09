"""Catálogo agregado. Solo posee metadatos; no reserva sesiones ni abre audio."""
from concurrent.futures import ThreadPoolExecutor
import threading

from flask import g, jsonify

from .common import DependencyError, VERSION, internal, new_app


class CatalogService:
    def __init__(self, nodes, rpc):
        self.nodes, self.rpc = dict(nodes), rpc
        self.cache = {}
        self.lock = threading.RLock()
        self.app = new_app('catalog')
        protect = internal(rpc.token)

        @self.app.get('/api/health')
        def health():
            return jsonify(status='ok', service='catalog', version=VERSION)

        @self.app.get('/internal/v1/nodes')
        @protect
        def nodes_route():
            nodes, offline = self.discover(g.request_id)
            return jsonify(nodes=nodes, offline=offline)

        @self.app.get('/internal/v1/catalog')
        @protect
        def catalog_route():
            return jsonify(self.catalog(g.request_id))

    def discover(self, trace=None):
        def inspect(item):
            node_id, url = item
            try:
                data, code = self.rpc.json('GET', url + '/internal/v1/node', trace=trace)
                if code != 200 or data.get('server_id') != node_id or not isinstance(data.get('songs'), list):
                    raise DependencyError('Nodo incompatible.')
                data['transport_url'] = url
                with self.lock:
                    self.cache[node_id] = data
                return data
            except (DependencyError, ValueError, KeyError, TypeError):
                return None
        with ThreadPoolExecutor(max_workers=min(len(self.nodes), 16)) as pool:
            results = list(pool.map(inspect, self.nodes.items()))
        live = [node for node in results if node]
        offline = [node_id for node_id, result in zip(self.nodes, results) if not result]
        return live, offline

    def catalog(self, trace=None):
        nodes, offline = self.discover(trace)
        with self.lock:
            sources = [(node, True) for node in nodes] + [
                (self.cache[node_id], False) for node_id in offline if node_id in self.cache]
        songs = {}
        for node, available in sources:
            for item in node['songs']:
                song = songs.setdefault(item['id'], {**item, 'servers': [], 'available': False})
                if node['server_id'] not in song['servers']:
                    song['servers'].append(node['server_id'])
                song['available'] |= available
        # transport_url solo existe en el contrato interno; nunca llega a la PWA.
        return {'songs': sorted(songs.values(), key=lambda song: song['title'].casefold()),
                'nodes': [{'server_id': node['server_id'], 'base_url': node['base_url'],
                           'resources': node['resources'], 'song_count': len(node['songs'])}
                          for node in nodes],
                'offline': offline}

    def close(self):
        pass
