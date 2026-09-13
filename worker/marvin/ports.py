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
    """How a port on this machine is reachable from a browser.

    Public installs: a child of this machine's hostname (`p3000.marvin.example.com`).
    Older k8s ingress: a sibling on the parent zone (`marvin-3000.example.com`) when only
    `MARVIN_APPS_DOMAIN` is set. Local dev with neither: `http://localhost:{port}`.
    """

    domain: str | None = None
    prefix: str = "marvin-"
    routed_ports: frozenset[int] = frozenset()  # ports with an ingress host; empty = all (local / edge)

    @classmethod
    def from_env(cls, env=os.environ) -> "AppsRouting":
        host = (env.get("MARVIN_APPS_HOST") or env.get("MARVIN_DOMAIN") or "").strip() or None
        legacy = (env.get("MARVIN_APPS_DOMAIN") or "").strip() or None
        ports = frozenset(int(p) for p in env.get("MARVIN_APPS_PORTS", "").replace(" ", "").split(",") if p)
        if host:
            return cls(domain=host, prefix=env.get("MARVIN_APPS_PREFIX", "p"), routed_ports=ports)
        if legacy:
            return cls(domain=legacy, prefix=env.get("MARVIN_APPS_PREFIX", "marvin-"), routed_ports=ports)
        return cls(routed_ports=ports)

    def link(self, port: int) -> dict:
        if self.domain is None:
            return {"label": f"port {port}", "url": f"http://localhost:{port}"}
        if self.routed_ports and port not in self.routed_ports:
            return {"label": f"port {port} (no URL: add it to the apps port list)", "url": ""}
        return {"label": f"port {port}", "url": f"https://{self.prefix}{port}.{self.domain}"}

    def preview_pattern(self) -> str | None:
        if not self.domain:
            return None
        return f"https://{self.prefix}{{port}}.{self.domain}"

    def allows_preview_host(self, name: str) -> bool:
        """True when `name` is a preview host we will get a certificate for (Caddy on-demand TLS ask)."""
        if not self.domain or not name:
            return False
        host = name.split(":")[0].strip(".").lower()
        suffix = "." + self.domain.lower()
        if not host.endswith(suffix):
            return False
        label = host[: -len(suffix)]
        if not label or "." in label or not label.startswith(self.prefix.lower()):
            return False
        rest = label[len(self.prefix) :]
        if not rest.isdigit():
            return False
        port = int(rest)
        return 1 <= port <= 65535 and port not in OWN_PORTS
