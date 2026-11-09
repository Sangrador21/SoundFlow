"""Asignación y FIFO. Consulta catálogo y reserva medios exclusivamente por HTTP."""
import threading

from flask import g, jsonify

from .common import DependencyError, VERSION, internal, new_app, parse_song
from .tickets import TicketStore


class PlaybackService:
    def __init__(self, catalog_url, nodes, rpc, database, *, wait_timeout=120):
        self.catalog_url, self.nodes, self.rpc = catalog_url, dict(nodes), rpc
        self.wait_timeout = wait_timeout
        self.store = TicketStore(database)
        self.dispatch_lock = threading.Lock()
        self.stop_event, self.wake = threading.Event(), threading.Event()
        self.app = new_app('playback')
        protect = internal(rpc.token)

        @self.app.get('/api/health')
        def health():
            return jsonify(status='ok', service='playback', version=VERSION)

        @self.app.post('/internal/v1/requests')
        @protect
        def create():
            song, start = parse_song()
            ticket = self.store.create(song, start, g.request_id)
            self.wake.set()
            return jsonify(self.ticket_data(self.store.get(ticket))), 202

        @self.app.get('/internal/v1/requests/<ticket_id>')
        @protect
        def status(ticket_id):
            ticket = self.store.get(ticket_id)
            if not ticket:
                return jsonify(error='Solicitud desconocida.'), 404
            return jsonify(self.ticket_data(ticket))

        @self.app.delete('/internal/v1/requests/<ticket_id>')
        @protect
        def cancel(ticket_id):
            # Releer tras un CAS fallido: la asignación puede terminar mientras
            # llega DELETE. La cancelación debe alcanzar también esa reserva.
            while True:
                ticket = self.store.get(ticket_id)
                if not ticket:
                    return jsonify(error='Solicitud desconocida.'), 404
                if ticket['state'] not in {'waiting', 'ready'}:
                    break
                changed = self.store.change(ticket_id, 'cancelled', 'Solicitud cancelada.',
                                            stream=ticket['stream'], expected=ticket['state'])
                if changed:
                    if ticket['stream']:
                        self.cancel_assignment(ticket['stream'], g.request_id)
                    break
            self.wake.set()
            return '', 204

        self.worker = threading.Thread(target=self._loop, daemon=True, name='playback-fifo')
        self.worker.start()

    def ticket_data(self, ticket):
        return {'request_id': ticket['id'], 'song_id': ticket['song_id'],
                'state': ticket['state'], 'position': self.store.position(ticket),
                'message': ticket['reason'], 'stream': ticket['stream'],
                'error_code': ticket['error_code'], 'wait_timeout': self.wait_timeout}

    def cancel_assignment(self, stream, trace=None):
        url = self.nodes.get(stream.get('server_id'))
        if not url:
            return
        try:
            self.rpc.call('DELETE', url + '/internal/v1/streams/' + stream['stream_id'], trace=trace)
        except DependencyError:
            # Las reservas de medios no consumidas vencen a los 30 segundos.
            pass

    def attempt(self, ticket):
        trace = ticket['trace']
        try:
            data, code = self.rpc.json('GET', self.catalog_url + '/internal/v1/nodes', trace=trace)
            if code != 200:
                return False
            nodes, offline = data['nodes'], data['offline']
        except (DependencyError, KeyError, TypeError):
            return False
        holders = [node for node in nodes if any(song['id'] == ticket['song_id'] for song in node['songs'])]
        candidates = sorted((node for node in holders if node['resources']['accepting']),
                            key=lambda node: (node['resources']['active_streams'],
                                              node['resources']['cpu_percent'], node['resources']['memory_percent']))
        transient = False
        for node in candidates:
            current = self.store.get(ticket['id'])
            if not current or current['state'] != 'waiting':
                return True
            # Solo las direcciones configuradas: nunca se sigue una URL enviada por el navegador.
            url = self.nodes.get(node['server_id'])
            if not url:
                continue
            try:
                stream, status = self.rpc.json('POST', url + '/internal/v1/streams', trace=trace,
                    json={'song_id': ticket['song_id'], 'start': ticket['start'],
                          'reservation_id': ticket['id']})
                if status == 400:
                    self.store.change(ticket['id'], 'failed', stream.get('error', 'Posición inválida.'), 400)
                    return True
                if status != 201:
                    transient = True
                    continue
                if stream.get('server_id') != node['server_id']:
                    raise DependencyError('Asignación incompatible.')
                changed = self.store.change(ticket['id'], 'ready', 'Solicitud asignada a ' + node['server_id'],
                                            stream=stream)
                if not changed:
                    self.cancel_assignment(stream, trace)
                return True
            except (DependencyError, KeyError, TypeError):
                transient = True
        if not holders and not offline and not transient:
            self.store.change(ticket['id'], 'failed', 'La canción no existe en los nodos disponibles.', 404)
            return True
        return False

    def dispatch_once(self):
        if not self.dispatch_lock.acquire(blocking=False):
            return
        try:
            self.store.expire(self.wait_timeout)
            while not self.stop_event.is_set():
                ticket = self.store.head()
                if not ticket or not self.attempt(ticket):
                    break
        finally:
            self.dispatch_lock.release()

    def _loop(self):
        while not self.stop_event.is_set():
            self.dispatch_once()
            self.wake.wait(1)
            self.wake.clear()

    def close(self):
        self.stop_event.set()
        self.wake.set()
        self.worker.join(timeout=3 * self.rpc.timeout + 5)
        if not self.worker.is_alive():
            self.store.close()
