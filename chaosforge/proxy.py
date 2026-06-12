"""A fault-injecting HTTP reverse proxy.

The proxy sits between a client and a target service and forwards traffic
unchanged until a fault is *armed*. Faults are toggled at runtime by the
experiment runner so the same proxy can serve a clean baseline and then a
degraded window without restarting.

Implemented with the standard library only (no extra runtime deps) so it is
trivial to drop in front of any HTTP service.
"""

from __future__ import annotations

import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional


@dataclass
class FaultConfig:
    """Runtime-tunable fault parameters. Mutated by the runner while serving."""

    # Added latency in milliseconds applied to every proxied request.
    latency_ms: int = 0
    # Probability [0, 1] that a request is failed with `error_status`.
    error_rate: float = 0.0
    error_status: int = 503
    # Probability [0, 1] that a connection is "blackholed" (dropped with no reply).
    blackhole_rate: float = 0.0

    enabled: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def arm(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)
            self.enabled = True

    def disarm(self) -> None:
        with self._lock:
            self.latency_ms = 0
            self.error_rate = 0.0
            self.blackhole_rate = 0.0
            self.enabled = False

    def snapshot(self) -> "FaultConfig":
        with self._lock:
            return FaultConfig(
                latency_ms=self.latency_ms,
                error_rate=self.error_rate,
                error_status=self.error_status,
                blackhole_rate=self.blackhole_rate,
                enabled=self.enabled,
            )


class _ProxyHandler(BaseHTTPRequestHandler):
    # Set by FaultProxy before the server starts.
    target_base: str = ""
    fault: FaultConfig = FaultConfig()
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # silence default stderr logging
        pass

    def _handle(self) -> None:
        cfg = self.fault.snapshot()

        if cfg.enabled:
            if cfg.blackhole_rate and random.random() < cfg.blackhole_rate:
                # Drop the connection without responding.
                try:
                    self.connection.close()
                finally:
                    return
            if cfg.latency_ms:
                time.sleep(cfg.latency_ms / 1000.0)
            if cfg.error_rate and random.random() < cfg.error_rate:
                self._send_error_response(cfg.error_status)
                return

        self._forward()

    def _send_error_response(self, status: int) -> None:
        body = b'{"error": "chaos-forge injected fault"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Chaos-Forge", "injected")
        self.end_headers()
        self.wfile.write(body)

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else None
        url = self.target_base.rstrip("/") + self.path

        req = urllib.request.Request(url, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() in ("host", "content-length"):
                continue
            req.add_header(key, value)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() in ("transfer-encoding", "content-length", "connection"):
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            self._send_error_response(502)

    # Map every common verb to the same handler.
    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle
    do_HEAD = _handle


class FaultProxy:
    """Run a fault-injecting reverse proxy in a background thread."""

    def __init__(self, target_base: str, host: str = "127.0.0.1", port: int = 0):
        self.target_base = target_base
        self.host = host
        self.fault = FaultConfig()

        handler = type(
            "BoundProxyHandler",
            (_ProxyHandler,),
            {"target_base": target_base, "fault": self.fault},
        )
        self._server = ThreadingHTTPServer((host, port), handler)
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> "FaultProxy":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self) -> "FaultProxy":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
