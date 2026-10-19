"""`scripts/cluster_runner.py: wait_health`: a coordinator that answers 401 (it wants a token; the health check carries none) is UP; a dead port is not."""
import http.server
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import cluster_runner as cr  # noqa: E402


def serve(status):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_a_401_means_the_coordinator_is_up():
    server = serve(401)
    try:
        cr.wait_health(f"http://127.0.0.1:{server.server_port}", 5)
    finally:
        server.shutdown()


def test_a_200_means_the_coordinator_is_up():
    server = serve(200)
    try:
        cr.wait_health(f"http://127.0.0.1:{server.server_port}", 5)
    finally:
        server.shutdown()


def test_a_500_does_not_count_as_up():
    server = serve(500)
    try:
        with pytest.raises(TimeoutError):
            cr.wait_health(f"http://127.0.0.1:{server.server_port}", 2)
    finally:
        server.shutdown()


def test_a_closed_port_does_not_count_as_up():
    server = serve(200)
    port = server.server_port
    server.shutdown()
    server.server_close()
    with pytest.raises(TimeoutError):
        cr.wait_health(f"http://127.0.0.1:{port}", 2)
