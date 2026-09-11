"""WebSocket streaming STT server.

One connection = one speaker. Protocol (all JSON text frames except audio):

  client -> {"op": "start", "lang": "it-IT" | "en" | "auto"}      once per connection (optional; default lang = auto)
  client -> <binary>  int16 little-endian mono 16 kHz PCM, any frame size
  client -> {"op": "end"}                                          end of utterance: flush and reset the stream
  server -> {"type": "ready", "chunk_ms": 320, "lang": "it-IT"}
  server -> {"type": "partial", "text": "..."}                     after every processed chunk
  server -> {"type": "final", "text": "...", "lang": "it-IT"|null, "utterance": 3}
  server -> {"type": "error", "message": "..."}

Audio after an `end` starts a new utterance automatically (fresh encoder cache). GET /healthz answers 200 once the
model is loaded, so Kubernetes can probe it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Protocol

import numpy as np
from aiohttp import WSMsgType, web

log = logging.getLogger(__name__)


class StreamLike(Protocol):
    text: str
    detected_lang: str | None

    async def feed(self, pcm: np.ndarray) -> str | None: ...
    async def finish(self) -> str: ...


class EngineLike(Protocol):
    chunk_ms: int
    langs: list[str]

    def resolve_lang(self, lang: str | None) -> str: ...
    def new_stream(self, lang: str | None = None) -> StreamLike: ...


def make_app(engine: EngineLike) -> web.Application:
    app = web.Application()
    app["engine"] = engine
    app["loaded"] = asyncio.Event()
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/v1/stream", stream)
    return app


async def healthz(request: web.Request) -> web.Response:
    if not request.app["loaded"].is_set():
        return web.Response(status=503, text="loading")
    return web.json_response({"ok": True, "chunk_ms": request.app["engine"].chunk_ms})


async def stream(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(max_msg_size=4 * 1024 * 1024, heartbeat=20)
    await ws.prepare(request)
    engine: EngineLike = request.app["engine"]
    if not request.app["loaded"].is_set():
        await ws.send_json({"type": "error", "message": "model loading"})
        await ws.close()
        return ws

    lang = engine.resolve_lang(None)
    st: StreamLike | None = None
    n_utt = 0
    peer = request.remote
    t_utt = 0.0

    async def ensure_stream() -> StreamLike:
        nonlocal st, t_utt
        if st is None:
            st = engine.new_stream(lang)
            t_utt = time.monotonic()
        return st

    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                pcm = np.frombuffer(msg.data, dtype=np.int16)
                if pcm.size == 0:
                    continue
                s = await ensure_stream()
                text = await s.feed(pcm)
                if text is not None:
                    await ws.send_json({"type": "partial", "text": text})
            elif msg.type == WSMsgType.TEXT:
                try:
                    cmd = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "bad json"})
                    continue
                op = cmd.get("op")
                if op == "start":
                    try:
                        lang = engine.resolve_lang(cmd.get("lang"))
                    except ValueError as e:
                        await ws.send_json({"type": "error", "message": str(e)})
                        continue
                    await ws.send_json({"type": "ready", "chunk_ms": engine.chunk_ms, "lang": lang})
                elif op == "end":
                    if st is None:
                        await ws.send_json({"type": "final", "text": "", "lang": None, "utterance": n_utt})
                        continue
                    text = await st.finish()
                    n_utt += 1
                    log.info("%s utt %d (%.1fs) [%s]: %s", peer, n_utt, time.monotonic() - t_utt, st.detected_lang or lang, text)
                    await ws.send_json({"type": "final", "text": text, "lang": st.detected_lang, "utterance": n_utt})
                    st = None
                elif op == "close":
                    break
                else:
                    await ws.send_json({"type": "error", "message": f"unknown op {op!r}"})
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR):
                break
    except Exception:
        log.exception("%s: stream failed", peer)
        if not ws.closed:
            await ws.send_json({"type": "error", "message": "internal error"})
    finally:
        if st is not None:
            try:
                await st.finish()
            except Exception:
                pass
        await ws.close()
    return ws


async def serve(engine, *, host: str, port: int, load) -> None:
    """Start HTTP immediately (so probes see 503 while loading), load the model in a thread, then accept streams."""
    app = make_app(engine)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("listening on %s:%d, loading model...", host, port)
    await asyncio.to_thread(load)
    app["loaded"].set()
    log.info("ready")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
