"""rooms.yaml: which rooms exist, which repos each one works in, and which app URLs to show.

A room is a *project*: one or more repos worked on together (a frontend, its API, a shared library...). The first
repo is where the agent starts (its working directory); every repo is readable and editable. `repo`, `git_url`,
`branch` and `linked` on RoomConfig are derived views of `repos` kept for the code and configs that predate projects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

REPO_ROLES = ("frontend", "api", "worker", "lib", "infra", "docs", "other")  # suggestions; any short word is accepted


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
class ProjectRepo:
    path: str  # absolute directory on the machine (the sandbox mounts it at the same path)
    role: str = ""  # frontend | api | worker | lib | infra | docs | other | ""
    git_url: str | None = None  # cloned into `path` when the directory is missing
    branch: str | None = None

    @property
    def name(self) -> str:
        return Path(self.path).name

    def to_wire(self) -> dict:
        return {"path": self.path, "name": self.name, "role": self.role, "git_url": self.git_url, "branch": self.branch}

    @classmethod
    def from_any(cls, d: "ProjectRepo | dict[str, Any]") -> "ProjectRepo":
        if isinstance(d, ProjectRepo):
            return d
        return cls(path=str(d["path"]), role=str(d.get("role") or ""), git_url=d.get("git_url") or None, branch=d.get("branch") or None)


@dataclass(frozen=True)
class RoomConfig:
    name: str
    repo: str = ""  # working directory for the harness: repos[0].path
    git_url: str | None = None  # repos[0].git_url
    branch: str | None = None  # repos[0].branch
    model: str | None = None
    harness: str | None = None  # profile id from marvin.adapters.registry (claude-code, codex, opencode, ...); None = worker default
    language: str | None = None  # force STT language, e.g. "en"
    app_links: tuple[AppLink, ...] = field(default_factory=tuple)
    linked: tuple[str, ...] = field(default_factory=tuple)  # repos[1:].path: the other project repos (harness add_dirs)
    repos: tuple[ProjectRepo, ...] = field(default_factory=tuple)  # the project; source of truth for the four above

    def __post_init__(self) -> None:
        repos = tuple(ProjectRepo.from_any(r) for r in self.repos)
        if not repos:
            if not self.repo:
                raise ValueError(f"room {self.name!r}: needs at least one repo")
            repos = (ProjectRepo(path=self.repo, git_url=self.git_url, branch=self.branch), *(ProjectRepo(path=p) for p in self.linked))
        seen: set[str] = set()
        deduped = []
        for r in repos:
            if r.path not in seen:
                seen.add(r.path)
                deduped.append(r)
        repos = tuple(deduped)
        object.__setattr__(self, "repos", repos)
        object.__setattr__(self, "repo", repos[0].path)
        object.__setattr__(self, "git_url", repos[0].git_url)
        object.__setattr__(self, "branch", repos[0].branch)
        object.__setattr__(self, "linked", tuple(r.path for r in repos[1:]))

    def repo_for(self, path: str | None) -> ProjectRepo | None:
        """The project repo at `path` (None/"" = the primary)."""
        if not path:
            return self.repos[0]
        return next((r for r in self.repos if r.path == path), None)

    def project_text(self) -> str:
        """One line per repo for the agent's instructions: what is where and what it is for."""
        if len(self.repos) == 1:
            return ""
        lines = ["This room is a project of several repos; all of them are readable and editable:"]
        for i, r in enumerate(self.repos):
            role = f" ({r.role})" if r.role else ""
            here = " <- your working directory" if i == 0 else ""
            lines.append(f"- {r.name}{role}: {r.path}{f' [branch {r.branch}]' if r.branch else ''}{here}")
        return "\n".join(lines)


@dataclass(frozen=True)
class Config:
    rooms: tuple[RoomConfig, ...]

    def room(self, name: str) -> RoomConfig | None:
        return next((r for r in self.rooms if r.name == name), None)


def room_from_dict(r: dict[str, Any]) -> RoomConfig:
    """rooms.yaml / rooms.json record -> RoomConfig. Accepts both the project form (`repos:`) and the old one
    (`repo:` + `linked:`)."""
    r = dict(r)
    links = tuple(AppLink(label=l["label"], url=l["url"], port=l.get("port")) for l in r.pop("app_links", []) or [])
    repos = tuple(ProjectRepo.from_any(x) for x in r.pop("repos", []) or [])
    return RoomConfig(
        name=r["name"], repo=r.get("repo") or "", git_url=r.get("git_url"), branch=r.get("branch"), model=r.get("model"), harness=r.get("harness"),
        language=r.get("language"), app_links=links, linked=tuple(r.get("linked", []) or []), repos=repos,
    )


def load_config(path: str | Path) -> Config:
    data = yaml.safe_load(Path(path).read_text()) or {}
    rooms = [room_from_dict(r) for r in data.get("rooms", [])]
    names = [r.name for r in rooms]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate room names in {path}")
    return Config(rooms=tuple(rooms))
