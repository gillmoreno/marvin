"""Per-room Docker sandbox: the coding agent runs inside a container, not on the worker's host.

One long-lived container per room (`marvin-sbx-<room>`, `sleep infinity`); every harness process is a `docker exec`
into it. The repo, the linked repos and the room's HOME are mounted at the *same absolute paths* as on the worker,
so nothing in Marvin translates paths: tool events, the Changes pane (git on the worker side) and the agent's own
view of the tree all agree. Credentials reach the agent only as environment variables on each exec (`forward_env`),
never on disk in the container.

What the sandbox contains: the agent's shell, file edits, test runs, package installs. What it does not contain:
the worker itself, LiveKit, the STT, the admin API. The blast radius of a bad tool call is the container plus what
is mounted into it (the repo). See docs_and_changelog/sandbox.md.

MARVIN_SANDBOX=off|docker         off (default): harnesses run as worker subprocesses, as before
MARVIN_SANDBOX_IMAGE              image with the harness CLIs (deploy/sandbox/Dockerfile; `make sandbox-image`)
MARVIN_SANDBOX_NETWORK            docker network for the container: host (default; app ports show up as before),
                                  bridge, none, or container:<name> (share the worker container's namespace)
MARVIN_SANDBOX_PORTS              with bridge: ports to publish on 127.0.0.1, e.g. "3000-3010,5173,8000-8010"
MARVIN_SANDBOX_MOUNTS             extra "src:dst[:ro]" mounts, comma-separated (compose: "marvin_work:/work")
MARVIN_SANDBOX_ENV                extra env var names to forward into every exec (credentials the agent needs)
MARVIN_SANDBOX_USER               uid:gid inside the container (default: the worker's on Linux, root elsewhere)
MARVIN_SANDBOX_MEMORY / _CPUS / _PIDS   resource limits (4g, 2, 2048)
MARVIN_SANDBOX_DOCKER_SOCKET=1    hand the agent the host's Docker daemon (root-equivalent on that host; off by default)
MARVIN_SANDBOX_DOCKER             docker binary (default: docker)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

from marvin.config import RoomConfig

log = logging.getLogger("marvin.sandbox")

# Environment the agent needs and nothing else: provider credentials, GitHub, proxies, git identity, SDK plumbing.
DEFAULT_FORWARD_ENV: tuple[str, ...] = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_REGION",
    "CLOUD_ML_REGION", "ANTHROPIC_VERTEX_PROJECT_ID",
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "CURSOR_API_KEY",
    "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
    "MARVIN_GIT_NAME", "MARVIN_GIT_EMAIL", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
    "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING", "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "GIT_CONFIG_GLOBAL", "GH_CONFIG_DIR", "MARVIN_TURN_FILE", "MARVIN_STATE_DIR",
    "GROK_HOME",  # Grok subscription session (~/.grok/auth.json) written by Settings → Coding agents
    "TERM", "LANG", "LC_ALL",
)
_NAME_RE = re.compile(r"[^a-z0-9-]+")


@dataclass(frozen=True)
class Mount:
    src: str
    dst: str
    ro: bool = False

    def arg(self) -> str:
        return f"{self.src}:{self.dst}" + (":ro" if self.ro else "")

    def covers(self, path: str) -> bool:
        """Whether `path` is already visible in the container at the same location through this mount. Extra mounts
        (MARVIN_SANDBOX_MOUNTS) are by definition filesystems the worker also sees at `dst` (a shared named volume),
        so anything under `dst` needs no bind mount of its own."""
        p, d = Path(path), Path(self.dst)
        return p == d or d in p.parents

    @classmethod
    def parse(cls, spec: str) -> "Mount":
        parts = spec.split(":")
        if len(parts) == 2:
            return cls(parts[0], parts[1])
        if len(parts) == 3 and parts[2] in ("ro", "rw"):
            return cls(parts[0], parts[1], ro=parts[2] == "ro")
        raise ValueError(f"bad mount {spec!r}: expected src:dst or src:dst:ro")


@dataclass(frozen=True)
class SandboxConfig:
    mode: str = "off"  # "off" | "docker"
    image: str = "marvin-sandbox:local"
    docker: str = "docker"
    network: str = "host"
    ports: tuple[str, ...] = ()  # "3000-3010", "5173": published on 127.0.0.1 when network is bridge
    mounts: tuple[Mount, ...] = ()
    forward_env: tuple[str, ...] = DEFAULT_FORWARD_ENV
    user: str | None = None
    memory: str = "4g"
    cpus: str = "2"
    pids: int = 2048
    docker_socket: bool = False
    extra_run_args: tuple[str, ...] = field(default_factory=tuple)

    @property
    def enabled(self) -> bool:
        return self.mode == "docker"

    @classmethod
    def from_env(cls, env=os.environ) -> "SandboxConfig":
        mode = (env.get("MARVIN_SANDBOX") or "off").strip().lower()
        if mode not in ("off", "docker"):
            raise ValueError(f"MARVIN_SANDBOX={mode!r}: expected off or docker")
        csv = lambda k: tuple(x.strip() for x in env.get(k, "").split(",") if x.strip())  # noqa: E731
        user = env.get("MARVIN_SANDBOX_USER", "").strip() or None
        if user is None and sys.platform.startswith("linux") and hasattr(os, "getuid"):
            user = f"{os.getuid()}:{os.getgid()}"  # files the agent writes into the bind-mounted repo stay ours
        return cls(
            mode=mode,
            image=env.get("MARVIN_SANDBOX_IMAGE", "").strip() or cls.image,
            docker=env.get("MARVIN_SANDBOX_DOCKER", "").strip() or cls.docker,
            network=env.get("MARVIN_SANDBOX_NETWORK", "").strip() or cls.network,
            ports=csv("MARVIN_SANDBOX_PORTS"),
            mounts=tuple(Mount.parse(m) for m in csv("MARVIN_SANDBOX_MOUNTS")),
            forward_env=DEFAULT_FORWARD_ENV + csv("MARVIN_SANDBOX_ENV"),
            user=user,
            memory=env.get("MARVIN_SANDBOX_MEMORY", "").strip() or cls.memory,
            cpus=env.get("MARVIN_SANDBOX_CPUS", "").strip() or cls.cpus,
            pids=int(env.get("MARVIN_SANDBOX_PIDS", "") or cls.pids),
            docker_socket=env.get("MARVIN_SANDBOX_DOCKER_SOCKET", "").strip().lower() in ("1", "true", "yes"),
            extra_run_args=tuple(shlex.split(env.get("MARVIN_SANDBOX_RUN_ARGS", ""))),
        )


class SandboxError(RuntimeError):
    pass


class Sandbox:
    """Manages the containers; `for_room` hands a harness the bits it needs (exec prefix, CLI wrapper)."""

    def __init__(self, cfg: SandboxConfig, *, state_dir: str | None, notes_path: Path | None = None) -> None:
        self.cfg = cfg
        if cfg.enabled and not state_dir:
            raise SandboxError("MARVIN_SANDBOX=docker needs --state-dir / MARVIN_STATE_DIR (per-room HOME and CLI wrappers live there)")
        self.state_dir = Path(state_dir) if state_dir else None
        self.notes_path = notes_path if notes_path is not None else Path.home() / ".claude" / "CLAUDE.md"

    # -- naming ------------------------------------------------------------------
    @staticmethod
    def container_name(room: str) -> str:
        return "marvin-sbx-" + _NAME_RE.sub("-", room.lower()).strip("-")[:50]

    def room_dir(self, room: str) -> Path:
        assert self.state_dir is not None
        return self.state_dir / "sandbox" / room

    def home_dir(self, room: str) -> Path:
        return self.room_dir(room) / "home"

    # -- what a room mounts --------------------------------------------------------
    def mounts_for(self, cfg: RoomConfig) -> list[Mount]:
        """Extra mounts first, then whatever they do not already cover: repo, linked repos, HOME, machine notes (ro)."""
        out = list(self.cfg.mounts)

        def add(m: Mount) -> None:
            if any(x.covers(m.dst) for x in out) or any(x.dst == m.dst for x in out):
                return
            out.append(m)

        add(Mount(cfg.repo, cfg.repo))
        for p in cfg.linked:
            add(Mount(p, p))
        home = str(self.home_dir(cfg.name))
        add(Mount(home, home))
        if self.notes_path.exists() and not self.notes_covered():
            # Nested on purpose: HOME is the room's own directory, the notes file is the worker's, mounted read-only over it.
            out.append(Mount(str(self.notes_path), f"{home}/.claude/CLAUDE.md", ro=True))
        if self.cfg.docker_socket:
            add(Mount("/var/run/docker.sock", "/var/run/docker.sock"))
        return out

    def notes_covered(self) -> bool:
        """The machine notes are already visible in the container (under a shared volume): link instead of mount."""
        return any(m.covers(str(self.notes_path)) for m in self.cfg.mounts)

    def link_notes(self, room: str) -> None:
        """$HOME/.claude/CLAUDE.md in the sandbox -> the worker's notes file, when both are on a shared volume."""
        target = self.home_dir(room) / ".claude" / "CLAUDE.md"
        if not self.notes_covered() or target.exists() or target.is_symlink():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(self.notes_path)

    def run_argv(self, cfg: RoomConfig) -> list[str]:
        name = self.container_name(cfg.name)
        home = str(self.home_dir(cfg.name))
        mounts = self.mounts_for(cfg)
        argv = [
            self.cfg.docker, "run", "-d", "--name", name, "--init",
            "--label", f"marvin.room={cfg.name}", "--label", f"marvin.sig={self.signature(cfg)}",
            "--network", self.cfg.network,
            "--memory", self.cfg.memory, "--cpus", self.cfg.cpus, "--pids-limit", str(self.cfg.pids),
            "--security-opt", "no-new-privileges",
            "-e", f"HOME={home}", "-e", f"MARVIN_ROOM={cfg.name}", "-e", "MARVIN_SANDBOX=1",
            "-w", cfg.repo,
        ]
        if self.cfg.user:
            argv += ["--user", self.cfg.user]
        if self.cfg.network == "bridge":
            for spec in self.cfg.ports:
                argv += ["-p", f"127.0.0.1:{spec}:{spec}"]
        for m in mounts:
            argv += ["-v", m.arg()]
        argv += list(self.cfg.extra_run_args)
        argv += [self.cfg.image, "sleep", "infinity"]
        return argv

    def signature(self, cfg: RoomConfig) -> str:
        """Changes to anything that is fixed at `docker run` time recreate the container."""
        parts = [self.cfg.image, self.cfg.network, self.cfg.user or "", self.cfg.memory, self.cfg.cpus, str(self.cfg.pids),
                 ",".join(self.cfg.ports), " ".join(self.cfg.extra_run_args), *(m.arg() for m in self.mounts_for(cfg))]
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]

    # -- what a harness gets ---------------------------------------------------------
    def for_room(self, cfg: RoomConfig) -> "RoomSandbox":
        return RoomSandbox(self, cfg)

    def exec_argv(self, room: str, cmd: list[str], *, cwd: str, env: dict[str, str] | None = None) -> list[str]:
        """`docker exec` prefix for one harness process. Forwarded variables take their value from the exec'ing
        process's environment (so an adapter's `env=` merge still applies); `env` adds fixed values."""
        argv = [self.cfg.docker, "exec", "-i", "-w", cwd, "-e", f"HOME={self.home_dir(room)}"]
        for k, v in (env or {}).items():
            argv += ["-e", f"{k}={v}"]
        for name in self.cfg.forward_env:
            if name in os.environ and name not in (env or {}):
                argv += ["-e", name]
        return argv + [self.container_name(room), *cmd]

    def cli_wrapper(self, room: str, binary: str) -> Path:
        """An executable that runs `binary` inside the room's container, for SDKs that spawn a CLI by path
        (Claude Agent SDK `cli_path`). Runs in the caller's cwd (mounted at the same path) and forwards the env."""
        path = self.room_dir(room) / "bin" / binary
        path.parent.mkdir(parents=True, exist_ok=True)
        fwd = "\n".join(f'[ -n "${{{n}+x}}" ] && set -- -e {n} "$@"' for n in self.cfg.forward_env)
        script = f"""#!/bin/sh
# generated by marvin.sandbox: `{binary}` runs inside {self.container_name(room)}
set -- {shlex.quote(self.container_name(room))} {shlex.quote(binary)} "$@"
{fwd}
exec {shlex.quote(self.cfg.docker)} exec -i -w "$PWD" -e HOME={shlex.quote(str(self.home_dir(room)))} "$@"
"""
        if not path.exists() or path.read_text() != script:
            path.write_text(script)
            path.chmod(0o755)
        return path

    # -- lifecycle -----------------------------------------------------------------
    async def check(self) -> None:
        """Fail fast at worker start: daemon reachable, image present (pulled if it names a registry)."""
        if not self.cfg.enabled:
            return
        rc, out = await self._docker("version", "--format", "{{.Server.Version}}")
        if rc != 0:
            raise SandboxError(f"MARVIN_SANDBOX=docker but the Docker daemon is not reachable ({out.strip()[:200]}). Start Docker, or set MARVIN_SANDBOX=off.")
        log.info("sandbox: docker %s, image %s, network %s%s", out.strip(), self.cfg.image, self.cfg.network,
                 ", agent gets the host Docker socket" if self.cfg.docker_socket else "")
        if self.cfg.docker_socket:
            log.warning("sandbox: MARVIN_SANDBOX_DOCKER_SOCKET=1 hands every room's agent the host Docker daemon (root-equivalent on that host)")
        rc, _ = await self._docker("image", "inspect", self.cfg.image)
        if rc == 0:
            return
        if "/" in self.cfg.image.split(":")[0]:
            log.info("sandbox: pulling %s", self.cfg.image)
            rc, out = await self._docker("pull", self.cfg.image, timeout=900)
            if rc == 0:
                return
            raise SandboxError(f"cannot pull sandbox image {self.cfg.image}: {out.strip()[-300:]}")
        raise SandboxError(f"sandbox image {self.cfg.image!r} not found; build it with `make sandbox-image` or set MARVIN_SANDBOX_IMAGE")

    async def ensure(self, cfg: RoomConfig) -> str:
        """Container for the room exists, matches the current configuration and is running. Returns its name."""
        name = self.container_name(cfg.name)
        home = self.home_dir(cfg.name)
        (home / ".claude").mkdir(parents=True, exist_ok=True)
        self.link_notes(cfg.name)
        want = self.signature(cfg)
        rc, out = await self._docker("inspect", "--format", '{{index .Config.Labels "marvin.sig"}} {{.State.Running}}', name)
        if rc == 0:
            sig, _, running = out.strip().partition(" ")
            if sig == want:
                if running != "true":
                    rc, out = await self._docker("start", name)
                    if rc != 0:
                        raise SandboxError(f"cannot start {name}: {out.strip()[-300:]}")
                    log.info("sandbox %s: started", name)
                if not await self._network_stale(name):
                    return name
                log.info("sandbox %s: shared network namespace is stale, recreating", name)
                await self._docker("rm", "-f", name)
            log.info("sandbox %s: configuration changed, recreating", name)
            await self._docker("rm", "-f", name)
        argv = self.run_argv(cfg)
        log.info("sandbox %s: creating (%s)", name, " ".join(shlex.quote(a) for a in argv[2:]))
        rc, out = await self._docker(*argv[1:], timeout=300)
        if rc != 0:
            raise SandboxError(f"cannot create {name}: {out.strip()[-400:]}")
        rc, out = await self._docker(*self.exec_argv(cfg.name, ["marvin-sandbox-init"], cwd=cfg.repo)[1:], timeout=120)
        if rc != 0:
            log.warning("sandbox %s: marvin-sandbox-init failed (%s); git identity/credentials inside may be unset", name, out.strip()[-200:])
        return name

    async def _network_stale(self, name: str) -> bool:
        """`docker restart` of a `container:<peer>` target keeps the sandbox running in the old netns.
        DNS and model APIs then fail inside the room (`Temporary failure in name resolution`)."""
        if not self.cfg.network.startswith("container:"):
            return False
        peer = self.cfg.network.split(":", 1)[1]
        rc1, a = await self._docker("exec", name, "readlink", "/proc/1/ns/net")
        rc2, b = await self._docker("exec", peer, "readlink", "/proc/1/ns/net")
        if rc1 != 0 or rc2 != 0:
            return False
        return a.strip() != b.strip()

    async def remove(self, room: str) -> None:
        name = self.container_name(room)
        rc, out = await self._docker("rm", "-f", name)
        if rc == 0:
            log.info("sandbox %s: removed", name)

    async def listening_ports(self, room: str) -> set[int] | None:
        """TCP listeners inside the room's container (bridge mode; host mode is seen by the worker's own scanner)."""
        if self.cfg.network == "host":
            return None
        argv = self.exec_argv(room, ["cat", "/proc/net/tcp", "/proc/net/tcp6"], cwd="/")
        rc, out = await self._docker(*argv[1:])
        if rc != 0:
            return set()
        ports: set[int] = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) > 3 and parts[3] == "0A":
                ports.add(int(parts[1].rsplit(":", 1)[1], 16))
        return ports

    async def _docker(self, *args: str, timeout: float = 60) -> tuple[int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(self.cfg.docker, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, stdin=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
            return proc.returncode or 0, out.decode(errors="replace")
        except FileNotFoundError:
            return 127, f"{self.cfg.docker}: not found"
        except asyncio.TimeoutError:
            return 124, f"docker {' '.join(args[:2])}: timed out after {timeout}s"


@dataclass(frozen=True)
class RoomSandbox:
    """What `create_harness` needs for one room."""

    sandbox: Sandbox
    cfg: RoomConfig

    def wrap(self, cmd: list[str], *, env: dict[str, str] | None = None) -> list[str]:
        return self.sandbox.exec_argv(self.cfg.name, cmd, cwd=self.cfg.repo, env=env)

    def cli_path(self, binary: str) -> str:
        return str(self.sandbox.cli_wrapper(self.cfg.name, binary))

    @property
    def container(self) -> str:
        return self.sandbox.container_name(self.cfg.name)
