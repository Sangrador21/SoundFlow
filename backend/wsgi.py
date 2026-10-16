"""Gunicorn carga este módulo en el worker, nunca mediante --preload."""
import atexit
import logging

from soundflow.factory import create_server

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
server = create_server()
app = server.app
app.extensions['soundflow'] = server
atexit.register(server.close)
