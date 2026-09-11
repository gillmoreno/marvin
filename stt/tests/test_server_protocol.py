"""Server protocol with a fake engine (no NeMo, no GPU): start/partial/final/reset semantics."""
from __future__ import annotations

import json

import aiohttp
import numpy as np
import pytest
from aiohttp import web

from marvin_stt.server import make_app


class FakeStream:
    def __init__(self, engine, lang):
        self.engine, self.lang = engine, lang
        self.n = 0
        self.text = ""
        self.detected_lang = None
        self.finished = False

    async def feed(self, pcm):
        self.n += pcm.size
        # "a chunk" every 5120 samples (320 ms): emit a partial with the running count
        if self.n // 5120 > len(self.text.split()):
            self.text = " ".join(f"w{i}" for i in range(self.n // 5120))
            return self.text
        return None

    async def finish(self):
        self.finished = True
        self.detected_lang = "it-IT" if self.lang == "auto" else self.lang
        self.text = (self.text + " end").strip()
        return self.text


class FakeEngine:
    chunk_ms = 320
    langs = ["auto", "en", "en-US", "it", "it-IT"]

    def __init__(self):
        self.streams: list[FakeStream] = []

    def resolve_lang(self, lang):
        lang = lang or "auto"
        if lang in self.langs:
            return lang
        raise ValueError(f"unsupported language {lang!r}")

    def new_stream(self, lang=None):
        s = FakeStream(self, self.resolve_lang(lang))
        self.streams.append(s)
        return s


@pytest.fixture
async def server(aiohttp_server):
    engine = FakeEngine()
    app = make_app(engine)
    app["loaded"].set()
    srv = await aiohttp_server(app)
    return srv, engine


async def test_healthz_reports_loading_then_ready(aiohttp_client):
    app = make_app(FakeEngine())
    client = await aiohttp_client(app)
    assert (await client.get("/healthz")).status == 503
    app["loaded"].set()
    assert (await client.get("/healthz")).status == 200


async def test_partials_final_and_reset(server):
    srv, engine = server
    async with aiohttp.ClientSession() as sess, sess.ws_connect(srv.make_url("/v1/stream")) as ws:
        await ws.send_json({"op": "start", "lang": "it"})
        assert await ws.receive_json() == {"type": "ready", "chunk_ms": 320, "lang": "it"}

        pcm = np.zeros(5120, dtype=np.int16).tobytes()
        got = []
        for _ in range(3):
            await ws.send_bytes(pcm)
            got.append(await ws.receive_json())
        assert [g["type"] for g in got] == ["partial"] * 3
        assert got[-1]["text"] == "w0 w1 w2"

        await ws.send_json({"op": "end"})
        fin = await ws.receive_json()
        assert fin == {"type": "final", "text": "w0 w1 w2 end", "lang": "it", "utterance": 1}

        # next audio starts a fresh stream with the same language
        await ws.send_bytes(pcm)
        assert (await ws.receive_json())["text"] == "w0"
        await ws.send_json({"op": "end"})
        assert (await ws.receive_json())["utterance"] == 2
        assert len(engine.streams) == 2 and all(s.finished for s in engine.streams)
        await ws.send_json({"op": "close"})


async def test_end_without_audio_and_bad_lang(server):
    srv, _ = server
    async with aiohttp.ClientSession() as sess, sess.ws_connect(srv.make_url("/v1/stream")) as ws:
        await ws.send_json({"op": "start", "lang": "xx-XX"})
        assert (await ws.receive_json())["type"] == "error"
        await ws.send_json({"op": "end"})
        assert (await ws.receive_json()) == {"type": "final", "text": "", "lang": None, "utterance": 0}
        await ws.send_str("not json")
        assert (await ws.receive_json())["type"] == "error"
        await ws.send_json({"op": "close"})


async def test_disconnect_mid_utterance_finishes_stream(server):
    srv, engine = server
    async with aiohttp.ClientSession() as sess:
        ws = await sess.ws_connect(srv.make_url("/v1/stream"))
        await ws.send_bytes(np.zeros(1000, dtype=np.int16).tobytes())
        await ws.close()
    import asyncio

    for _ in range(50):
        if engine.streams and engine.streams[0].finished:
            break
        await asyncio.sleep(0.02)
    assert engine.streams[0].finished
