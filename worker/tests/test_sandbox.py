"""marvin.sandbox against a fake `docker` binary that records every invocation and keeps a tiny container table."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from marvin.adapters import registry
from marvin.config import RoomConfig
from marvin.sandbox import DEFAULT_FORWARD_ENV, Mount, Sandbox, SandboxConfig, SandboxError

FAKE_DOCKER = r'''#!/usr/bin/env python3
"""Fake docker: logs argv to $FAKE_DOCKER_LOG, keeps containers in $FAKE_DOCKER_STATE."""
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_DOCKER_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
state_path = os.environ["FAKE_DOCKER_STATE"]
state = json.load(open(state_path)) if os.path.exists(state_path) else {}
def save(): json.dump(state, open(state_path, "w"))
cmd = args[0] if args else ""
if cmd == "version":
    print("27.0.0")
elif cmd == "image":
    sys.exit(0 if os.environ.get("FAKE_DOCKER_IMAGE_PRESENT", "1") == "1" else 1)
elif cmd == "pull":
    sys.exit(0)
elif cmd == "inspect":
    name = args[-1]
    if name not in state:
        print("Error: No such object: " + name); sys.exit(1)
    print(state[name]["sig"] + " " + ("true" if state[name]["running"] else "false"))
elif cmd == "run":
    name = args[args.index("--name") + 1]
    sig = next(a.split("=", 1)[1] for a in args if a.startswith("marvin.sig="))
    state[name] = {"sig": sig, "running": True, "argv": args}; save(); print("abc123")
elif cmd == "start":
    state[args[-1]]["running"] = True; save()
elif cmd == "rm":
    state.pop(args[-1], None); save()
elif cmd == "exec":
    if "cat" in args:
        print("  sl  local_address rem_address   st\n   0: 00000000:1F90 00000000:0000 0A\n   1: 0100007F:0BB8 00000000:0000 01")
    else:
        print("ok")
else:
    print("fake docker: unknown " + cmd); sys.exit(2)
'''


@pytest.fixture
def fake_docker(tmp_path, monkeypatch):
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    log = tmp_path / "docker.log"
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(tmp_path / "docker-state.json"))

    class Fake:
        path = str(docker)

        @staticmethod
        def calls() -> list[list[str]]:
            return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []

        @staticmethod
        def state() -> dict:
            p = tmp_path / "docker-state.json"
            return json.loads(p.read_text()) if p.exists() else {}

    return Fake


@pytest.fixture
def room(tmp_path) -> RoomConfig:
    repo = tmp_path / "repos" / "app"
    linked = tmp_path / "repos" / "api"
    repo.mkdir(parents=True)
    linked.mkdir()
    return RoomConfig(name="dev", repo=str(repo), linked=(str(linked),))


def make(fake_docker, tmp_path, **kw) -> Sandbox:
    notes = tmp_path / "home" / ".claude" / "CLAUDE.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("# machine\n")
    cfg = SandboxConfig(mode="docker", docker=fake_docker.path, **{"user": None, **kw})
    return Sandbox(cfg, state_dir=str(tmp_path / "state"), notes_path=notes)


# -- configuration -----------------------------------------------------------------
def test_config_from_env_defaults_off():
    cfg = SandboxConfig.from_env({})
    assert cfg.mode == "off" and not cfg.enabled


def test_config_from_env_parses_everything():
    cfg = SandboxConfig.from_env({
        "MARVIN_SANDBOX": "docker", "MARVIN_SANDBOX_IMAGE": "ghcr.io/x/sbx:1", "MARVIN_SANDBOX_NETWORK": "bridge",
        "MARVIN_SANDBOX_PORTS": "3000-3010, 5173", "MARVIN_SANDBOX_MOUNTS": "marvin_work:/work, /cache:/cache:ro",
        "MARVIN_SANDBOX_ENV": "MY_TOKEN", "MARVIN_SANDBOX_USER": "1000:1000", "MARVIN_SANDBOX_MEMORY": "8g", "MARVIN_SANDBOX_PIDS": "512",
        "MARVIN_SANDBOX_DOCKER_SOCKET": "true",
    })
    assert cfg.enabled and cfg.image == "ghcr.io/x/sbx:1" and cfg.network == "bridge"
    assert cfg.ports == ("3000-3010", "5173")
    assert cfg.mounts == (Mount("marvin_work", "/work"), Mount("/cache", "/cache", ro=True))
    assert "MY_TOKEN" in cfg.forward_env and "ANTHROPIC_API_KEY" in cfg.forward_env
    assert cfg.user == "1000:1000" and cfg.memory == "8g" and cfg.pids == 512 and cfg.docker_socket


def test_config_rejects_unknown_mode_and_bad_mount():
    with pytest.raises(ValueError):
        SandboxConfig.from_env({"MARVIN_SANDBOX": "podman"})
    with pytest.raises(ValueError):
        Mount.parse("a:b:c:d")


def test_enabled_sandbox_needs_a_state_dir(fake_docker):
    with pytest.raises(SandboxError):
        Sandbox(SandboxConfig(mode="docker", docker=fake_docker.path), state_dir=None)


# -- what gets mounted ---------------------------------------------------------------
def test_mounts_repo_linked_home_and_notes_at_identical_paths(fake_docker, tmp_path, room):
    sbx = make(fake_docker, tmp_path)
    mounts = sbx.mounts_for(room)
    home = str(sbx.home_dir("dev"))
    assert Mount(room.repo, room.repo) in mounts
    assert Mount(room.linked[0], room.linked[0]) in mounts
    assert Mount(home, home) in mounts
    assert Mount(str(sbx.notes_path), f"{home}/.claude/CLAUDE.md", ro=True) in mounts
    assert not any(m.src == "/var/run/docker.sock" for m in mounts)


def test_shared_volume_covers_paths_under_it(fake_docker, tmp_path):
    """Compose: /work is the same named volume in worker and sandbox, so nothing under it is bind-mounted, and the
    notes become a symlink inside the sandbox HOME instead of a mount."""
    work = tmp_path / "work"
    (work / "repos" / "app").mkdir(parents=True)
    notes = work / "home" / ".claude" / "CLAUDE.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("# notes\n")
    cfg = SandboxConfig(mode="docker", docker=fake_docker.path, user=None, mounts=(Mount("marvin_work", str(work)),))
    sbx = Sandbox(cfg, state_dir=str(work / "state"), notes_path=notes)
    room = RoomConfig(name="dev", repo=str(work / "repos" / "app"))
    mounts = sbx.mounts_for(room)
    assert mounts == [Mount("marvin_work", str(work))]
    sbx.link_notes("dev")
    link = sbx.home_dir("dev") / ".claude" / "CLAUDE.md"
    assert link.is_symlink() and link.resolve() == notes.resolve()


def test_docker_socket_opt_in(fake_docker, tmp_path, room):
    sbx = make(fake_docker, tmp_path, docker_socket=True)
    assert Mount("/var/run/docker.sock", "/var/run/docker.sock") in sbx.mounts_for(room)


# -- docker run -----------------------------------------------------------------------
def test_run_argv_host_network_limits_and_labels(fake_docker, tmp_path, room):
    sbx = make(fake_docker, tmp_path, memory="2g", cpus="1.5", pids=300, user="1000:1000")
    argv = sbx.run_argv(room)
    assert argv[:4] == [fake_docker.path, "run", "-d", "--name"] and argv[4] == "marvin-sbx-dev"
    for flag, val in (("--network", "host"), ("--memory", "2g"), ("--cpus", "1.5"), ("--pids-limit", "300"), ("--user", "1000:1000"), ("-w", room.repo)):
        assert argv[argv.index(flag) + 1] == val
    assert "--security-opt" in argv and "--init" in argv and "-p" not in argv
    assert "marvin.room=dev" in argv and any(a.startswith("marvin.sig=") for a in argv)
    assert argv[-3:] == ["marvin-sandbox:local", "sleep", "infinity"]
    assert f"HOME={sbx.home_dir('dev')}" in argv


def test_run_argv_bridge_publishes_ports_on_loopback(fake_docker, tmp_path, room):
    sbx = make(fake_docker, tmp_path, network="bridge", ports=("3000-3010", "5173"))
    argv = sbx.run_argv(room)
    ps = [argv[i + 1] for i, a in enumerate(argv) if a == "-p"]
    assert ps == ["127.0.0.1:3000-3010:3000-3010", "127.0.0.1:5173:5173"]


def test_container_name_is_safe():
    assert Sandbox.container_name("My Room/1") == "marvin-sbx-my-room-1"


# -- lifecycle ------------------------------------------------------------------------
async def test_ensure_creates_then_reuses_then_recreates_on_change(fake_docker, tmp_path, room):
    sbx = make(fake_docker, tmp_path)
    name = await sbx.ensure(room)
    assert name == "marvin-sbx-dev"
    kinds = [c[0] for c in fake_docker.calls()]
    assert kinds == ["inspect", "run", "exec"]  # exec = marvin-sandbox-init
    assert fake_docker.calls()[2][-1] == "marvin-sandbox-init"
    assert (sbx.home_dir("dev") / ".claude").is_dir()

    await sbx.ensure(room)  # same config: only an inspect
    assert [c[0] for c in fake_docker.calls()][3:] == ["inspect"]

    more = tmp_path / "repos" / "worker"
    more.mkdir()
    changed = RoomConfig(name="dev", repo=room.repo, linked=room.linked + (str(more),))
    await sbx.ensure(changed)  # linked repos changed -> new mounts -> recreate
    assert [c[0] for c in fake_docker.calls()][4:] == ["inspect", "rm", "run", "exec"]
    assert f"{more}:{more}" in fake_docker.state()["marvin-sbx-dev"]["argv"]


async def test_ensure_starts_a_stopped_container(fake_docker, tmp_path, room):
    sbx = make(fake_docker, tmp_path)
    await sbx.ensure(room)
    state = fake_docker.state()
    state["marvin-sbx-dev"]["running"] = False
    Path(os.environ["FAKE_DOCKER_STATE"]).write_text(json.dumps(state))
    await sbx.ensure(room)
    assert [c[0] for c in fake_docker.calls()][-2:] == ["inspect", "start"]


async def test_remove(fake_docker, tmp_path, room):
    sbx = make(fake_docker, tmp_path)
    await sbx.ensure(room)
    await sbx.remove("dev")
    assert "marvin-sbx-dev" not in fake_docker.state()


async def test_check_reports_missing_image_clearly(fake_docker, tmp_path, monkeypatch):
    sbx = make(fake_docker, tmp_path)
    await sbx.check()  # image present
    monkeypatch.setenv("FAKE_DOCKER_IMAGE_PRESENT", "0")
    with pytest.raises(SandboxError, match="make sandbox-image"):
        await sbx.check()
    # an image that names a registry is pulled instead
    sbx2 = make(fake_docker, tmp_path, image="ghcr.io/acme/sbx:1")
    await sbx2.check()
    assert fake_docker.calls()[-1][:2] == ["pull", "ghcr.io/acme/sbx:1"]


async def test_check_is_a_noop_when_off(tmp_path):
    await Sandbox(SandboxConfig(mode="off", docker="/nonexistent/docker"), state_dir=None).check()


async def test_check_fails_when_daemon_unreachable(tmp_path):
    sbx = Sandbox(SandboxConfig(mode="docker", docker="/nonexistent/docker"), state_dir=str(tmp_path))
    with pytest.raises(SandboxError, match="not reachable"):
        await sbx.check()


# -- exec and the CLI wrapper ---------------------------------------------------------------
def test_exec_argv_forwards_only_present_env(fake_docker, tmp_path, room, monkeypatch):
    sbx = make(fake_docker, tmp_path)
    monkeypatch.setenv("XAI_API_KEY", "k")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    argv = sbx.exec_argv("dev", ["grok", "agent", "stdio"], cwd=room.repo, env={"FOO": "bar"})
    assert argv[:5] == [fake_docker.path, "exec", "-i", "-w", room.repo]
    assert "XAI_API_KEY" in argv and "OPENAI_API_KEY" not in argv and "FOO=bar" in argv
    assert argv[-4:] == ["marvin-sbx-dev", "grok", "agent", "stdio"]


def test_cli_wrapper_runs_the_binary_inside_the_container(fake_docker, tmp_path, room, monkeypatch):
    sbx = make(fake_docker, tmp_path)
    wrapper = sbx.cli_wrapper("dev", "claude")
    assert wrapper.name == "claude" and os.access(wrapper, os.X_OK)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    out = subprocess.run([str(wrapper), "--version"], cwd=room.repo, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "ok"
    call = fake_docker.calls()[-1]
    assert call[:4] == ["exec", "-i", "-w", room.repo]
    assert f"HOME={sbx.home_dir('dev')}" in call
    assert "ANTHROPIC_API_KEY" in call and "GEMINI_API_KEY" not in call
    assert call[-3:] == ["marvin-sbx-dev", "claude", "--version"]
    # rewriting with identical content is a no-op; the file stays executable
    assert sbx.cli_wrapper("dev", "claude") == wrapper and os.access(wrapper, os.X_OK)


async def test_listening_ports_inside_bridge_container(fake_docker, tmp_path, room):
    sbx = make(fake_docker, tmp_path, network="bridge")
    assert await sbx.listening_ports("dev") == {8080}  # 1F90 LISTEN; 0BB8 is ESTABLISHED
    assert await make(fake_docker, tmp_path).listening_ports("dev") is None  # host network: the worker's scanner sees it


# -- registry integration -------------------------------------------------------------------
def test_create_harness_wraps_acp_command_and_points_sdk_at_wrapper(fake_docker, tmp_path, room, monkeypatch):
    monkeypatch.delenv(registry.command_env_var("grok"), raising=False)
    sbx = make(fake_docker, tmp_path).for_room(room)
    h = registry.create_harness("grok", room.repo, sandbox=sbx)
    assert h.command[:3] == [fake_docker.path, "exec", "-i"] and h.command[-4:] == ["marvin-sbx-dev", "grok", "agent", "stdio"]
    c = registry.create_harness("claude-code", room.repo, sandbox=sbx)
    assert c.cli_path == str(tmp_path / "state" / "sandbox" / "dev" / "bin" / "claude")
    plain = registry.create_harness("grok", room.repo)
    assert plain.command == ["grok", "agent", "stdio"]


def test_default_forward_env_has_the_provider_keys_and_no_livekit_secrets():
    assert {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN"} <= set(DEFAULT_FORWARD_ENV)
    assert not any(n.startswith("LIVEKIT") or n.startswith("MARVIN_SESSION") or n.endswith("PASSWORD") for n in DEFAULT_FORWARD_ENV)
