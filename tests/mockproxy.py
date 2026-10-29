"""A stand-in for one Singapore Mobile Proxy line, for tests and for trying the quickstart offline.

One local server plays three parts:
  * the HTTP proxy port (absolute-URI requests, Basic proxy auth)
  * the sites behind it: /json answers like ipinfo.io, /page returns 403 to "blocked" IPs
  * the rotation link: GET /rotate/<token> hands the line a new IP, with a cooldown

    python tests/mockproxy.py          # prints the env vars to export, then serves until Ctrl+C
"""

from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

USER, PASSWORD, TOKEN = "smpuser", "p@ss:w/rd", "tok123"


class State:
    def __init__(self, cooldown: float = 0.0, blocked_ips=()):
        self.n = 1
        self.cooldown = cooldown
        self.blocked = set(blocked_ips)
        self.last_rotate = 0.0
        self.rotations = 0
        self.latency = 0.0  # seconds each proxied request takes
        self.proxied = []  # (ip, path) for every request that came through the proxy
        self.lock = threading.Lock()

    @property
    def ip(self) -> str:
        return f"203.0.113.{self.n}"


class Handler(BaseHTTPRequestHandler):
    state: State

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json", headers=None):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        st = self.state
        if self.path.startswith("http://"):
            return self._proxy(urlsplit(self.path).path)
        if self.path == f"/rotate/{TOKEN}" or (
                self.path.startswith("/api/v1/proxy/change-ip") and self.headers.get("x-api-key") == "sk_test"):
            with st.lock:
                wait = st.cooldown - (time.monotonic() - st.last_rotate)
                if st.last_rotate and wait > 0:
                    return self._send(429, json.dumps({"detail": "rotating too often"}),
                                      headers={"Retry-After": str(int(wait) + 1)})
                st.last_rotate = time.monotonic()
                st.n += 1
                st.rotations += 1
            return self._send(200, json.dumps({"success": True, "message": "IP rotation triggered"}))
        if self.path.startswith("/rotate/"):
            return self._send(410, "this rotation link no longer exists", "text/plain")
        if self.path.startswith("/api/v1/"):
            return self._send(401, json.dumps({"detail": "bad api key"}))
        self._send(404, "not found", "text/plain")

    def _proxy(self, path):
        st = self.state
        expected = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
        if self.headers.get("Proxy-Authorization") != expected:
            return self._send(407, "proxy auth required", "text/plain", {"Proxy-Authenticate": 'Basic realm="smp"'})
        ip = st.ip
        time.sleep(st.latency)
        with st.lock:
            st.proxied.append((ip, path))
        if path == "/json":
            return self._send(200, json.dumps({"ip": ip, "country": "SG", "org": "AS45143 Singtel Mobile"}))
        if path.startswith("/page"):
            if ip in st.blocked:
                return self._send(403, f"blocked {ip}", "text/plain")
            return self._send(200, f"ok from {ip}", "text/plain")
        self._send(404, "no such page", "text/plain")


def start(cooldown: float = 0.0, blocked_ips=(), port: int = 0):
    """Start in a background thread. Returns (server, state, env) where env holds the SMP_* variables."""
    state = State(cooldown, blocked_ips)
    handler = type("H", (Handler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    p = server.server_address[1]
    env = {
        "SMP_PROXY": f"127.0.0.1:{p}:{USER}:{PASSWORD}",
        "SMP_ROTATE_URL": f"http://127.0.0.1:{p}/rotate/{TOKEN}",
        "SMP_IP_INFO_URL": "http://ipinfo.test/json",
    }
    return server, state, env


if __name__ == "__main__":
    srv, st, env = start(cooldown=10, port=8899)
    for k, v in env.items():
        print(f"export {k}='{v}'")
    print("# serving on 127.0.0.1:8899, Ctrl+C to stop", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.shutdown()
