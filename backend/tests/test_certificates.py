"""TLS estricto: compatibilidad con Python 3.13+ sin relajar verificación."""
import http.server
import socket
import ssl
import threading

import pytest

from tools.create_cert import create_certificate


def test_strict_tls_accepts_valid_names_and_rejects_invalid_trust(tmp_path):
    certs = tmp_path / 'certs'
    create_certificate(certs, [])

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certs / 'server.pem', certs / 'server-key.pem')
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = ssl.create_default_context(cafile=str(certs / 'ca.pem'))
    context.verify_flags |= ssl.VERIFY_X509_STRICT

    def fetch(client_context, hostname):
        with socket.create_connection(server.server_address, timeout=3) as raw:
            with client_context.wrap_socket(raw, server_hostname=hostname) as connection:
                connection.sendall(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
                return connection.recv(4096)

    try:
        for hostname in ['localhost', '127.0.0.1']:
            assert b'200 OK' in fetch(context, hostname)
        with pytest.raises(ssl.SSLCertVerificationError):
            fetch(context, 'wrong.invalid')
        other_certs = tmp_path / 'other'
        create_certificate(other_certs, [])
        untrusted = ssl.create_default_context(cafile=str(other_certs / 'ca.pem'))
        untrusted.verify_flags |= ssl.VERIFY_X509_STRICT
        with pytest.raises(ssl.SSLCertVerificationError):
            fetch(untrusted, 'localhost')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
