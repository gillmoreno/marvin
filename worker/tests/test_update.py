import asyncio
import json
from pathlib import Path

from marvin.update import Install, github_slug


def test_github_slug():
    assert github_slug("https://github.com/gillmoreno/marvin.git") == ("gillmoreno", "marvin")
    assert github_slug("git@github.com:gillmoreno/marvin.git") == ("gillmoreno", "marvin")
    assert github_slug("https://example.com/x.git") is None


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "marvin"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("abc123def456\n")
    (root / "docker-compose.edge.yml").write_text("services: {}\n")
    script = root / "deploy" / "edge"
    script.mkdir(parents=True)
    (script / "update.sh").write_text("#!/bin/sh\n")
    return root


def test_from_env_and_can_apply(tmp_path):
    root = _tree(tmp_path)
    inst = Install.from_env({
        "MARVIN_INSTALL_DIR": str(root),
        "MARVIN_GIT_SHA": "abc123def456",
        "MARVIN_GIT_REF": "main",
        "MARVIN_STATE_DIR": str(tmp_path / "state"),
    })
    assert inst.can_apply() and inst.sha == "abc123def456"
    bare = Install.from_env({"MARVIN_STATE_DIR": str(tmp_path / "state")})
    assert not bare.can_apply() and bare.sha is None


async def test_describe_lists_commits_behind(tmp_path):
    root = _tree(tmp_path)
    async def fetch(path: str):
        if path.startswith("/commits/"):
            return {"sha": "fff000111222", "commit": {"message": "Immediate feedback on Send\n\nbody"}}
        if path.startswith("/compare/"):
            return {"commits": [
                {"sha": "bbb", "commit": {"message": "older"}},
                {"sha": "cccddd", "commit": {"message": "Immediate feedback on Send"}},
            ]}
        return None

    inst = Install(root, "abc123def456", "main", "https://github.com/gillmoreno/marvin.git", tmp_path / "update.json", fetch=fetch)
    d = await inst.describe()
    assert d["behind"] is True and d["can_apply"] is True
    assert d["latest_short"] == "fff0001"
    assert d["commits"][0]["message"] == "Immediate feedback on Send"
    assert d["latest_message"] == "Immediate feedback on Send"


async def test_describe_current_is_not_behind(tmp_path):
    root = _tree(tmp_path)
    sha = "abc123def456999"
    async def fetch(path: str):
        if path.startswith("/commits/"):
            return {"sha": sha, "commit": {"message": "same"}}
        return None

    inst = Install(root, sha[:7], "main", "https://github.com/gillmoreno/marvin.git", tmp_path / "update.json", fetch=fetch)
    d = await inst.describe()
    assert d["behind"] is False and d["commits"] == []


async def test_start_runs_script_once(tmp_path):
    root = _tree(tmp_path)
    ran = []
    gate = asyncio.Event()

    async def runner(cmd, cwd):
        ran.append((cmd, cwd))
        await gate.wait()

    inst = Install(root, "abc", "main", "https://github.com/gillmoreno/marvin.git", tmp_path / "update.json", fetch=lambda p: None, runner=runner)
    assert inst.start()["started"] is True
    assert (await inst.describe())["applying"] is True
    try:
        inst.start()
        raise AssertionError("second start should fail while applying")
    except RuntimeError as e:
        assert "already" in str(e)
    gate.set()
    for _ in range(50):
        await asyncio.sleep(0.01)
        if not inst._state().get("applying"):
            break
    assert ran and ran[0][1] == root
    assert ran[0][0][1].endswith("deploy/edge/update.sh")
    st = json.loads((tmp_path / "update.json").read_text())
    assert st["applying"] is False and st["error"] is None
