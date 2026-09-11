"""RemoteSegmenter against an in-process fake marvin-stt server: VAD -> streamed audio -> partial + final segments."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess

import numpy as np
import pytest
from aiohttp import WSMsgType, web

from marvin.bridge import WakeDetector
from marvin.stt.remote_stream import SAMPLE_RATE, RemoteSegmenter

pytestmark = pytest.mark.skipif(shutil.which("say") is None or shutil.which("ffmpeg") is None, reason="needs macOS say + ffmpeg")


def synth(text: str, tmp_path) -> np.ndarray:
    aiff = tmp_path / "u.aiff"
    subprocess.run(["say", "-o", str(aiff), text], check=True)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(aiff), "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"], check=True, capture_output=True
    ).stdout
    return np.frombuffer(raw, dtype=np.int16)


class FakeSTT:
    """Echoes a transcript that encodes how much audio it received; the 'transcript' is the seconds count."""

    def __init__(self):
        self.utterances: list[tuple[str, int]] = []  # (lang, samples)
        self.starts = 0

    async def handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        lang, n, partials = "auto", 0, 0
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                n += len(msg.data) // 2
                if n // 5120 > partials:
                    partials = n // 5120
                    await ws.send_json({"type": "partial", "text": f"heard {n / SAMPLE_RATE:.1f}s"})
            elif msg.type == WSMsgType.TEXT:
                cmd = json.loads(msg.data)
                if cmd["op"] == "start":
                    self.starts += 1
                    lang = cmd.get("lang", "auto")
                    await ws.send_json({"type": "ready", "chunk_ms": 320, "lang": lang})
                elif cmd["op"] == "end":
                    self.utterances.append((lang, n))
                    await ws.send_json({"type": "final", "text": f"Marvin, heard {n / SAMPLE_RATE:.1f} seconds", "lang": "en-US", "utterance": len(self.utterances)})
                    n, partials = 0, 0
                elif cmd["op"] == "close":
                    break
        return ws


@pytest.fixture
async def fake(aiohttp_server):
    stt = FakeSTT()
    app = web.Application()
    app.router.add_get("/v1/stream", stt.handler)
    srv = await aiohttp_server(app)
    return srv, stt


async def test_speech_is_streamed_and_finalized(fake, tmp_path):
    srv, stt = fake
    got: list = []
    clock = {"t": 0.0}
    seg = RemoteSegmenter(str(srv.make_url("/v1/stream")), "Gil", got.append, clock=lambda: clock["t"], language="en")
    silence = np.zeros(SAMPLE_RATE, dtype=np.int16)
    audio = np.concatenate([silence, synth("Marvin, is the retry logic exponential with a cap", tmp_path), silence])
    step = SAMPLE_RATE // 50
    for i in range(0, audio.size, step):
        clock["t"] += 0.02
        await seg.push(audio[i : i + step])
        await asyncio.sleep(0)  # frames arrive one at a time from the room; let the reader task run between them
    await seg.flush()
    await seg.drain()
    await seg.close()

    finals = [s for s in got if s.final]
    partials = [s for s in got if not s.final]
    assert len(finals) == 1, got
    assert partials, "expected interim segments while speaking"
    assert stt.starts == 1 and stt.utterances[0][0] == "en"
    spoken = stt.utterances[0][1] / SAMPLE_RATE
    assert 1.0 < spoken < 5.0, spoken  # VAD trimmed the leading/trailing silence
    assert WakeDetector().detect(finals[0].text) is not None
    assert finals[0].end > finals[0].start > 0.5
    assert all(p.start == finals[0].start for p in partials)


async def test_unreachable_service_drops_utterance_quietly(tmp_path):
    got: list = []
    seg = RemoteSegmenter("ws://127.0.0.1:1/v1/stream", "Gil", got.append, language="en")
    audio = synth("hello there", tmp_path)
    await seg.push(audio)
    await seg.flush()
    await seg.drain()
    await seg.close()
    assert got == []
