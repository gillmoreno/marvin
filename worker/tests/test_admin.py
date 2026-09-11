import pytest
from aiohttp.test_utils import TestClient, TestServer

from marvin.admin import make_admin_app
from marvin.config import Config
from marvin.room import manager as mgr_mod
from marvin.room.manager import RoomManager
from tests.test_manager import FakeSession


@pytest.mark.asyncio
async def test_admin_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(mgr_mod, "RoomSession", FakeSession)
    (tmp_path / "repos").mkdir()
    mgr = RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})
    async with TestClient(TestServer(make_admin_app(mgr))) as c:
        assert (await (await c.get("/rooms")).json()) == {"rooms": []}
        r = await c.post("/rooms", json={"name": "demo"})
        assert r.status == 201 and (await r.json())["live"]
        r = await c.post("/rooms", json={"name": "demo"})
        assert r.status == 400
        assert (await c.get("/repos")).status == 200
        assert (await c.get("/ports")).status == 200
        assert (await c.delete("/rooms/demo")).status == 204
        assert (await c.delete("/rooms/demo")).status == 404


@pytest.mark.asyncio
async def test_harnesses_and_models(tmp_path, monkeypatch):
    from tests.test_room_update import ReconfSession

    monkeypatch.setattr(mgr_mod, "RoomSession", ReconfSession)
    monkeypatch.delenv("MARVIN_HARNESS", raising=False)
    monkeypatch.setenv("MARVIN_HARNESS_CMD_GROK", "/opt/grok agent stdio")
    (tmp_path / "repos").mkdir()
    mgr = RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})
    async with TestClient(TestServer(make_admin_app(mgr))) as c:
        j = await (await c.get("/harnesses")).json()
        assert j["default"] == "claude-code"
        by_id = {h["id"]: h for h in j["harnesses"]}
        assert set(by_id) >= {"claude-code", "claude-acp", "codex", "cursor", "gemini", "opencode", "grok", "copilot"}
        assert by_id["grok"]["command"] == ["/opt/grok", "agent", "stdio"] and "env" not in by_id["grok"]
        assert by_id["opencode"]["kind"] == "acp" and by_id["opencode"]["auth"]
        # models: default harness, an explicit one, an unknown one
        j = await (await c.get("/models")).json()
        assert j["harness"] == "claude-code" and j["default"] == "claude-fable-5-1" and [m["id"] for m in j["models"]][0] == "claude-fable-5-1"
        j = await (await c.get("/models?harness=opencode")).json()
        assert j == {"harness": "opencode", "models": [], "default": ""}
        assert (await c.get("/models?harness=nope")).status == 404
        # models?room=: an unknown room or a harness that reports nothing falls back to the profile list
        j = await (await c.get("/models?room=ghost&harness=opencode")).json()
        assert j == {"harness": "opencode", "models": [], "default": ""}
        # PATCH with a harness
        r = await c.post("/rooms", json={"name": "demo"})
        assert r.status == 201 and (await r.json())["harness"] == "claude-code"
        r = await c.patch("/rooms/demo", json={"harness": "codex"})
        assert r.status == 200 and (await r.json())["harness"] == "codex" and (await r.json())["harness_pinned"] == "codex"
        assert (await c.patch("/rooms/demo", json={"harness": "nope"})).status == 400
        r = await c.patch("/rooms/demo", json={"harness": ""})
        assert r.status == 200 and (await r.json())["harness_pinned"] is None
        assert (await c.patch("/rooms/ghost", json={"harness": "codex"})).status == 404


class _LiveHarness:
    name = "grok"
    model = "grok-4.6"
    available_models = [{"id": "grok-4.6", "label": "Grok 4.6", "note": ""}, {"id": "grok-4.6-mini", "label": "Grok 4.6 mini", "note": "fast"}]


@pytest.mark.asyncio
async def test_models_reported_by_live_agent(tmp_path, monkeypatch):
    """An ACP agent that reports its own models wins over the profile's (empty) static list for that room."""
    from tests.test_room_update import ReconfSession

    class LiveSession(ReconfSession):
        @property
        def harness(self):
            return _LiveHarness()

    monkeypatch.setattr(mgr_mod, "RoomSession", LiveSession)
    monkeypatch.delenv("MARVIN_HARNESS", raising=False)
    (tmp_path / "repos").mkdir()
    mgr = RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})
    async with TestClient(TestServer(make_admin_app(mgr))) as c:
        assert (await c.post("/rooms", json={"name": "demo"})).status == 201
        j = await (await c.get("/models?room=demo&harness=grok")).json()
        assert j["live"] is True and j["harness"] == "grok" and j["default"] == "grok-4.6"
        assert [m["id"] for m in j["models"]] == ["grok-4.6", "grok-4.6-mini"]
        # the room's effective model in /rooms is what the agent says it runs
        rooms = (await (await c.get("/rooms")).json())["rooms"]
        assert rooms[0]["model"] == "grok-4.6" and rooms[0]["harness"] == "grok"
