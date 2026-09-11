import datetime as dt

import pytest
from aiohttp.test_utils import TestClient, TestServer

from marvin.gate import Power, Schedule, make_app


class FakeK8s:
    def __init__(self):
        self.desired = {"marvin": 1, "marvin-stt": 1}
        self.ready = {"marvin": 1, "marvin-stt": 1}
        self.endpoints = True

    async def replicas(self, kind, name):
        return self.desired[name], self.ready[name]

    async def scale(self, kind, name, n):
        self.desired[name] = n
        self.ready[name] = 0  # takes time
        self.endpoints = False if n == 0 else self.endpoints

    async def has_endpoints(self, service):
        return self.endpoints


def at(h, m, weekday=0):  # 2026-09-14 is a Monday
    base = dt.datetime(2026, 9, 14, h, m, tzinfo=dt.timezone.utc)
    return base + dt.timedelta(days=weekday) - dt.timedelta(hours=2)  # Rome is UTC+2 in September


def test_schedule_decisions():
    s = Schedule(sleep_at=dt.time(20, 0), wake_at=dt.time(8, 0), tz="Europe/Rome")
    assert s.decide(at(20, 0), "awake", someone_in_a_room=False) == "sleep"
    assert s.decide(at(20, 0), "awake", someone_in_a_room=True) is None
    assert s.decide(at(20, 0), "asleep", False) is None
    assert s.decide(at(8, 0), "asleep", False) == "wake"
    assert s.decide(at(8, 0, weekday=5), "asleep", False) is None  # Saturday: stay asleep
    assert s.decide(at(12, 30), "awake", False) is None
    assert Schedule(sleep_at=None, wake_at=None).decide(at(20, 0), "awake", False) is None
    assert Schedule.from_env({"MARVIN_SLEEP_AT": "20:00", "TZ": "Europe/Rome"}).sleep_at == dt.time(20, 0)


async def test_power_roundtrip_and_routes():
    k = FakeK8s()
    p = Power(k)
    assert (await p.status()).state == "awake"
    async with TestClient(TestServer(make_app(p))) as c:
        r = await c.post("/power/sleep")
        j = await r.json()
        assert j["state"] == "asleep" and k.desired == {"marvin": 0, "marvin-stt": 0}
        assert (await c.get("/api/rooms")).status == 503  # the SPA's calls while asleep
        page = await (await c.get("/anything")).text()
        assert "Marvin is asleep" in page
        r = await c.post("/power/wake")
        assert (await r.json())["state"] == "waking" and k.desired == {"marvin": 1, "marvin-stt": 1}
        k.ready = {"marvin": 1, "marvin-stt": 1}; k.endpoints = True
        assert (await (await c.get("/power/status")).json())["state"] == "awake"
