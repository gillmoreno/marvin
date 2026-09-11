import asyncio

from marvin.adapters.base import HarnessEvent
from marvin.bridge import Segment, Timeline
from marvin.room.conductor import Conductor


class FakeHarness:
    name = "fake"

    def __init__(self):
        self.prompts = []
        self.permissions = None

    async def start(self):
        pass

    async def close(self):
        pass

    async def interrupt(self):
        pass

    async def send(self, prompt):
        self.prompts.append(prompt)
        yield HarnessEvent("turn_start")
        yield HarnessEvent("tool_use", {"id": "t1", "tool": "Bash", "input": {"command": "ls"}})
        allowed = await self.permissions.ask("Bash", {"command": "ls"})
        yield HarnessEvent("tool_result", {"id": "t1", "output": "ok" if allowed else "denied", "is_error": not allowed})
        yield HarnessEvent("text", {"text": "x" * 30_000})  # bigger than one packet
        yield HarnessEvent("result", {"subtype": "success", "is_error": False, "cost_usd": 0.01, "duration_ms": 5, "session_id": "s1"})


def test_full_turn_with_approval():
    async def run():
        events = []

        async def publish(ev):
            events.append(ev)
            if ev["kind"] == "permission_request":  # a client clicks Allow
                asyncio.create_task(c.on_control("Ana", {"action": "approve", "id": ev["id"]}))

        h = FakeHarness()
        c = Conductor(h, publish, timeline=Timeline(t0=0.0))
        h.permissions = c.permissions
        await c.start()
        await c.on_segment(Segment(start=1, end=2, speaker="Ana", text="let's list the files", final=True))
        await c.on_segment(Segment(start=3, end=4, speaker="Gil", text="Marvin list the files", final=True))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if any(e["kind"] == "result" for e in events):
                break
        await c.close()
        return h, events

    h, events = asyncio.run(run())
    kinds = [e["kind"] for e in events]
    assert kinds[:2] == ["status", "transcript"]
    assert "turn_start" in kinds and "permission_request" in kinds and "permission_resolved" in kinds and "result" in kinds
    assert kinds.count("turn_start") == 1  # harness's own turn_start is dropped
    assert "Ana: let's list the files" in h.prompts[0] and 'Gil is now addressing you: "list the files"' in h.prompts[0]
    assert [e for e in events if e["kind"] == "tool_result"][0]["output"] == "ok"
    assert all(len(str(e)) < 15_000 for e in events)  # long text was chunked
    assert [e["state"] for e in events if e["kind"] == "status"] == ["idle", "thinking", "waiting_approval", "idle"]


def test_typed_ask_becomes_turn():
    async def run():
        events = []

        async def publish(ev):
            events.append(ev)
            if ev["kind"] == "permission_request":
                asyncio.create_task(c.on_control("Gil", {"action": "deny", "id": ev["id"]}))

        h = FakeHarness()
        c = Conductor(h, publish, timeline=Timeline(t0=0.0))
        h.permissions = c.permissions
        await c.start()
        await c.on_control("Gil", {"action": "ask", "text": "what does this repo do"})
        for _ in range(200):
            await asyncio.sleep(0.01)
            if any(e["kind"] == "result" for e in events):
                break
        await c.close()
        return h, events

    h, events = asyncio.run(run())
    assert 'Gil is now addressing you: "what does this repo do"' in h.prompts[0]
    assert [e for e in events if e["kind"] == "tool_result"][0]["is_error"] is True


def test_auto_approve_is_admin_only():
    async def run():
        events = []

        async def publish(ev):
            events.append(ev)

        h = FakeHarness()
        c = Conductor(h, publish, timeline=Timeline(t0=0.0))
        h.permissions = c.permissions
        await c.start()
        events.clear()
        await c.on_control("Pat", {"action": "auto_approve", "on": True})  # no roles at all
        await c.on_control("Pat", {"action": "auto_approve", "on": True}, roles=frozenset({"participant"}))
        after_participants = (c.permissions.auto_approve, list(events))
        await c.on_control("Root", {"action": "auto_approve", "on": True}, roles=frozenset({"participant", "admin"}))
        await c.close()
        return after_participants, c.permissions.auto_approve, events

    (off, denied), on, events = asyncio.run(run())
    assert off is False
    assert denied == [{"kind": "denied", "action": "auto_approve", "by": "Pat", "reason": "admin role required"}] * 2
    assert on is True
    assert {"kind": "auto_approve", "on": True, "by": "Root"} in events


def test_announce_includes_app_links():
    async def run():
        events = []

        async def publish(ev):
            events.append(ev)

        h = FakeHarness()
        c = Conductor(h, publish, timeline=Timeline(t0=0.0), app_links=[{"label": "frontend", "url": "https://x"}])
        h.permissions = c.permissions
        await c.start()
        events.clear()
        await c.announce()  # what a late joiner receives
        await c.close()
        return events

    events = asyncio.run(run())
    assert {"kind": "app_links", "links": [{"label": "frontend", "url": "https://x"}]} in events
