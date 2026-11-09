"""Entrada pública de control. El audio va directamente al nodo asignado."""
from flask import g, jsonify, request

from .common import DependencyError, VERSION, new_app


class GatewayService:
    def __init__(self, catalog_url, playback_url, rpc, base_url, origins):
        self.catalog_url, self.playback_url = catalog_url, playback_url
        self.rpc, self.base_url = rpc, base_url
        self.app = new_app('gateway', origins)

        @self.app.get('/api/health')
        def health():
            return jsonify(status='ok', service='gateway', version=VERSION,
                           architecture='microservices', features=['pwa', 'offline-download'])

        @self.app.get('/api/services')
        def services():
            results = []
            for name, url in [('catalog', self.catalog_url), ('playback', self.playback_url)]:
                try:
                    data, code = self.rpc.json('GET', url + '/api/health', trace=g.request_id)
                    ok = code == 200 and data.get('version') == VERSION and data.get('service') == name
                except DependencyError:
                    ok = False
                results.append({'service': name, 'status': 'ok' if ok else 'unavailable'})
            return jsonify(services=results), 200 if all(x['status'] == 'ok' for x in results) else 503

        @self.app.get('/api/catalog')
        def catalog():
            data, code = self.rpc.json('GET', self.catalog_url + '/internal/v1/catalog', trace=g.request_id)
            if code == 200:
                data['entrypoints'] = [self.base_url]
            return jsonify(data), code

        @self.app.post('/api/requests')
        def create():
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                raise ValueError('Envía un objeto JSON.')
            data, code = self.rpc.json('POST', self.playback_url + '/internal/v1/requests',
                                        trace=g.request_id, json=body)
            return jsonify(data), code

        @self.app.route('/api/requests/<ticket_id>', methods=['GET', 'DELETE'])
        def ticket(ticket_id):
            # El ID forma parte de una ruta fija; no se utiliza como URL arbitraria.
            if len(ticket_id) != 32 or any(c not in '0123456789abcdef' for c in ticket_id):
                raise ValueError('Identificador de solicitud inválido.')
            url = self.playback_url + '/internal/v1/requests/' + ticket_id
            if request.method == 'DELETE':
                response = self.rpc.call('DELETE', url, trace=g.request_id)
                if response.status_code == 204:
                    return '', 204
                return jsonify(response.json()), response.status_code
            data, code = self.rpc.json('GET', url, trace=g.request_id)
            return jsonify(data), code

    def close(self):
        pass
