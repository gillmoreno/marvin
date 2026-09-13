"""Appliance updates: compare this install to GitHub and apply `deploy/edge/update.sh`.

The worker image is a snapshot. Settings shows the commits on `MARVIN_GIT_REF` that are not in
`MARVIN_GIT_SHA`, and an admin can pull + rebuild without SSH. The checkout must be mounted at the
same host path (`MARVIN_INSTALL_DIR`) so compose bind mounts still resolve. Docs: updates.md.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import httpx

log = logging.getLogger("marvin.update")

DEFAULT_REPO = "https://github.com/gillmoreno/marvin.git"
SCRIPT = "deploy/edge/update.sh"
_GITHUB = re.compile(
    r"(?:github\.com[:/])(?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?/?$",
    re.I,
)


def github_slug(url: str) -> tuple[str, str] | None:
    m = _GITHUB.search((url or "").strip())
    return (m["owner"], m["repo"]) if m else None


def _short(sha: str | None) -> str:
    return (sha or "")[:7]


def _subject(message: str) -> str:
    return (message or "").strip().split("\n", 1)[0][:200]


class Install:
    def __init__(
        self,
        root: Path | None,
        sha: str | None,
        ref: str,
        repo_url: str,
        state_path: Path,
        *,
        fetch: Callable[[str], Any] | None = None,
        runner: Callable[[list[str], Path], Any] | None = None,
    ) -> None:
        self.root = root
        self.sha = sha or (self._git_head() if root else None)
        self.ref = ref
        self.repo_url = repo_url
        self.state_path = state_path
        self._fetch = fetch
        self._runner = runner
        self._task: asyncio.Task | None = None

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Install:
        env = environ if environ is not None else os.environ
        raw = (env.get("MARVIN_INSTALL_DIR") or "").strip()
        root = Path(raw) if raw else None
        state_dir = Path(env.get("MARVIN_STATE_DIR") or "/work/state")
        return cls(
            root,
            (env.get("MARVIN_GIT_SHA") or "").strip() or None,
            (env.get("MARVIN_GIT_REF") or "main").strip() or "main",
            (env.get("MARVIN_GIT_REPO") or DEFAULT_REPO).strip() or DEFAULT_REPO,
            state_dir / "update.json",
        )

    def _git_head(self) -> str | None:
        if not self.root or not (self.root / ".git").exists():
            return None
        try:
            head = (self.root / ".git" / "HEAD").read_text().strip()
            if head.startswith("ref:"):
                ref = self.root / ".git" / head.split(" ", 1)[1].strip()
                return ref.read_text().strip() if ref.is_file() else None
            return head or None
        except OSError:
            return None

    def can_apply(self) -> bool:
        return bool(
            self.root
            and (self.root / ".git").exists()
            and (self.root / SCRIPT).is_file()
            and (self.root / "docker-compose.edge.yml").is_file()
        )

    def _state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, **kw: Any) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        cur = self._state()
        cur.update(kw)
        self.state_path.write_text(json.dumps(cur))

    async def github_json(self, path: str) -> dict[str, Any] | None:
        if self._fetch:
            return await _maybe_await(self._fetch(path))
        slug = github_slug(self.repo_url)
        if not slug:
            return None
        url = f"https://api.github.com/repos/{slug[0]}/{slug[1]}{path}"
        try:
            async with httpx.AsyncClient(timeout=12.0) as c:
                r = await c.get(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "marvin-update"})
            if r.status_code != 200:
                log.info("github %s -> %s", path, r.status_code)
                return None
            return r.json()
        except Exception:
            log.exception("github %s", path)
            return None

    async def describe(self) -> dict[str, Any]:
        st = self._state()
        applying = bool(st.get("applying"))
        latest = None
        latest_message = None
        commits: list[dict[str, str]] = []
        tip = await self.github_json(f"/commits/{self.ref}")
        if tip and isinstance(tip.get("sha"), str):
            latest = tip["sha"]
            latest_message = _subject((tip.get("commit") or {}).get("message") or "")
        if self.sha and latest and not latest.startswith(self.sha) and not self.sha.startswith(latest):
            cmp = await self.github_json(f"/compare/{self.sha}...{latest}")
            for c in reversed((cmp or {}).get("commits") or []):
                commits.append({"sha": _short(c.get("sha")), "message": _subject((c.get("commit") or {}).get("message") or "")})
                if len(commits) >= 15:
                    break
        elif latest and not self.sha:
            commits = [{"sha": _short(latest), "message": latest_message or ""}]
        behind = bool(latest and self.sha and not latest.startswith(self.sha) and not self.sha.startswith(latest))
        if latest and not self.sha:
            behind = True
        return {
            "sha": self.sha,
            "short": _short(self.sha) or None,
            "ref": self.ref,
            "repo": self.repo_url,
            "latest": latest,
            "latest_short": _short(latest) or None,
            "latest_message": latest_message,
            "behind": behind,
            "commits": commits,
            "can_apply": self.can_apply(),
            "applying": applying,
            "last_error": st.get("error"),
            "finished_at": st.get("finished_at"),
        }

    def start(self) -> dict[str, Any]:
        if not self.can_apply():
            raise RuntimeError("this process is not an appliance checkout (MARVIN_INSTALL_DIR)")
        if self._state().get("applying"):
            raise RuntimeError("an update is already running")
        self._write_state(applying=True, error=None, started_at=time.time(), finished_at=None)
        self._task = asyncio.get_running_loop().create_task(self._run(), name="marvin-update")
        return {"started": True}

    async def _run(self) -> None:
        assert self.root is not None
        script = self.root / SCRIPT
        log.info("update: running %s", script)
        try:
            if self._runner:
                await _maybe_await(self._runner(["/bin/bash", str(script)], self.root))
            else:
                proc = await asyncio.create_subprocess_exec(
                    "/bin/bash", str(script), cwd=str(self.root),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                )
                out, _ = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError((out or b"").decode(errors="replace")[-2000:] or f"exit {proc.returncode}")
            self._write_state(applying=False, error=None, finished_at=time.time())
            log.info("update: finished")
        except Exception as e:
            log.exception("update failed")
            self._write_state(applying=False, error=str(e)[:2000], finished_at=time.time())


async def _maybe_await(val: Any) -> Any:
    if asyncio.iscoroutine(val):
        return await val
    return val
