"""Streaming speech-to-text through the marvin-stt service (NVIDIA Nemotron 3.5 ASR, see ../../stt).

Same front-end as `WhisperSegmenter` (Silero VAD decides where utterances start and end), but the audio of an
utterance is streamed to the server while it is being spoken: partial transcripts come back every chunk
(Segment.final=False, for the UI) and the final one right after the VAD end (Segment.final=True, for turns).

One `RemoteSegmenter` per speaker track, one WebSocket per segmenter, opened lazily on first speech and reopened
on failure. If the service is unreachable or does not answer, the buffered utterance goes to the `fallback`
(local Whisper, see `make_stt`) so the room never goes deaf.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import aiohttp
import numpy as np

from marvin.bridge.transcript import Segment

from .vad import SileroVAD, VADIterator

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
VAD_WINDOW = 512


class RemoteSegmenter:
    def __init__(
        self,
        url: str,
        speaker: str,
        on_segment: Callable[[Segment], Awaitable[None] | None],
        *,
        clock: Callable[[], float] = time.monotonic,
        language: str | None = None,
        vad_threshold: float = 0.5,
        min_silence_ms: int = 400,  # the model already saw the audio; we only wait for the speaker to stop
        speech_pad_ms: int = 200,
        min_speech_ms: int = 300,
        max_utterance_s: float = 30.0,
        final_timeout_s: float = 8.0,
        session: aiohttp.ClientSession | None = None,
        fallback: Callable[[np.ndarray, float, float], Awaitable[None]] | None = None,
    ) -> None:
        self.url = url
        self.speaker = speaker
        self.on_segment = on_segment
        self.clock = clock
        self.language = language or "auto"
        self.min_speech_samples = int(SAMPLE_RATE * min_speech_ms / 1000)
        self.max_utterance_samples = int(SAMPLE_RATE * max_utterance_s)
        self.final_timeout_s = final_timeout_s
        self._vad = VADIterator(SileroVAD(), threshold=vad_threshold, sampling_rate=SAMPLE_RATE, min_silence_duration_ms=min_silence_ms, speech_pad_ms=speech_pad_ms)
        self._pending = np.empty(0, dtype=np.int16)
        self._in_speech = False
        self._speech_started_at: float | None = None
        self._utt_open = False  # from VAD start until the final transcript arrives: partials are still valid after VAD end
        self.fallback = fallback
        self._utt_buf: list[np.ndarray] = []  # the utterance's audio, kept only so the fallback can transcribe it
        self.fallbacks = 0
        self._utt_samples = 0
        self._session = session
        self._own_session = session is None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader: asyncio.Task | None = None
        self._final: asyncio.Future | None = None
        self._tasks: set[asyncio.Task] = set()
        self._send_lock = asyncio.Lock()
        self.partials = 0
        self.finals = 0

    # -- feeding (same contract as WhisperSegmenter) --------------------------------------
    async def push(self, pcm: np.ndarray) -> None:
        if pcm.dtype != np.int16:
            raise TypeError("expected int16 PCM")
        buf = np.concatenate([self._pending, pcm]) if self._pending.size else pcm
        n_full = (buf.size // VAD_WINDOW) * VAD_WINDOW
        for i in range(0, n_full, VAD_WINDOW):
            await self._window(buf[i : i + VAD_WINDOW])
        self._pending = buf[n_full:].copy()

    async def flush(self) -> None:
        if self._in_speech:
            await self._end_utterance()

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def close(self) -> None:
        await self.flush()
        await self.drain()
        if self._reader:
            self._reader.cancel()
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_json({"op": "close"})
            except Exception:
                pass
            await self._ws.close()
        if self._own_session and self._session:
            await self._session.close()

    async def _window(self, w: np.ndarray) -> None:
        ev = self._vad(w.astype(np.float32) / 32768.0)
        if ev and "start" in ev and not self._in_speech:
            self._in_speech = True
            self._utt_open = True
            self._speech_started_at = self.clock()
            self._utt_samples = 0
            self._utt_buf = []
        if self._in_speech:
            self._utt_samples += w.size
            if self.fallback is not None:
                self._utt_buf.append(w)
            await self._send_audio(w)
        if ev and "end" in ev and self._in_speech:
            await self._end_utterance()
        elif self._in_speech and self._utt_samples >= self.max_utterance_samples:
            await self._end_utterance()

    # -- transport -------------------------------------------------------------------------
    async def _connect(self) -> aiohttp.ClientWebSocketResponse | None:
        if self._ws and not self._ws.closed:
            return self._ws
        if self._session is None:
            self._session = aiohttp.ClientSession()
        try:
            ws = await self._session.ws_connect(self.url, heartbeat=20, max_msg_size=0)
            await ws.send_json({"op": "start", "lang": self.language})
            ready = await asyncio.wait_for(ws.receive_json(), timeout=10)
            if ready.get("type") != "ready":
                raise RuntimeError(f"stt refused: {ready}")
        except Exception as e:
            log.warning("%s: cannot reach stt at %s: %s", self.speaker, self.url, e)
            return None
        self._ws = ws
        if self._reader:
            self._reader.cancel()
        self._reader = asyncio.create_task(self._read(ws))
        log.info("%s: streaming to %s (lang=%s, chunk=%sms)", self.speaker, self.url, ready.get("lang"), ready.get("chunk_ms"))
        return ws

    async def _send_audio(self, w: np.ndarray) -> None:
        ws = await self._connect()
        if ws is None:
            return
        try:
            async with self._send_lock:
                await ws.send_bytes(w.tobytes())
        except Exception as e:
            log.warning("%s: send failed (%s); reconnecting on next utterance", self.speaker, e)
            self._ws = None

    async def _end_utterance(self) -> None:
        self._in_speech = False
        started = self._speech_started_at or self.clock()
        ended = self.clock()
        n = self._utt_samples
        self._utt_samples = 0
        audio = np.concatenate(self._utt_buf) if self._utt_buf else np.empty(0, dtype=np.int16)
        self._utt_buf = []
        ws = self._ws
        if ws is None or ws.closed:
            self._utt_open = False
            if n >= self.min_speech_samples:
                await self._use_fallback(audio, started, ended, "service unreachable")
            return
        loop = asyncio.get_running_loop()
        self._final = loop.create_future()
        try:
            async with self._send_lock:
                await ws.send_json({"op": "end"})
        except Exception as e:
            log.warning("%s: end failed: %s", self.speaker, e)
            self._ws = None
            self._utt_open = False
            if n >= self.min_speech_samples:
                await self._use_fallback(audio, started, ended, "send failed")
            return
        if n < self.min_speech_samples:
            # too short to be a real utterance; still let the server reset, ignore its answer
            self._final = None
            self._utt_open = False
            return
        task = asyncio.create_task(self._await_final(self._final, started, ended, audio))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _use_fallback(self, audio: np.ndarray, started: float, ended: float, why: str) -> None:
        if self.fallback is None or audio.size == 0:
            log.warning("%s: utterance dropped (%s, no fallback)", self.speaker, why)
            return
        self.fallbacks += 1
        log.warning("%s: %s; transcribing the utterance locally", self.speaker, why)
        try:
            await self.fallback(audio, started, ended)
        except Exception as e:
            log.warning("%s: local fallback failed: %s", self.speaker, e)

    async def _await_final(self, fut: asyncio.Future, started: float, ended: float, audio: np.ndarray) -> None:
        try:
            ev = await asyncio.wait_for(fut, timeout=self.final_timeout_s)
        except asyncio.TimeoutError:
            self._utt_open = False
            await self._use_fallback(audio, started, ended, f"no final transcript within {self.final_timeout_s:.0f}s")
            return
        except asyncio.CancelledError:
            return
        except ConnectionError:
            self._utt_open = False
            await self._use_fallback(audio, started, ended, "connection closed")
            return
        finally:
            self._utt_open = False
        text = (ev.get("text") or "").strip()
        if not text:
            return
        self.finals += 1
        seg = Segment(start=started, end=ended, speaker=self.speaker, text=text, final=True)
        log.debug("%s [%s]: %s", self.speaker, ev.get("lang"), text)
        await self._emit(seg)

    async def _read(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                ev = json.loads(msg.data)
                t = ev.get("type")
                if t == "partial":
                    self.partials += 1
                    if self._utt_open and ev.get("text"):
                        await self._emit(Segment(start=self._speech_started_at or self.clock(), end=self.clock(), speaker=self.speaker, text=ev["text"], final=False))
                elif t == "final":
                    if self._final is not None and not self._final.done():
                        self._final.set_result(ev)
                elif t == "error":
                    log.warning("%s: stt error: %s", self.speaker, ev.get("message"))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("%s: stt connection dropped: %s", self.speaker, e)
        finally:
            if self._ws is ws:
                self._ws = None
            if self._final is not None and not self._final.done():
                self._final.set_exception(ConnectionError("stt connection closed"))

    async def _emit(self, seg: Segment) -> None:
        res = self.on_segment(seg)
        if asyncio.iscoroutine(res):
            await res
