import asyncio

import pytest

from marvin.config import Config, RoomConfig
from marvin.room import manager as mgr_mod
from marvin.room.manager import RoomManager
from tests.test_manager import FakeSession


class ReconfSession(FakeSession):
    def __init__(self, cfg, **kw):
        super().__init__(cfg, **kw)
        self.reconfigured = []

    @property
    def harness(self):
        return None

    async def reconfigure(self, cfg):
        self.cfg = cfg
        self.reconfigured.append((cfg.model, cfg.linked, cfg.harness))


def test_update_model_and_linked_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(mgr_mod, "RoomSession", ReconfSession)
    monkeypatch.setattr(mgr_mod, "listening_ports", lambda: set())
    (tmp_path / "repos" / "backend").mkdir(parents=True)
    static = Config(rooms=(RoomConfig(name="front", repo=str(tmp_path / "repos" / "front")),))

    async def run():
        m = RoomManager(static, repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})
        await m.start_all()
        r = await m.update_room("front", model="claude-sonnet-5", linked=["backend"])
        assert r["model"] == "claude-sonnet-5" and r["linked"] == [str(tmp_path / "repos" / "backend")]
        assert m.sessions["front"].reconfigured[-1][0] == "claude-sonnet-5"
        with pytest.raises(ValueError):
            await m.update_room("front", linked=["nope"])
        with pytest.raises(KeyError):
            await m.update_room("ghost", model="x")
        r = await m.update_room("front", clear_model=True)
        assert r["model"] is None and r["linked"] == [str(tmp_path / "repos" / "backend")]
        await m.close()
        # overrides survive a restart, even for a static room
        m2 = RoomManager(static, repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})
        assert m2.configs()["front"].linked == (str(tmp_path / "repos" / "backend"),)

    asyncio.run(run())


def test_update_harness_persists_and_reconfigures(tmp_path, monkeypatch):
    monkeypatch.setattr(mgr_mod, "RoomSession", ReconfSession)
    monkeypatch.setattr(mgr_mod, "listening_ports", lambda: set())
    monkeypatch.delenv("MARVIN_HARNESS", raising=False)
    (tmp_path / "repos").mkdir()
    static = Config(rooms=(RoomConfig(name="front", repo=str(tmp_path / "repos" / "front")),))

    async def run():
        m = RoomManager(static, repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})
        await m.start_all()
        assert m.describe_one("front")["harness"] == "claude-code" and m.describe_one("front")["harness_pinned"] is None
        r = await m.update_room("front", harness="opencode")
        assert r["harness"] == "opencode" and r["harness_pinned"] == "opencode"
        assert m.sessions["front"].reconfigured[-1][2] == "opencode"
        with pytest.raises(ValueError):
            await m.update_room("front", harness="not-a-harness")
        r = await m.update_room("front", clear_harness=True)
        assert r["harness"] == "claude-code" and r["harness_pinned"] is None
        await m.update_room("front", harness="codex")
        await m.close()
        m2 = RoomManager(static, repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})
        assert m2.configs()["front"].harness == "codex"

    asyncio.run(run())


def test_notes_roundtrip(tmp_path, monkeypatch):
    from marvin import notes
    monkeypatch.setattr(notes.Path, "home", classmethod(lambda cls: tmp_path))
    assert "This machine" in notes.read_notes()  # template when missing
    notes.write_notes("# mine\n- frontend needs backend :8050")
    assert notes.read_notes().endswith("backend :8050\n") and (tmp_path / ".claude" / "CLAUDE.md").exists()
