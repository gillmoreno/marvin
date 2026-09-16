"""Appliance updates: compare this install to GitHub and apply `deploy/edge/update.sh`.

The worker image is a snapshot. Settings shows the commits on `MARVIN_GIT_REF` that are not in
`MARVIN_GIT_SHA`. Apply runs in a sibling container (`marvin-update`) so compose can recreate
this worker; the web process keeps serving `update.log` from the state volume. The checkout must
be mounted at the same host path (`MARVIN_INSTALL_DIR`) so compose bind mounts still resolve.
Docs: updates.md.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import httpx

log = logging.getLogger("marvin.update")

DEFAULT_REPO = "https://github.com/gillmoreno/marvin.git"
SCRIPT = "deploy/edge/update.sh"
UPDATER = "marvin-update"
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
        release_fetch: Callable[[], Any] | None = None,
        runner: Callable[[list[str], Path], Any] | None = None,
    ) -> None:
        self.root = root
        self.sha = sha or (self._git_head() if root else None)
        self.ref = ref
        self.repo_url = repo_url
        self.state_path = state_path
        self._fetch = fetch
        self._release_fetch = release_fetch
        self._runner = runner
        self._task: asyncio.Task | None = None
        self._release_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._describe_cache: tuple[float, dict[str, Any]] | None = None

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

    def log_path(self) -> Path:
        return self.state_path.with_name("update.log")

    def progress(self) -> dict[str, Any]:
        """What Settings can show without the worker or GitHub: the file the updater writes."""
        st = self._state()
        text = ""
        p = self.log_path()
        if p.exists():
            try:
                text = "\n".join(p.read_text(errors="replace").splitlines()[-50:])
            except OSError:
                text = ""
        return {
            "applying": bool(st.get("applying")),
            "step": st.get("step"),
            "log": text,
            "last_error": st.get("error"),
            "started_at": st.get("started_at"),
            "finished_at": st.get("finished_at"),
            "sha": st.get("sha") or self.sha,
        }

    def snapshot(self, *, worker_up: bool = False) -> dict[str, Any]:
        """Status the page can render from disk alone (token server uses this when the worker is down)."""
        prog = self.progress()
        applying = bool(prog["applying"])
        sha = prog.get("sha")
        return {
            "sha": sha,
            "short": _short(sha) or None,
            "ref": self.ref,
            "repo": self.repo_url,
            "latest": None,
            "latest_short": None,
            "latest_message": None,
            "behind": False,
            "commits": [],
            "can_apply": self.can_apply() and not applying,
            "applying": applying,
            "step": prog.get("step"),
            "log": prog.get("log") or "",
            "last_error": prog.get("last_error"),
            "started_at": prog.get("started_at"),
            "finished_at": prog.get("finished_at"),
            "worker_up": worker_up,
        }

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

    async def product_updates(self) -> list[dict[str, Any]]:
        """Human-readable notes from the target ref. Cached because Settings checks periodically."""
        if self._release_cache and time.time() - self._release_cache[0] < 300:
            return self._release_cache[1]
        if self._release_fetch:
            raw = await _maybe_await(self._release_fetch())
        elif self._fetch:
            # Tests that stub GitHub commit calls should not unexpectedly reach the network.
            raw = None
        else:
            slug = github_slug(self.repo_url)
            if not slug:
                return []
            url = (
                f"https://raw.githubusercontent.com/{slug[0]}/{slug[1]}/"
                f"{quote(self.ref, safe='')}/docs_and_changelog/product-updates.json"
            )
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.get(url, headers={"User-Agent": "marvin-update"})
                raw = response.json() if response.status_code == 200 else None
            except Exception:
                log.exception("product updates from %s", url)
                raw = None
        releases = raw.get("releases") if isinstance(raw, dict) else None
        out = [release for release in releases[:3] if isinstance(release, dict)] if isinstance(releases, list) else []
        self._release_cache = (time.time(), out)
        return out

    async def describe(self) -> dict[str, Any]:
        out = self.snapshot(worker_up=True)
        # Do not call GitHub while applying: the UI polls every couple of seconds and we already
        # burned the unauthenticated rate limit during the last update.
        if out["applying"]:
            return out
        if self._describe_cache and time.time() - self._describe_cache[0] < 300:
            out.update(self._describe_cache[1])
            return out
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
        remote = {
            "latest": latest,
            "latest_short": _short(latest) or None,
            "latest_message": latest_message,
            "behind": behind,
            "commits": commits,
            "product_updates": await self.product_updates() if behind else [],
        }
        self._describe_cache = (time.time(), remote)
        out.update(remote)
        return out

    def start(self) -> dict[str, Any]:
        if not self.can_apply():
            raise RuntimeError("this process is not an appliance checkout (MARVIN_INSTALL_DIR)")
        if self._state().get("applying"):
            raise RuntimeError("an update is already running")
        try:
            self.log_path().write_text("starting updater\n")
        except OSError:
            pass
        self._write_state(applying=True, error=None, step="starting", started_at=time.time(), finished_at=None)
        if self._runner:
            self._task = asyncio.get_running_loop().create_task(self._run(), name="marvin-update")
            return {"started": True}
        self._launch_detached()
        return {"started": True, "detached": True}

    def _launch_detached(self) -> None:
        """A sibling container runs update.sh. Compose will kill *this* worker; the sibling keeps writing the log."""
        if self.root is None:
            raise RuntimeError("no install dir")
        image = os.environ.get("MARVIN_IMAGE") or "marvin:local"
        sandbox = os.environ.get("MARVIN_SANDBOX_IMAGE") or "marvin-sandbox:local"
        subprocess.run(["docker", "rm", "-f", UPDATER], capture_output=True)
        cmd = [
            "docker", "run", "--rm", "-d", "--name", UPDATER,
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-v", f"{self.root}:{self.root}",
            "-v", "marvin_work:/work",
            "-e", f"MARVIN_GIT_REF={self.ref}",
            "-e", f"MARVIN_INSTALL_DIR={self.root}",
            "-e", "MARVIN_STATE_DIR=/work/state",
            "-e", f"MARVIN_SANDBOX_IMAGE={sandbox}",
            "-w", str(self.root),
            "--entrypoint", "bash",
            image,
            str(self.root / SCRIPT),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "docker run failed").strip()[:2000]
            self._write_state(applying=False, error=err, step="failed", finished_at=time.time())
            raise RuntimeError(err)
        self._write_state(updater=(r.stdout or "").strip(), step="updater running")
        log.info("update: started %s", UPDATER)

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
            self._write_state(applying=False, error=None, step="ready", finished_at=time.time())
            log.info("update: finished")
        except Exception as e:
            log.exception("update failed")
            self._write_state(applying=False, error=str(e)[:2000], step="failed", finished_at=time.time())


async def _maybe_await(val: Any) -> Any:
    if asyncio.iscoroutine(val):
        return await val
    return val
