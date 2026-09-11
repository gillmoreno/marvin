import asyncio
import subprocess

import pytest

from marvin.config import Config, RoomConfig
from marvin.room import manager as mgr_mod
from marvin.room.manager import RoomManager


class FakeSession:
    def __init__(self, cfg, **kw):
        self.cfg = cfg
        self.conductor = type("C", (), {"app_links": [], "set_app_links": self._set})()
        self.started = False

    async def _set(self, links):
        self.conductor.app_links = links

    async def start(self):
        self.started = True

    async def close(self):
        self.started = False


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    monkeypatch.setattr(mgr_mod, "RoomSession", FakeSession)
    monkeypatch.setattr(mgr_mod, "listening_ports", lambda: {3000})
    (tmp_path / "repos").mkdir()
    cfg = Config(rooms=(RoomConfig(name="static", repo=str(tmp_path / "repos" / "static")),))
    return RoomManager(cfg, repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})


def test_create_persist_and_reload(mgr, tmp_path, monkeypatch):
    async def run():
        await mgr.start_all()
        assert set(mgr.sessions) == {"static"}
        room = await mgr.create_room("backend", git_url=None)
        assert room["live"] and room["repo"].endswith("/repos/backend") and not room["static"]
        with pytest.raises(ValueError):
            await mgr.create_room("Bad Name!")
        with pytest.raises(ValueError):
            await mgr.create_room("static")
        with pytest.raises(ValueError):
            await mgr.delete_room("static")
        await asyncio.sleep(0.01)
        await mgr._watch_ports.__wrapped__(mgr) if hasattr(mgr._watch_ports, "__wrapped__") else None
        await mgr.close()
        # a new manager on the same state dir sees the dynamic room
        m2 = RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})
        assert "backend" in m2.configs() and "static" not in m2.configs()
        await m2.start_all()
        await m2.delete_room("backend")
        assert m2.describe() == []
        await m2.close()

    asyncio.run(run())


def test_ports_become_app_links(mgr):
    async def run():
        await mgr.start_all()
        # let the watcher run one iteration
        await asyncio.sleep(0.05)
        links = mgr.sessions["static"].conductor.app_links
        assert {"label": "port 3000", "url": "http://localhost:3000"} in links
        await mgr.close()

    asyncio.run(run())


def test_clone_repo(mgr, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    subprocess.run(["git", "-C", str(src), "commit", "-q", "--allow-empty", "-m", "init"], check=True, env=env)

    async def run():
        info = await mgr.clone_repo(str(src), name="cloned")
        assert info["git"] and info["path"].endswith("/repos/cloned")
        assert [r["name"] for r in mgr.repos()] == ["cloned"]
        with pytest.raises(ValueError):
            await mgr.clone_repo(str(src), name="cloned")

    asyncio.run(run())
