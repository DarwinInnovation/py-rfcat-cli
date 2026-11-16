import io
import json
import logging
import socket
import ssl
import threading
import time
import unittest
from unittest import mock

from http.server import ThreadingHTTPServer

from rfcat_cli.service import create_handler, transmit_via_cli


class _StubServer:
    server_version = "Test"
    sys_version = ""


class _HandlerHarness:
    def __init__(self, path, transmit):
        self.path = path
        self.transmit = transmit
        self.response = None

    def run(self):
        request = object.__new__(create_handler(transmit=self.transmit))
        request.path = self.path
        request.wfile = io.BytesIO()
        request.request_version = "HTTP/1.1"
        request.command = "GET"
        request.server = _StubServer()
        request.client_address = ("127.0.0.1", 0)
        request.send_response = lambda status: setattr(request, "status", status)
        request.send_header = lambda *_args: None
        request.end_headers = lambda: None
        request.address_string = lambda: "127.0.0.1"
        request.do_GET()
        self.response = {
            "status": request.status,
            "body": json.loads(request.wfile.getvalue().decode("utf-8")),
        }
        return self.response


class ServiceRouteTests(unittest.TestCase):
    def test_tx_route_dispatches_transmit(self):
        calls = []

        def transmit(manufacturer, command, **kwargs):
            calls.append((manufacturer, command, kwargs))

        response = _HandlerHarness("/tx/neet/door_unlock", transmit).run()

        self.assertEqual(response["status"], 200)
        self.assertEqual(response["body"]["status"], "sent")
        self.assertEqual(calls, [("neet", "door_unlock", {"manufacturer_dir": "/etc/rfcat-cli/manufacturers", "manu_path": None})])

    def test_unknown_path_returns_404(self):
        response = _HandlerHarness("/health", lambda *_args, **_kwargs: None).run()

        self.assertEqual(response["status"], 404)
        self.assertEqual(response["body"]["error"], "expected /tx/<manufacturer>/<cmd>")

    def test_transmit_key_error_returns_404(self):
        def transmit(*_args, **_kwargs):
            raise KeyError("missing manufacturer")

        response = _HandlerHarness("/tx/neet/door_unlock", transmit).run()

        self.assertEqual(response["status"], 404)
        self.assertEqual(response["body"]["error"], "'missing manufacturer'")

    def test_service_closes_connection_after_response(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(transmit=lambda *_args, **_kwargs: None))
        thread = threading.Thread(target=server.handle_request)
        thread.start()

        try:
            time.sleep(0.05)
            client = socket.create_connection(server.server_address, timeout=2)
            try:
                client.sendall(b"GET /tx/neet/door_unlock HTTP/1.1\r\nHost: localhost\r\n\r\n")

                # Reading to EOF only succeeds (rather than timing out) if the server closes the connection.
                chunks = []
                while chunk := client.recv(4096):
                    chunks.append(chunk)
                response = b"".join(chunks).decode("latin1")

                self.assertIn("Connection: close", response)
                self.assertIn('"status": "sent"', response)
            finally:
                client.close()
        finally:
            thread.join(timeout=2)
            server.server_close()

    def test_tls_handshake_on_http_port_is_ignored_without_400_log(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(transmit=lambda *_args, **_kwargs: None))
        thread = threading.Thread(target=server.handle_request)
        logger = logging.getLogger()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        previous_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        thread.start()

        try:
            time.sleep(0.05)
            context = ssl.create_default_context()
            with self.assertRaises(ssl.SSLError):
                with context.wrap_socket(socket.socket(), server_hostname="localhost") as client:
                    client.settimeout(1)
                    client.connect(server.server_address)
        finally:
            thread.join(timeout=2)
            server.server_close()
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        logs = stream.getvalue()
        self.assertIn("Ignoring TLS handshake on plain HTTP port", logs)
        self.assertNotIn("Bad request version", logs)

    def _assert_server_closes(self, handler_cls, payload):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        thread = threading.Thread(target=server.handle_request)
        thread.start()

        try:
            client = socket.create_connection(server.server_address, timeout=2)
            try:
                client.sendall(payload)
                # Times out (and errors) unless the server closes the connection without waiting for a newline.
                self.assertEqual(client.recv(4096), b"")
            finally:
                client.close()
        finally:
            thread.join(timeout=2)
            server.server_close()

    def test_tls_handshake_without_newline_is_closed(self):
        handler_cls = create_handler(transmit=lambda *_args, **_kwargs: None)
        self._assert_server_closes(handler_cls, b"\x16\x03\x01\x00\x05hello")

    def test_incomplete_request_times_out(self):
        handler_cls = create_handler(transmit=lambda *_args, **_kwargs: None)
        self.assertIsNotNone(handler_cls.timeout)
        handler_cls.timeout = 0.2
        self._assert_server_closes(handler_cls, b"GET /tx/neet")

    def test_concurrent_requests_transmit_one_at_a_time(self):
        active = []
        overlaps = []
        lock = threading.Lock()

        def transmit(*_args, **_kwargs):
            with lock:
                active.append(1)
                if len(active) > 1:
                    overlaps.append(len(active))
            time.sleep(0.1)
            with lock:
                active.pop()

        server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(transmit=transmit))
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.start()

        def request():
            with socket.create_connection(server.server_address, timeout=2) as client:
                client.sendall(b"GET /tx/neet/door_unlock HTTP/1.1\r\nHost: localhost\r\n\r\n")
                while client.recv(4096):
                    pass

        try:
            clients = [threading.Thread(target=request) for _ in range(3)]
            for client in clients:
                client.start()
            for client in clients:
                client.join(timeout=5)
        finally:
            server.shutdown()
            server_thread.join(timeout=2)
            server.server_close()

        self.assertEqual(overlaps, [])


class ServiceCliTransmitTests(unittest.TestCase):
    @mock.patch("rfcat_cli.service.subprocess.run")
    def test_transmit_via_cli_builds_expected_command(self, run_mock):
        run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")

        transmit_via_cli(
            "neet",
            "door_unlock",
            manufacturer_dir="/tmp/manufacturers",
            manu_path="/tmp/neet.yaml",
            cli_path="/tmp/rfcat-tx-cmd",
            timeout=12,
        )

        run_mock.assert_called_once_with(
            [
                "/tmp/rfcat-tx-cmd",
                "-d",
                "/tmp/manufacturers",
                "-m",
                "/tmp/neet.yaml",
                "--",
                "neet",
                "door_unlock",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=12,
        )

    @mock.patch("rfcat_cli.service.subprocess.run")
    def test_transmit_via_cli_raises_on_nonzero_exit(self, run_mock):
        run_mock.return_value = mock.Mock(returncode=3, stdout="", stderr="usb busy")

        with self.assertRaisesRegex(RuntimeError, "tx CLI failed"):
            transmit_via_cli("neet", "door_unlock", cli_path="/tmp/rfcat-tx-cmd")


if __name__ == "__main__":
    unittest.main()