"""Speech-to-text back-ends. A `SegmenterFactory` builds one segmenter per speaker track:

    seg = factory(speaker, on_segment, language=..., clock=...)
    await seg.push(int16_pcm); await seg.flush(); await seg.drain()

Two implementations: local faster-whisper (`whisper_local`, utterance at a time, CPU) and the streaming
marvin-stt service (`remote_stream`, NVIDIA Nemotron 3.5 ASR on a GPU, partials while speaking).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)


class Segmenter(Protocol):
    async def push(self, pcm: Any) -> None: ...
    async def flush(self) -> None: ...
    async def drain(self) -> None: ...


SegmenterFactory = Callable[..., Segmenter]


def make_stt(*, stt_url: str | None, whisper_model: str = "small") -> SegmenterFactory:
    if stt_url:
        from marvin.bridge.transcript import Segment

        from .remote_stream import RemoteSegmenter
        from .whisper_local import load_model, transcribe_utterance

        log.info("STT: streaming service at %s (local %s as fallback)", stt_url, whisper_model)
        state: dict[str, Any] = {"model": None}
        lock = asyncio.Lock()

        async def local_model():
            async with lock:
                if state["model"] is None:
                    log.warning("STT: loading local %s for fallback", whisper_model)
                    state["model"] = await asyncio.to_thread(load_model, whisper_model)
            return state["model"]

        def remote(speaker: str, on_segment, *, language: str | None = None, clock=None) -> Segmenter:
            kw = {"clock": clock} if clock else {}

            async def fallback(audio, started: float, ended: float) -> None:
                model = await local_model()
                text = await transcribe_utterance(model, audio, None if language in (None, "auto") else language, lock)
                if text:
                    res = on_segment(Segment(start=started, end=ended, speaker=speaker, text=text, final=True))
                    if asyncio.iscoroutine(res):
                        await res

            return RemoteSegmenter(stt_url, speaker, on_segment, language=language, fallback=fallback, **kw)

        return remote

    from .whisper_local import WhisperSegmenter, load_model

    model = load_model(whisper_model)
    lock = asyncio.Lock()

    def local(speaker: str, on_segment, *, language: str | None = None, clock=None) -> Segmenter:
        kw = {"clock": clock} if clock else {}
        return WhisperSegmenter(model, speaker, on_segment, language=language, lock=lock, **kw)

    return local
