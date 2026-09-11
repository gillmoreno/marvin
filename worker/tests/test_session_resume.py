"""A stale saved session id must not take the room down: start again without resume."""
import asyncio
import json

from marvin.config import RoomConfig
from marvin.room import session as sess_mod


class FakeHarness:
    calls = []

    def __init__(self, cwd, permissions=None, *, resume=None, **kw):
        self.resume = resume
        self.permissions = permissions
        self.session_id = resume
        self.model = kw.get("model")

    async def start(self):
        FakeHarness.calls.append(self.resume)
        if self.resume:
            raise RuntimeError(f"No conversation found with session ID: {self.resume}")

    async def close(self):
        pass

    async def interrupt(self):
        pass

    def send(self, prompt):  # pragma: no cover
        raise NotImplementedError


class FakeRoom:
    def __init__(self):
        self.local_participant = self

    def on(self, *_a, **_k):
        return lambda f: f

    async def connect(self, *a, **k):
        pass

    async def disconnect(self):
        pass

    async def publish_data(self, *a, **k):
        pass


def test_switching_harness_drops_the_saved_session(tmp_path, monkeypatch):
    made = []

    class Quiet(FakeHarness):
        def __init__(self, cwd, permissions=None, *, profile, resume=None, **kw):
            super().__init__(cwd, permissions, resume=resume, **kw)
            self.name = profile
            made.append(self)

        async def start(self):
            pass

    monkeypatch.setattr(sess_mod, "create_harness", lambda profile, cwd, **kw: Quiet(cwd, profile=profile, **kw))
    monkeypatch.setattr(sess_mod.rtc, "Room", FakeRoom)
    monkeypatch.setattr(sess_mod, "agent_token", lambda *a, **k: "jwt")
    monkeypatch.delenv("MARVIN_HARNESS", raising=False)
    state = tmp_path / "state"; state.mkdir()
    (state / "r.json").write_text(json.dumps({"session_id": "sess-claude"}))
    repo = tmp_path / "repo"; repo.mkdir()
    cfg = RoomConfig(name="r", repo=str(repo))

    async def run():
        s = sess_mod.RoomSession(cfg, url="ws://x", api_key="k", api_secret="s", stt=lambda *a, **k: None, state_dir=str(state))
        await s.start()
        assert made[-1].name == "claude-code" and made[-1].resume == "sess-claude"
        # same harness, new model: the conversation is resumed
        await s.reconfigure(RoomConfig(name="r", repo=str(repo), model="claude-sonnet-5"))
        assert made[-1].name == "claude-code" and made[-1].resume == "sess-claude" and made[-1].model == "claude-sonnet-5"
        # different harness: no resume, and the saved id is cleared so a restart does not try it either
        await s.reconfigure(RoomConfig(name="r", repo=str(repo), harness="opencode"))
        assert made[-1].name == "opencode" and made[-1].resume is None
        assert json.loads((state / "r.json").read_text())["session_id"] is None
        assert s.harness is made[-1]
        await s.close()

    asyncio.run(run())


def test_stale_session_id_falls_back_to_fresh_session(tmp_path, monkeypatch):
    monkeypatch.setattr(sess_mod, "create_harness", lambda profile, cwd, **kw: FakeHarness(cwd, **kw))
    monkeypatch.setattr(sess_mod.rtc, "Room", FakeRoom)
    monkeypatch.setattr(sess_mod, "agent_token", lambda *a, **k: "jwt")
    state = tmp_path / "state"; state.mkdir()
    (state / "r.json").write_text(json.dumps({"session_id": "deadbeef-0000"}))
    repo = tmp_path / "repo"; repo.mkdir()
    cfg = RoomConfig(name="r", repo=str(repo))

    async def run():
        s = sess_mod.RoomSession(cfg, url="ws://x", api_key="k", api_secret="s", stt=lambda *a, **k: None, state_dir=str(state))
        await s.start()
        assert FakeHarness.calls == ["deadbeef-0000", None]
        assert json.loads((state / "r.json").read_text())["session_id"] is None
        await s.close()

    asyncio.run(run())
