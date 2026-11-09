import atexit
import logging

from .settings import create_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
service = create_service()
app = service.app
app.extensions['soundflow'] = service
atexit.register(service.close)
