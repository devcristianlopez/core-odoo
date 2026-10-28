"""Minimal Docker stats exporter.

Docker 29 uses the containerd image store (snapshotter `overlayfs`), where
cAdvisor cannot resolve container layers and drops every container. This
exporter reads the Docker API over the socket and publishes cAdvisor-compatible
names, so the panel and the Grafana dashboards keep working:

    container_cpu_usage_seconds_total
    container_memory_working_set_bytes
    container_last_seen
"""

from __future__ import annotations

import http.client
import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOCKET_PATH = "/var/run/docker.sock"
PORT = 9101


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str) -> None:
        super().__init__("localhost", timeout=5)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect(self.socket_path)


def docker_get(path: str) -> object | None:
    connection = UnixHTTPConnection(SOCKET_PATH)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        if response.status >= 400:
            return None
        return json.loads(body) if body else None
    except (OSError, ValueError):
        return None
    finally:
        connection.close()


def escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def labels(container: dict) -> str:
    raw = container.get("Labels") or {}
    name = (container.get("Names") or ["/unknown"])[0].lstrip("/")
    pairs = [f'name="{escape(name)}"']
    for key, value in sorted(raw.items()):
        if key.startswith("com.docker.compose."):
            metric_key = "container_label_" + key.replace(".", "_").replace("-", "_")
            pairs.append(f'{metric_key}="{escape(str(value))}"')
    return ",".join(pairs)


def render() -> str:
    containers = docker_get("/containers/json")
    if not isinstance(containers, list):
        return "# docker API unavailable\n"
    now = time.time()
    lines = [
        "# HELP container_cpu_usage_seconds_total Cumulative CPU time in seconds.",
        "# TYPE container_cpu_usage_seconds_total counter",
        "# HELP container_memory_working_set_bytes Current memory usage in bytes.",
        "# TYPE container_memory_working_set_bytes gauge",
        "# HELP container_last_seen Last time the container was seen.",
        "# TYPE container_last_seen gauge",
    ]
    for container in containers:
        container_id = container.get("Id") or ""
        if not container_id:
            continue
        stats = docker_get(f"/containers/{container_id}/stats?stream=false&one-shot=true")
        if not isinstance(stats, dict):
            continue
        base = labels(container)
        cpu = (
            ((stats.get("cpu_stats") or {}).get("cpu_usage") or {}).get("total_usage") or 0
        )
        memory = (stats.get("memory_stats") or {}).get("usage") or 0
        lines.append(f"container_cpu_usage_seconds_total{{{base}}} {cpu / 1e9}")
        lines.append(f"container_memory_working_set_bytes{{{base}}} {memory}")
        lines.append(f"container_last_seen{{{base}}} {now}")
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        body = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
