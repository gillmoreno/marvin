"""End-to-end local STT: macOS `say` -> 16k PCM -> VAD -> faster-whisper. Skipped where `say` is missing."""
import asyncio
import shutil
import subprocess

import numpy as np
import pytest

from marvin.bridge import WakeDetector
from marvin.stt.whisper_local import SAMPLE_RATE, WhisperSegmenter, load_model

pytestmark = pytest.mark.skipif(shutil.which("say") is None or shutil.which("ffmpeg") is None, reason="needs macOS say + ffmpeg")


def synth(text: str, tmp_path) -> np.ndarray:
    aiff = tmp_path / "u.aiff"
    subprocess.run(["say", "-o", str(aiff), text], check=True)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(aiff), "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16)


@pytest.fixture(scope="module")
def model():
    return load_model("small")  # the deployed fallback model; base drops a leading name


def test_two_speakers_two_tracks(model, tmp_path):
    got: list = []

    async def run():
        clock = {"t": 0.0}
        gil = WhisperSegmenter(model, "Gil", got.append, clock=lambda: clock["t"])
        ana = WhisperSegmenter(model, "Ana", got.append, clock=lambda: clock["t"])
        silence = np.zeros(SAMPLE_RATE, dtype=np.int16)
        a = np.concatenate([synth("The retry logic is exponential with a cap", tmp_path), silence])
        b = np.concatenate([synth("Marvin, is that correct", tmp_path), silence])
        # feed both tracks in 20 ms frames, interleaved, like they'd arrive from the room
        step = SAMPLE_RATE // 50
        for i in range(0, max(a.size, b.size), step):
            clock["t"] += 0.02
            if i < a.size:
                await ana.push(a[i : i + step])
            if i < b.size:
                await gil.push(b[i : i + step])
        await ana.flush(); await gil.flush()
        await ana.drain(); await gil.drain()

    asyncio.run(run())
    by_speaker = {s.speaker: s.text.lower() for s in got}
    assert "retry" in by_speaker["Ana"] or "exponential" in by_speaker["Ana"], got
    assert WakeDetector().detect(by_speaker["Gil"]) is not None, got
    assert all(s.end > s.start for s in got)
