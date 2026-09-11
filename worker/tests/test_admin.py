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
