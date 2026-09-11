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


def test_stale_session_id_falls_back_to_fresh_session(tmp_path, monkeypatch):
    monkeypatch.setattr(sess_mod, "ClaudeCodeHarness", FakeHarness)
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
