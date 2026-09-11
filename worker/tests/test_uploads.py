import asyncio
import base64

from marvin.adapters.base import HarnessEvent
from marvin.bridge import Timeline
from marvin.room.conductor import Conductor
from marvin.room.protocol import MAX_PACKET
from marvin.room.uploads import ImageInbox

PNG = base64.b64decode(  # 1x1 transparent png
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def chunks(data: bytes, mime="image/png", name="shot.png", upload_id="abc123", size=8000):
    b64 = base64.b64encode(data).decode()
    parts = [b64[i : i + size] for i in range(0, len(b64), size)] or [""]
    return [{"action": "image", "id": upload_id, "seq": i, "total": len(parts), "mime": mime, "name": name, "data": p} for i, p in enumerate(parts)]


def test_inbox_reassembles_and_writes(tmp_path):
    inbox = ImageInbox(tmp_path)
    msgs = chunks(PNG * 4000, size=64)  # many packets
    assert len(msgs) > 1
    assert all(inbox.add("Gil", m) is None for m in msgs[:-1])
    att = inbox.add("Gil", msgs[-1])
    assert att is not None and att.sender == "Gil" and att.name == "shot.png"
    assert att.path.suffix == ".png" and att.path.read_bytes() == PNG * 4000
    assert all(len(str(m)) < MAX_PACKET for m in msgs)


def test_inbox_rejects_junk(tmp_path):
    inbox = ImageInbox(tmp_path)
    assert inbox.add("Gil", {"action": "image", "id": "x", "seq": 0, "total": 1, "data": "not base64!!"}) is None
    assert inbox.add("Gil", {"action": "image", "id": "x", "seq": 5, "total": 2, "data": ""}) is None
    assert inbox.add("Gil", {"action": "image"}) is None
    assert list(tmp_path.iterdir()) == []


class EchoHarness:
    name = "echo"

    def __init__(self):
        self.prompts = []

    async def start(self):
        pass

    async def close(self):
        pass

    async def interrupt(self):
        pass

    async def send(self, prompt):
        self.prompts.append(prompt)
        yield HarnessEvent("result", {"subtype": "success", "is_error": False, "cost_usd": None, "duration_ms": 1, "session_id": "s1"})


def test_dropped_image_reaches_the_next_turn(tmp_path):
    async def run():
        events = []
        h = EchoHarness()
        c = Conductor(h, lambda ev: _append(events, ev), timeline=Timeline(t0=0.0), uploads_dir=tmp_path)
        await c.start()
        for m in chunks(PNG):
            await c.on_control("Gil", m)
        await c.on_control("Gil", {"action": "ask", "text": "what is wrong with this screen"})
        for _ in range(200):
            await asyncio.sleep(0.01)
            if any(e["kind"] == "result" for e in events):
                break
        await c.close()
        return h, events, c

    h, events, c = asyncio.run(run())
    att = [e for e in events if e["kind"] == "attachment"]
    assert len(att) == 1 and att[0]["name"] == "shot.png" and att[0]["by"] == "Gil"
    assert att[0]["path"] in h.prompts[0] and "Read tool" in h.prompts[0]
    assert c._attachments == []  # claimed by the turn, not re-sent to the next one


async def _append(events, ev):
    events.append(ev)
