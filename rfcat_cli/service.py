import argparse
import json
import logging
import subprocess
from pathlib import Path
from http.client import LineTooLong
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .tx import DEFAULT_MANUFACTURER_DIR, transmit_command


DEFAULT_TX_CLI_PATH = Path(__file__).resolve().parent.parent / "rfcat-tx-cmd"


def _write_json(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Connection", "close")
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    handler.close_connection = True


def _looks_like_tls_handshake(raw_requestline):
    return len(raw_requestline) >= 3 and raw_requestline[0] == 0x16 and raw_requestline[1] == 0x03


def transmit_via_cli(
    manufacturer,
    command,
    manufacturer_dir=DEFAULT_MANUFACTURER_DIR,
    manu_path=None,
    cli_path=DEFAULT_TX_CLI_PATH,
    timeout=30,
):
    cli_path = Path(cli_path)
    cmd = [str(cli_path), "-d", manufacturer_dir]
    if manu_path:
        cmd.extend(["-m", manu_path])
    cmd.extend([manufacturer, command])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"tx CLI not found: {cli_path}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"tx CLI timed out after {timeout}s") from exc

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        if details:
            raise RuntimeError(f"tx CLI failed ({result.returncode}): {details}")
        raise RuntimeError(f"tx CLI failed ({result.returncode})")


def create_handler(transmit=transmit_command, manufacturer_dir=DEFAULT_MANUFACTURER_DIR, manu_path=None):
    class TxHandler(BaseHTTPRequestHandler):
        def handle_one_request(self):
            try:
                self.raw_requestline = self.rfile.readline(65537)
                if len(self.raw_requestline) > 65536:
                    self.requestline = ""
                    self.request_version = ""
                    self.command = ""
                    self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG)
                    return
                if not self.raw_requestline:
                    self.close_connection = True
                    return
                if _looks_like_tls_handshake(self.raw_requestline):
                    logging.debug("Ignoring TLS handshake on plain HTTP port from %s", self.address_string())
                    self.close_connection = True
                    return
                if not self.parse_request():
                    return
                method_name = f"do_{self.command}"
                if not hasattr(self, method_name):
                    self.send_error(
                        HTTPStatus.NOT_IMPLEMENTED,
                        "Unsupported method (%r)" % self.command,
                    )
                    return
                method = getattr(self, method_name)
                method()
                self.wfile.flush()
            except TimeoutError as exc:
                self.log_error("Request timed out: %r", exc)
                self.close_connection = True
                return
            except LineTooLong:
                self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG)
                return

        def do_GET(self):
            manufacturer, command = self._parse_tx_path()
            if manufacturer is None:
                _write_json(
                    self,
                    HTTPStatus.NOT_FOUND,
                    {"error": "expected /tx/<manufacturer>/<cmd>"},
                )
                return

            try:
                transmit(
                    manufacturer,
                    command,
                    manufacturer_dir=manufacturer_dir,
                    manu_path=manu_path,
                )
            except KeyError as exc:
                _write_json(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            except Exception as exc:  # pylint: disable=broad-exception-caught  # pragma: no cover
                logging.exception("Transmit failed")
                _write_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            _write_json(
                self,
                HTTPStatus.OK,
                {
                    "manufacturer": manufacturer,
                    "command": command,
                    "status": "sent",
                },
            )

        def log_message(self, fmt, *args):
            logging.info("%s - %s", self.address_string(), fmt % args)

        def _parse_tx_path(self):
            path = self.path.split("?", 1)[0].rstrip("/")
            parts = path.split("/")

            if len(parts) != 4 or parts[1] != "tx":
                return None, None

            return parts[2], parts[3]

    return TxHandler


def serve(
    host="0.0.0.0",
    port=8080,
    manufacturer_dir=DEFAULT_MANUFACTURER_DIR,
    manu_path=None,
    transmit=transmit_command,
):
    server = ThreadingHTTPServer(
        (host, port),
        create_handler(transmit=transmit, manufacturer_dir=manufacturer_dir, manu_path=manu_path),
    )
    logging.info("Starting rfcat tx service on %s:%s", host, port)
    server.serve_forever()


def _configure_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler("rfcat-tx-service.log", mode="w"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("-v", "--verbose", action="store_true", help="enable verbose debug logging")
    parser.add_argument("-m", "--manu", help="use a single manufacturer file")
    parser.add_argument(
        "--tx-cli",
        default=str(DEFAULT_TX_CLI_PATH),
        help="path to rfcat-tx-cmd executable for isolated transmit",
    )
    parser.add_argument(
        "--tx-timeout",
        type=int,
        default=30,
        help="seconds to wait for rfcat-tx-cmd before failing",
    )
    parser.add_argument(
        "-d",
        "--dir",
        help="set directory to search for manufacturer YAML files",
        default=DEFAULT_MANUFACTURER_DIR,
    )
    args = parser.parse_args()

    _configure_logging(verbose=args.verbose)
    logging.debug("rfcat-tx-service args: %s", args)

    def _transmit(manufacturer, command, **kwargs):
        transmit_via_cli(
            manufacturer,
            command,
            manufacturer_dir=kwargs.get("manufacturer_dir", args.dir),
            manu_path=kwargs.get("manu_path", args.manu),
            cli_path=args.tx_cli,
            timeout=args.tx_timeout,
        )

    serve(host=args.host, port=args.port, manufacturer_dir=args.dir, manu_path=args.manu, transmit=_transmit)


if __name__ == "__main__":
    main()