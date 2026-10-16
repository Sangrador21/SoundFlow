import os

bind = '0.0.0.0:' + os.getenv('PORT', '10000')
# Las sesiones y la FIFO se comparten en memoria dentro de este único worker.
workers = 1
worker_class = 'gthread'
threads = int(os.getenv('GUNICORN_THREADS', '16'))
preload_app = False
timeout = 120
graceful_timeout = 20
accesslog = '-'
errorlog = '-'
worker_tmp_dir = '/dev/shm' if os.path.isdir('/dev/shm') else None


def worker_exit(server, worker):
    application = getattr(worker, 'wsgi', None)
    core = getattr(application, 'extensions', {}).get('soundflow')
    if core:
        core.close()
