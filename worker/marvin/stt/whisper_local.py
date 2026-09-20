"""Local speech-to-text: Silero VAD segments speech, faster-whisper transcribes each utterance.

One `WhisperSegmenter` per speaker (per audio track). The `WhisperModel` is shared.
Input is 16 kHz mono int16 PCM in frames of any size.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

import numpy as np
from faster_whisper import WhisperModel

from marvin.bridge.transcript import Segment

from .vad import SileroVAD, VADIterator

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
VAD_WINDOW = 512  # samples; Silero requires exactly 512 at 16 kHz


def whisper_language(language: str | None) -> str | None:
    """faster-whisper autodetects when language is None. Empty MARVIN_LANGUAGE (and 'auto') must not be passed as ''."""
    if language is None:
        return None
    value = language.strip().lower()
    if not value or value == "auto":
        return None
    return value


def load_model(size: str = "small", device: str = "cpu", compute_type: str = "int8") -> WhisperModel:
    """`small` is a good latency/accuracy point on Apple Silicon CPU; `large-v3-turbo` if you have the cores."""
    log.info("loading faster-whisper %s (%s/%s)", size, device, compute_type)
    return WhisperModel(size, device=device, compute_type=compute_type)


class WhisperSegmenter:
    def __init__(
        self,
        model: WhisperModel,
        speaker: str,
        on_segment: Callable[[Segment], Awaitable[None] | None],
        *,
        clock: Callable[[], float] = time.monotonic,
        language: str | None = None,
        vad_threshold: float = 0.5,
        min_silence_ms: int = 600,
        speech_pad_ms: int = 320,
        min_speech_ms: int = 300,
        max_utterance_s: float = 30.0,
        lock: asyncio.Lock | None = None,
        initial_prompt: str | None = "A voice room with a coding agent named Marvin.",
        hotwords: str | None = "Marvin",
    ) -> None:
        self.model = model
        self.speaker = speaker
        self.on_segment = on_segment
        self.clock = clock
        self.language = whisper_language(language)
        # Do not prompt with a bare "Marvin, Marvin.": small Whisper treats that as already-said and drops the
        # spoken name at the start of the next sentence. A full sentence + hotwords keeps the spelling.
        self.initial_prompt = initial_prompt
        self.hotwords = hotwords
        self.min_speech_samples = int(SAMPLE_RATE * min_speech_ms / 1000)
        self.max_utterance_samples = int(SAMPLE_RATE * max_utterance_s)
        self._vad = VADIterator(
            SileroVAD(),
            threshold=vad_threshold,
            sampling_rate=SAMPLE_RATE,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
        )
        self._lock = lock or asyncio.Lock()
        self._pending = np.empty(0, dtype=np.int16)  # samples not yet handed to the VAD (< 512)
        self._speech: list[np.ndarray] = []  # windows of the utterance in progress
        self._in_speech = False
        self._speech_started_at: float | None = None
        self._tasks: set[asyncio.Task] = set()

    # -- feeding ----------------------------------------------------------------
    async def push(self, pcm: np.ndarray) -> None:
        """Push int16 mono 16 kHz samples."""
        if pcm.dtype != np.int16:
            raise TypeError("expected int16 PCM")
        buf = np.concatenate([self._pending, pcm]) if self._pending.size else pcm
        n_full = (buf.size // VAD_WINDOW) * VAD_WINDOW
        for i in range(0, n_full, VAD_WINDOW):
            await self._window(buf[i : i + VAD_WINDOW])
        self._pending = buf[n_full:].copy()

    async def flush(self) -> None:
        """Force out whatever is buffered (track ended)."""
        if self._in_speech:
            await self._end_utterance()

    async def _window(self, w: np.ndarray) -> None:
        # Silero expects float32 in [-1, 1]
        ev = self._vad(w.astype(np.float32) / 32768.0)
        if ev and "start" in ev:
            self._in_speech = True
            self._speech_started_at = self.clock()
            self._speech = []
        if self._in_speech:
            self._speech.append(w)
        if ev and "end" in ev and self._in_speech:
            await self._end_utterance()
        elif self._in_speech and sum(len(x) for x in self._speech) >= self.max_utterance_samples:
            await self._end_utterance()  # very long monologue: cut and keep going

    async def _end_utterance(self) -> None:
        self._in_speech = False
        audio = np.concatenate(self._speech) if self._speech else np.empty(0, dtype=np.int16)
        self._speech = []
        started = self._speech_started_at or self.clock()
        ended = self.clock()
        if audio.size < self.min_speech_samples:
            return
        task = asyncio.create_task(self._transcribe(audio, started, ended))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # -- transcription ----------------------------------------------------------
    async def _transcribe(self, audio: np.ndarray, started: float, ended: float) -> None:
        f32 = audio.astype(np.float32) / 32768.0
        async with self._lock:  # one CTranslate2 job at a time keeps latency predictable on CPU
            text = await asyncio.to_thread(self._run_whisper, f32)
        text = text.strip()
        if not text:
            return
        seg = Segment(start=started, end=ended, speaker=self.speaker, text=text, final=True)
        log.info("stt %s: %s", self.speaker, text)
        res = self.on_segment(seg)
        if asyncio.iscoroutine(res):
            await res

    def _run_whisper(self, f32: np.ndarray) -> str:
        segments, _info = self.model.transcribe(
            f32,
            language=self.language,
            beam_size=1,
            vad_filter=False,  # we already segmented
            initial_prompt=self.initial_prompt,
            hotwords=self.hotwords,
            condition_on_previous_text=False,
        )
        return " ".join(s.text for s in segments)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


async def transcribe_utterance(
    model: WhisperModel,
    audio: np.ndarray,
    language: str | None,
    lock: asyncio.Lock,
    initial_prompt: str | None = "A voice room with a coding agent named Marvin.",
    hotwords: str | None = "Marvin",
) -> str:
    """Transcribe one int16 utterance with the local model (used as the fallback for the streaming service)."""
    f32 = audio.astype(np.float32) / 32768.0

    def run() -> str:
        segments, _ = model.transcribe(
            f32, language=whisper_language(language), beam_size=1, vad_filter=False,
            initial_prompt=initial_prompt, hotwords=hotwords, condition_on_previous_text=False,
        )
        return " ".join(s.text for s in segments).strip()

    async with lock:
        return await asyncio.to_thread(run)
