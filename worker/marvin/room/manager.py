"""Owns every RoomSession in this worker. Rooms come from rooms.yaml (static) or are created at runtime
through the admin API and persisted in <state_dir>/rooms.json so they survive restarts."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from marvin.adapters import registry
from marvin.config import Config, ProjectRepo, RoomConfig, room_from_dict
from marvin.ports import OWN_PORTS, AppsRouting, listening_ports

from .session import RoomSession

log = logging.getLogger("marvin.manager")
ROOM_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class RoomManager:
    def __init__(self, config: Config, *, repos_dir: str, state_dir: str | None, session_kwargs: dict[str, Any], routing: AppsRouting | None = None) -> None:
        self.static = {r.name: r for r in config.rooms}
        self.repos_dir = Path(repos_dir)
        self.state_file = Path(state_dir) / "rooms.json" if state_dir else None
        self.session_kwargs = session_kwargs
        sbx = session_kwargs.get("sandbox")
        self.sandbox = sbx if sbx is not None and sbx.cfg.enabled else None
        self.routing = routing or AppsRouting()
        self.overrides: dict[str, dict] = {}  # per-room model/linked changes made from the UI (also for static rooms)
        self.dynamic: dict[str, RoomConfig] = self._load_dynamic()
        self.sessions: dict[str, RoomSession] = {}
        self._ports: set[int] = set()
        self._watcher: asyncio.Task | None = None

    # -- persistence -------------------------------------------------------------
    def _load_dynamic(self) -> dict[str, RoomConfig]:
        if not self.state_file or not self.state_file.exists():
            return {}
        try:
            data = json.loads(self.state_file.read_text())
        except Exception:
            log.exception("could not read %s", self.state_file)
            return {}
        out = {}
        for r in data.get("rooms", []):
            try:
                out[r["name"]] = room_from_dict(r)
            except (KeyError, ValueError) as e:
                log.error("skipping room record %r: %s", r.get("name"), e)
        self.overrides = data.get("overrides", {})
        return out

    def _save_dynamic(self) -> None:
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        rooms = []
        for r in self.dynamic.values():
            d = asdict(r)
            d["app_links"] = [asdict(l) for l in r.app_links]
            d["repos"] = [asdict(x) for x in r.repos]
            rooms.append(d)
        self.state_file.write_text(json.dumps({"rooms": rooms, "overrides": self.overrides}, indent=2))

    # -- queries -----------------------------------------------------------------
    def configs(self) -> dict[str, RoomConfig]:
        merged = {**self.dynamic, **self.static}  # static wins on a name clash
        for name, ov in self.overrides.items():
            if name in merged:
                merged[name] = self._apply_override(merged[name], ov)
        return merged

    @staticmethod
    def _apply_override(cfg: RoomConfig, ov: dict) -> RoomConfig:
        """UI changes on top of a room: model, harness, and the project's repos. An old `linked` override (paths only)
        is read as "primary + those", keeping roles the config already knows."""
        kw = {k: v for k, v in ov.items() if k in ("model", "harness")}
        if "repos" in ov:
            kw["repos"] = tuple(ProjectRepo.from_any(r) for r in ov["repos"])
        elif "linked" in ov:
            known = {r.path: r for r in cfg.repos}
            kw["repos"] = (cfg.repos[0], *(known.get(p, ProjectRepo(path=p)) for p in ov["linked"] if p != cfg.repo))
        return replace(cfg, **kw)

    def describe(self) -> list[dict]:
        out = []
        for name, cfg in sorted(self.configs().items()):
            s = self.sessions.get(name)
            h = getattr(s, "harness", None) if s else None
            out.append({
                "name": name, "repo": cfg.repo, "git_url": cfg.git_url, "branch": cfg.branch,
                "static": name in self.static, "live": s is not None,
                "model": (getattr(h, "model", None) or cfg.model), "model_pinned": cfg.model, "linked": list(cfg.linked),
                "repos": [{**r.to_wire(), "exists": Path(r.path).is_dir(), "git": (Path(r.path) / ".git").exists()} for r in cfg.repos],
                "harness": (getattr(h, "name", None) if h is not None else None) or cfg.harness or registry.default_id(), "harness_pinned": cfg.harness,
                "app_links": (s.conductor.app_links if s and s.conductor else [l.to_wire() for l in cfg.app_links]),
                "sandbox": ({"image": self.sandbox.cfg.image, "container": self.sandbox.container_name(name), "network": self.sandbox.cfg.network} if self.sandbox else None),
            })
        return out

    def live_models(self, room: str) -> dict | None:
        """Models the room's running agent reports about itself (ACP harnesses), or None to fall back to the profile."""
        s = self.sessions.get(room)
        h = getattr(s, "harness", None) if s else None
        models = list(getattr(h, "available_models", None) or [])
        if h is None or not models:
            return None
        return {"harness": h.name, "models": models, "default": getattr(h, "model", None) or "", "live": True}

    def repos(self) -> list[dict]:
        out = []
        if self.repos_dir.exists():
            for d in sorted(p for p in self.repos_dir.iterdir() if p.is_dir()):
                out.append({"name": d.name, "path": str(d), **_git_info(d), "rooms": [n for n, c in self.configs().items() if Path(c.repo) == d]})
        return out

    # -- lifecycle -----------------------------------------------------------------
    async def start_all(self) -> None:
        results = await asyncio.gather(*(self.start_room(name) for name in self.configs()), return_exceptions=True)
        for name, r in zip(self.configs(), results):
            if isinstance(r, Exception):
                log.error("room %s failed to start: %s", name, r)
        self._watcher = asyncio.create_task(self._watch_ports())

    async def start_room(self, name: str) -> RoomSession:
        if name in self.sessions:
            return self.sessions[name]
        cfg = self.configs()[name]
        session = RoomSession(cfg, **self.session_kwargs)
        await session.start()
        self.sessions[name] = session
        await self._push_links(session)
        return session

    async def stop_room(self, name: str) -> None:
        if s := self.sessions.pop(name, None):
            await s.close()

    async def close(self) -> None:
        if self._watcher:
            self._watcher.cancel()
        await asyncio.gather(*(s.close() for s in self.sessions.values()), return_exceptions=True)

    # -- admin operations ----------------------------------------------------------
    def _resolve_repo(self, d: dict, *, fallback_name: str) -> ProjectRepo:
        """A repo as the UI sends it ({path|git_url, role, branch}) -> a ProjectRepo with an absolute path under repos_dir."""
        path = str(d.get("path") or "").strip()
        git_url = str(d.get("git_url") or "").strip() or None
        if path and not path.startswith("/"):
            path = str(self.repos_dir / path)
        if not path:
            path = str(self.repos_dir / (_repo_name(git_url) if git_url else fallback_name))
        role = str(d.get("role") or "").strip().lower()[:24]
        return ProjectRepo(path=path, role=role, git_url=git_url, branch=(str(d.get("branch") or "").strip() or None))

    async def create_room(
        self, name: str, *, repo: str | None = None, git_url: str | None = None, branch: str | None = None, language: str | None = None,
        linked: list[str] | None = None, repos: list[dict] | None = None, clone_token: str | None = None,
    ) -> dict:
        """Create a project room. `repos` is the project form ([{path|git_url, role, branch}, ...], first = working
        directory); `repo`/`git_url`/`branch`/`linked` is the single-repo form. Repos with a git_url whose directory is
        missing are cloned first, with `clone_token` (the requester's GitHub token) when given."""
        if not ROOM_NAME_RE.match(name):
            raise ValueError("room name: lowercase letters, digits and dashes, max 40 chars")
        if name in self.configs():
            raise ValueError(f"room {name!r} already exists")
        if repos:
            project = tuple(self._resolve_repo(r, fallback_name=name) for r in repos)
        else:
            project = (self._resolve_repo({"path": repo, "git_url": git_url, "branch": branch}, fallback_name=name), *(self._resolve_repo({"path": p}, fallback_name=name) for p in (linked or [])))
        cfg = RoomConfig(name=name, language=language, repos=project)
        log.info("create room %s: %s", name, ", ".join(f"{r.name}{f' ({r.role})' if r.role else ''}" for r in cfg.repos))
        for r in cfg.repos:
            await self._materialize(r, clone_token)
        self.dynamic[name] = cfg
        self._save_dynamic()
        try:
            await self.start_room(name)
        except Exception:
            self.dynamic.pop(name, None)
            self._save_dynamic()
            raise
        return self.describe_one(name)

    async def update_room(
        self, name: str, *, model: str | None = None, linked: list[str] | None = None, clear_model: bool = False, harness: str | None = None, clear_harness: bool = False,
        repos: list[dict] | None = None, clone_token: str | None = None,
    ) -> dict:
        """Change a room's model, harness and/or project repos; the harness is swapped, the conversation resumes
        (except across harnesses: a different agent cannot pick up another agent's session)."""
        if name not in self.configs():
            raise KeyError(name)
        ov = dict(self.overrides.get(name, {}))
        if repos is not None:
            if not repos:
                raise ValueError("a project needs at least one repo")
            project = [self._resolve_repo(r, fallback_name=name) for r in repos]
            for r in project:
                await self._materialize(r, clone_token)
            ov.pop("linked", None)
            ov["repos"] = [asdict(r) for r in project]
        if clear_model:
            ov.pop("model", None)
        elif model is not None:
            ov["model"] = model
        if clear_harness:
            ov.pop("harness", None)
        elif harness is not None:
            if harness not in registry.ids():
                raise ValueError(f"unknown harness {harness!r}; known: {', '.join(registry.ids())}")
            ov["harness"] = harness
        if linked is not None:
            paths = []
            for p in linked:
                p = p if p.startswith("/") else str(self.repos_dir / p)
                if not Path(p).is_dir():
                    raise ValueError(f"{p} is not a directory on this machine")
                paths.append(p)
            cur = self.configs()[name]
            known = {r.path: r for r in cur.repos}
            ov.pop("linked", None)
            ov["repos"] = [asdict(cur.repos[0]), *(asdict(known.get(p, ProjectRepo(path=p))) for p in paths if p != cur.repo)]
        self.overrides[name] = ov
        self._save_dynamic()
        cfg = self.configs()[name]
        if s := self.sessions.get(name):
            await s.reconfigure(cfg)
        return self.describe_one(name)

    async def delete_room(self, name: str) -> None:
        if name in self.static:
            raise ValueError(f"room {name!r} comes from rooms.yaml; remove it there")
        if name not in self.dynamic:
            raise KeyError(name)
        await self.stop_room(name)
        self.dynamic.pop(name)
        self._save_dynamic()
        if self.sandbox:
            await self.sandbox.remove(name)

    async def _materialize(self, r: ProjectRepo, token: str | None) -> None:
        """Make sure the repo's directory exists: clone it when it has a git_url, otherwise it must already be there
        (a new project may start from an empty primary folder; the session creates that one)."""
        path = Path(r.path)
        if path.is_dir():
            return
        if r.git_url:
            await self._git_clone(r.git_url, path, r.branch, token)
        elif r.path != str(self.repos_dir / path.name) or r.role:
            raise ValueError(f"{r.path} is not a directory on this machine")

    async def _git_clone(self, url: str, dest: Path, branch: str | None, token: str | None) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone", *(["--branch", branch] if branch else []), _https_github(url) if token else url, str(dest)]
        log.info("clone: %s", " ".join(cmd))
        env = dict(os.environ)
        if token:
            # The token goes in through the environment and a one-off credential helper: never on the command line.
            env.update({
                "MARVIN_CLONE_TOKEN": token, "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "credential.helper",
                "GIT_CONFIG_VALUE_0": '!f() { echo username=x-access-token; echo "password=$MARVIN_CLONE_TOKEN"; }; f',
            })
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env)
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            msg = out.decode(errors="replace")[-800:]
            raise RuntimeError(msg.replace(token, "***") if token else msg)

    async def clone_repo(self, url: str, name: str | None = None, branch: str | None = None, clone_token: str | None = None) -> dict:
        name = name or _repo_name(url)
        if not ROOM_NAME_RE.match(name.lower()):
            raise ValueError("repo folder name: letters, digits and dashes")
        dest = self.repos_dir / name
        if dest.exists():
            raise ValueError(f"{dest} already exists")
        await self._git_clone(url, dest, branch, clone_token)
        return {"name": name, "path": str(dest), **_git_info(dest)}

    def describe_one(self, name: str) -> dict:
        return next(r for r in self.describe() if r["name"] == name)

    # -- app links: static config + whatever is listening on this machine -----------
    def ports(self) -> list[dict]:
        return [{"port": p, **self.routing.link(p)} for p in sorted(self._ports)]

    async def _push_links(self, session: RoomSession) -> None:
        if not session.conductor:
            return
        links = [l.to_wire() for l in session.cfg.app_links] + [self.routing.link(p) for p in sorted(self._ports)]
        await session.conductor.set_app_links(links)

    async def _scan_ports(self) -> set[int]:
        """Listeners in the worker's network namespace, plus those inside bridge-mode sandboxes (host-mode sandboxes
        already show up in the former)."""
        now = listening_ports()
        if self.sandbox:
            for name in list(self.sessions):
                inside = await self.sandbox.listening_ports(name)
                if inside:
                    now |= {p for p in inside if p not in OWN_PORTS and p < 30000}
        return now

    async def _watch_ports(self, interval: float = 4.0) -> None:
        while True:
            try:
                now = await self._scan_ports()
                if now != self._ports:
                    log.info("listening ports: %s", sorted(now))
                    self._ports = now
                    for s in list(self.sessions.values()):
                        await self._push_links(s)
            except Exception:
                log.exception("port watcher")
            await asyncio.sleep(interval)


def _https_github(url: str) -> str:
    """git@github.com:org/repo.git -> https://github.com/org/repo.git, so a token can authenticate the clone."""
    return "https://github.com/" + url[len("git@github.com:"):] if url.startswith("git@github.com:") else url


def _repo_name(url: str | None) -> str:
    if not url:
        return "repo"
    tail = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return tail[:-4] if tail.endswith(".git") else tail


def _git_info(path: Path) -> dict:
    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            return ""
    if not (path / ".git").exists():
        return {"git": False, "remote": None, "branch": None, "dirty": False}
    return {"git": True, "remote": git("remote", "get-url", "origin") or None, "branch": git("rev-parse", "--abbrev-ref", "HEAD") or None, "dirty": bool(git("status", "--porcelain"))}
