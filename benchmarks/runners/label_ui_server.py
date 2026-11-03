"""A local web page for labelling your own blank label files: `annotate.py serve <annotator>`.

Standard library only. It listens on 127.0.0.1, answers only requests that carry the session
token, whose Host is this server and whose Origin (when sent) is this server, and loads nothing
from anywhere else, so private runs never leave the machine.
"""

from __future__ import annotations

import hmac
import json
import secrets
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit

from label_ui_api import ErrorBody, LabelApi, Reply
from label_ui_page import content_security_policy, page

MAX_BODY = 2_000_000
TOKEN_HEADER = "X-Attest-Token"


class LabelServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, api: LabelApi, port: int = 0, token: str | None = None) -> None:
        super().__init__(("127.0.0.1", port), LabelHandler)
        self.api = api
        self.token = token or secrets.token_urlsafe(32)
        self.port = self.server_address[1]
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.origins = {f"http://{host}" for host in self.hosts}

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?token={quote(self.token)}"


class LabelHandler(BaseHTTPRequestHandler):
    server_version = "attest-labels"
    sys_version = ""

    def do_GET(self) -> None:
        self._handle("GET")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_POST(self) -> None:
        self._handle("POST")

    def log_message(self, format: str, *args: object) -> None:
        """Say nothing: request lines carry the token."""

    def _handle(self, method: str) -> None:
        server = self.server
        assert isinstance(server, LabelServer)
        refusal = self._refusal(server)
        if refusal is not None:
            self._send(Reply(status=HTTPStatus.FORBIDDEN, body=ErrorBody(error=refusal)))
            return
        path = unquote(urlsplit(self.path).path)
        if method == "GET" and path == "/":
            self._send_page()
            return
        body: object = None
        if method != "GET":
            body = self._body()
            if body is _BAD_BODY:
                self._send(
                    Reply(status=HTTPStatus.BAD_REQUEST, body=ErrorBody(error="invalid JSON"))
                )
                return
        self._send(server.api.handle(method, path, body))

    def _refusal(self, server: LabelServer) -> str | None:
        """Why this request is refused, or None. Checked before anything is read."""
        if self.headers.get("Host") not in server.hosts:
            return "wrong Host header"
        origin = self.headers.get("Origin")
        if origin is not None and origin not in server.origins:
            return "cross-origin requests are refused"
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return "cross-site requests are refused"
        query = parse_qs(urlsplit(self.path).query).get("token", [""])[0]
        given = self.headers.get(TOKEN_HEADER) or query
        if not hmac.compare_digest(given.encode(), server.token.encode()):
            return "missing or wrong token: open the link the serve command printed"
        return None

    def _body(self) -> object:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return _BAD_BODY
        if length <= 0 or length > MAX_BODY:
            return _BAD_BODY
        try:
            return json.loads(self.rfile.read(length))
        except ValueError:
            return _BAD_BODY

    def _send_page(self) -> None:
        nonce = secrets.token_urlsafe(16)
        content = page(nonce).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Security-Policy", content_security_policy(nonce))
        self._finish(content)

    def _send(self, reply: Reply) -> None:
        content = reply.body.model_dump_json().encode()
        self.send_response(reply.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self._finish(content)

    def _finish(self, content: bytes) -> None:
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(content)


_BAD_BODY = object()


def serve(api: LabelApi, *, port: int = 0, open_browser: bool = True) -> int:
    """Serve the labelling page until interrupted."""
    server = LabelServer(api, port)
    print(f"Labelling {api.store.folder} at\n  {server.url}\nPress Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0
