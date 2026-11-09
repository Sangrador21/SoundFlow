"""Transporte HTTP, validación y observabilidad; sin estado de negocio compartido."""
from __future__ import annotations

from functools import wraps
import hmac
import logging
import math
import re
import uuid

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import requests

VERSION = '0.8.0'
log = logging.getLogger('soundflow.rpc')


class DependencyError(Exception):
    pass


def new_app(role, origins=()):
    app = Flask('soundflow.' + role)
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
    if origins:
        CORS(app, resources={r'/api/*': {
            'origins': list(origins), 'methods': ['GET', 'POST', 'DELETE', 'OPTIONS'],
            'allow_headers': ['Content-Type', 'X-Request-ID'],
            'expose_headers': ['X-Audio-Format', 'X-Sample-Rate', 'X-Channels',
                               'X-Audio-Start', 'X-Audio-Duration', 'X-Server-ID',
                               'X-Estimated-Bytes', 'X-Download-SHA256', 'X-Download-Bytes',
                               'X-Request-ID', 'X-Service-Version'],
        }}, max_age=600)

    @app.before_request
    def trace():
        supplied = request.headers.get('X-Request-ID', '')
        g.request_id = supplied if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', supplied) else uuid.uuid4().hex

    @app.after_request
    def headers(response):
        response.headers['X-Request-ID'] = g.request_id
        response.headers['X-Service-Version'] = VERSION
        response.headers['Cache-Control'] = 'no-store'
        log.info('service=%s request_id=%s method=%s path=%s status=%s',
                 role, g.request_id, request.method, request.path, response.status_code)
        return response

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error=exc.description), exc.code

    @app.errorhandler(ValueError)
    @app.errorhandler(TypeError)
    def invalid(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(DependencyError)
    def unavailable(exc):
        return jsonify(error=str(exc)), 503
    return app


def internal(token):
    if not token:
        raise ValueError('Configura SOUNDFLOW_CLUSTER_TOKEN para los microservicios.')

    def decorate(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            if not hmac.compare_digest(request.headers.get('X-Cluster-Token', ''), token):
                return jsonify(error='Acceso interno no autorizado.'), 403
            return function(*args, **kwargs)
        return guarded
    return decorate


def parse_song():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError('Envía un objeto JSON con song_id y start opcional.')
    song = data.get('song_id')
    if not isinstance(song, str) or not re.fullmatch(r'[a-f0-9]{64}', song):
        raise ValueError('song_id debe ser un identificador del catálogo.')
    raw = data.get('start', 0)
    if isinstance(raw, bool):
        raise ValueError('start debe ser un número de segundos.')
    start = float(raw)
    if not math.isfinite(start) or start < 0 or start * 44100 >= 2**63:
        raise ValueError('start está fuera de rango.')
    return song, start


class Rpc:
    def __init__(self, token, timeout=3, verify=True):
        if not token:
            raise ValueError('Falta SOUNDFLOW_CLUSTER_TOKEN.')
        self.token, self.timeout, self.verify = token, timeout, verify

    def call(self, method, url, *, trace=None, **kwargs):
        headers = {'X-Cluster-Token': self.token, 'X-Request-ID': trace or uuid.uuid4().hex}
        try:
            return requests.request(method, url, timeout=(self.timeout, self.timeout),
                                    headers=headers, verify=self.verify, **kwargs)
        except requests.RequestException as exc:
            raise DependencyError('Un servicio no respondió; vuelve a intentar.') from exc

    def json(self, method, url, **kwargs):
        response = self.call(method, url, **kwargs)
        try:
            data = response.json()
        except ValueError as exc:
            raise DependencyError('Un servicio devolvió una respuesta incompatible.') from exc
        if not isinstance(data, dict):
            raise DependencyError('Un servicio devolvió un contrato incompatible.')
        if response.status_code >= 500:
            raise DependencyError('Un servicio está temporalmente fuera de servicio.')
        return data, response.status_code
