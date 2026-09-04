"""A minimal token-authenticated HTTP object store.

Implements the contract expected by
:class:`osi_sandbox.storage.http_token.HttpTokenStorageBackend`:

- ``PUT  /<key>``            store bytes                       -> 201
- ``GET  /<key>``            -> 200 + bytes | 404
- ``HEAD /<key>``            -> 200 | 404
- ``GET  /?prefix=<prefix>`` -> 200 JSON ``{"keys": [...]}``

Every request must present ``Authorization: Bearer <token>`` matching the
configured token, otherwise the server responds ``401``. Used by the test
suite and runnable standalone for end-to-end demos:

    python -m tests.http_object_store --token secret --port 9110
"""

from __future__ import annotations

import argparse
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse


def _make_handler(objects: dict[str, bytes], token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # quiet
            pass

        def _authed(self) -> bool:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {token}":
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"unauthorized"}')
                return False
            return True

        def _key(self) -> str:
            return unquote(urlparse(self.path).path).lstrip("/")

        def do_PUT(self) -> None:
            if not self._authed():
                return
            length = int(self.headers.get("Content-Length", 0))
            objects[self._key()] = self.rfile.read(length)
            self.send_response(201)
            self.end_headers()

        def do_HEAD(self) -> None:
            if not self._authed():
                return
            self.send_response(200 if self._key() in objects else 404)
            self.end_headers()

        def do_GET(self) -> None:
            if not self._authed():
                return
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path == "/":
                prefix = (parse_qs(parsed.query).get("prefix", [""]) or [""])[0]
                keys = [k for k in sorted(objects) if k.startswith(prefix)]
                body = json.dumps({"keys": keys}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            key = path.lstrip("/")
            if key not in objects:
                self.send_response(404)
                self.end_headers()
                return
            data = objects[key]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


@contextmanager
def running_object_store(token: str) -> Iterator[tuple[str, dict[str, bytes]]]:
    """Run the store on an ephemeral port; yields ``(base_url, objects)``."""
    objects: dict[str, bytes] = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(objects, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield f"http://{host}:{port}", objects
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="token object store")
    parser.add_argument("--token", required=True)
    parser.add_argument("--port", type=int, default=9110)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    objects: dict[str, bytes] = {}
    server = ThreadingHTTPServer((args.host, args.port), _make_handler(objects, args.token))
    print(f"object store listening on http://{args.host}:{args.port} (bearer token required)")
    server.serve_forever()


if __name__ == "__main__":
    main()
