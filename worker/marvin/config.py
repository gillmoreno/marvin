"""rooms.yaml: which rooms exist, which repo each one works in, and which app URLs to show."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True)
class AppLink:
    label: str
    url: str
    port: int | None = None  # set when the app is served from this Pod and needs a Service+Ingress (see deploy/gen_apps.py)

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or ""

    def to_wire(self) -> dict:
        return {"label": self.label, "url": self.url}


@dataclass(frozen=True)
class RoomConfig:
    name: str
    repo: str  # working directory for the harness
    git_url: str | None = None  # cloned into `repo` on first start when the directory is missing
    branch: str | None = None
    model: str | None = None
    language: str | None = None  # force STT language, e.g. "en"
    app_links: tuple[AppLink, ...] = field(default_factory=tuple)
    linked: tuple[str, ...] = field(default_factory=tuple)  # other repos this room may read/edit (harness add_dirs)


@dataclass(frozen=True)
class Config:
    rooms: tuple[RoomConfig, ...]

    def room(self, name: str) -> RoomConfig | None:
        return next((r for r in self.rooms if r.name == name), None)


def load_config(path: str | Path) -> Config:
    data = yaml.safe_load(Path(path).read_text()) or {}
    rooms = []
    for r in data.get("rooms", []):
        links = tuple(AppLink(label=l["label"], url=l["url"], port=l.get("port")) for l in r.get("app_links", []))
        rooms.append(RoomConfig(name=r["name"], repo=r["repo"], git_url=r.get("git_url"), branch=r.get("branch"), model=r.get("model"), language=r.get("language"), app_links=links, linked=tuple(r.get("linked", []))))
    names = [r.name for r in rooms]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate room names in {path}")
    return Config(rooms=tuple(rooms))
