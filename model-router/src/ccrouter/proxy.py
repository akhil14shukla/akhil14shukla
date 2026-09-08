"""A pass-through reverse proxy for the Anthropic API that rewrites `model`.

Point Claude Code at it with ANTHROPIC_BASE_URL. Everything except the model
field on /v1/messages is relayed byte for byte, credentials included, so
subscription auth and streaming keep working. If anything in the routing path
raises, the original request is forwarded untouched -- the proxy fails open.
"""

from __future__ import annotations

import http.client
import json
import socket
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import Config, tier_name
from .router import Router

# Headers that describe this hop only and must not be forwarded.
_HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length",
})

_ROUTED_PATHS = ("/v1/messages",)
_NEVER_ROUTED = ("/v1/messages/count_tokens", "/v1/messages/batches")


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ccrouter"
    sys_version = ""

    # -- plumbing ---------------------------------------------------------
    @property
    def cfg(self) -> Config:
        return self.server.cfg           # type: ignore[attr-defined]

    @property
    def router(self) -> Router:
        return self.server.router        # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        if getattr(self.server, "verbose", False):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _read_body(self) -> bytes:
        length = int(self.headers.get("content-length") or 0)
        return self.rfile.read(length) if length else b""

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, indent=1).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- verbs ------------------------------------------------------------
    def do_GET(self) -> None:      # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/__router/healthz":
            return self._json(200, {"ok": True, "upstream": self.cfg.upstream,
                                    "tiers": self.cfg.tiers})
        if path == "/__router/stats":
            return self._json(200, self.router.savings())
        self._relay(b"")

    def do_POST(self) -> None:     # noqa: N802
        self._relay(self._read_body())

    do_PUT = do_DELETE = do_PATCH = do_POST

    # -- the interesting part ---------------------------------------------
    def _route(self, body: bytes) -> tuple[bytes, dict[str, str]]:
        path = urllib.parse.urlparse(self.path).path
        if self.command != "POST" or not body:
            return body, {}
        if path in _NEVER_ROUTED or not any(path.startswith(p) for p in _ROUTED_PATHS):
            return body, {}
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or "model" not in payload:
                return body, {}
            decision = self.router.decide(payload)
        except Exception as exc:                       # fail open, always
            self.log_message("routing skipped: %r", exc)
            return body, {"x-ccrouter-error": type(exc).__name__}

        self.log_message("%s", decision.summary())
        if not decision.rewrote:
            return body, {"x-ccrouter-tier": tier_name(decision.tier),
                          "x-ccrouter-source": decision.source}
        payload["model"] = decision.model
        return json.dumps(payload).encode(), {
            "x-ccrouter-tier": tier_name(decision.tier),
            "x-ccrouter-source": decision.source,
            "x-ccrouter-from": decision.original_model,
        }

    def _connect(self) -> http.client.HTTPConnection:
        url = urllib.parse.urlparse(self.cfg.upstream)
        host, port = url.hostname or "api.anthropic.com", url.port
        if url.scheme == "http":
            return http.client.HTTPConnection(host, port or 80, timeout=900)
        conn = http.client.HTTPSConnection(host, port or 443, timeout=900)
        return conn

    def _relay(self, body: bytes) -> None:
        body, extra = self._route(body)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in _HOP_BY_HOP}
        if body:
            headers["content-length"] = str(len(body))

        base = urllib.parse.urlparse(self.cfg.upstream)
        target = (base.path.rstrip("/") + self.path) or self.path

        try:
            conn = self._connect()
            conn.request(self.command, target, body=body or None, headers=headers)
            upstream = conn.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            return self._json(502, {"type": "error", "error": {
                "type": "ccrouter_upstream_error", "message": f"{type(exc).__name__}: {exc}"}})

        try:
            self._send_response(upstream, extra)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            conn.close()

    def _send_response(self, upstream: http.client.HTTPResponse, extra: dict[str, str]) -> None:
        declared_length = upstream.getheader("content-length")
        self.send_response(upstream.status, upstream.reason)
        for name, value in upstream.getheaders():
            if name.lower() not in _HOP_BY_HOP:
                self.send_header(name, value)
        for name, value in extra.items():
            self.send_header(name, value)

        if declared_length is not None:
            payload = upstream.read()
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # Streaming (SSE). http.client already de-chunks, so re-chunk on the way out.
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()
        while True:
            chunk = upstream.read(8192)
            if not chunk:
                break
            self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
            self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, cfg: Config, verbose: bool = False) -> None:
        host, _, port = cfg.listen.rpartition(":")
        super().__init__((host or "127.0.0.1", int(port)), _Handler)
        self.cfg = cfg
        self.router = Router(cfg)
        self.verbose = verbose

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


def serve(cfg: Config, verbose: bool = True) -> ProxyServer:
    server = ProxyServer(cfg, verbose=verbose)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
