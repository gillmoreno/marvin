"""Detect TCP ports listening in this network namespace (dind-published app ports show up here too)."""
from __future__ import annotations

import os
from dataclasses import dataclass

# Ports that belong to Marvin's own plumbing, never shown as app links.
OWN_PORTS = {2375, 3478, 7880, 7881, 7882, 8080, 8081, 8090}


def listening_ports(proc_root: str = "/proc") -> set[int]:
    ports: set[int] = set()
    for name in ("net/tcp", "net/tcp6"):
        try:
            with open(os.path.join(proc_root, name)) as f:
                next(f)  # header
                for line in f:
                    parts = line.split()
                    if len(parts) > 3 and parts[3] == "0A":  # LISTEN
                        ports.add(int(parts[1].rsplit(":", 1)[1], 16))
        except (FileNotFoundError, StopIteration):
            continue
    return {p for p in ports if p not in OWN_PORTS and p < 30000}  # relay/ICE ranges live above


@dataclass(frozen=True)
class AppsRouting:
    """How a port on this machine is reachable from a browser."""

    domain: str | None = None  # e.g. example.com -> https://marvin-3000.<domain>
    prefix: str = "marvin-"
    routed_ports: frozenset[int] = frozenset()  # ports with an ingress host (the `ports` list in rooms.yaml); empty = all (local dev)

    @classmethod
    def from_env(cls, env=os.environ) -> "AppsRouting":
        domain = env.get("MARVIN_APPS_DOMAIN") or None
        ports = frozenset(int(p) for p in env.get("MARVIN_APPS_PORTS", "").replace(" ", "").split(",") if p)
        return cls(domain=domain, prefix=env.get("MARVIN_APPS_PREFIX", "marvin-"), routed_ports=ports)

    def link(self, port: int) -> dict:
        if self.domain is None:
            return {"label": f"port {port}", "url": f"http://localhost:{port}"}
        if self.routed_ports and port not in self.routed_ports:
            return {"label": f"port {port} (no URL: add it to the apps port list)", "url": ""}
        return {"label": f"port {port}", "url": f"https://{self.prefix}{port}.{self.domain}"}
