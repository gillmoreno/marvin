"""When the streaming STT service is unreachable, the utterance goes to the fallback instead of being dropped."""
import asyncio
import shutil
import subprocess

import numpy as np
import pytest

from marvin.stt.remote_stream import SAMPLE_RATE, RemoteSegmenter

pytestmark = pytest.mark.skipif(shutil.which("say") is None or shutil.which("ffmpeg") is None, reason="needs macOS say + ffmpeg")


def synth(text, tmp_path):
    aiff = tmp_path / "u.aiff"
    subprocess.run(["say", "-o", str(aiff), text], check=True)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(aiff), "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16)


def test_unreachable_service_uses_fallback(tmp_path):
    got = []

    async def fallback(audio, started, ended):
        got.append((audio.size, started, ended))

    async def run():
        clock = {"t": 0.0}
        seg = RemoteSegmenter("ws://127.0.0.1:9/v1/stream", "Gil", lambda s: None, clock=lambda: clock["t"], fallback=fallback)
        audio = np.concatenate([synth("Marvin, is that correct", tmp_path), np.zeros(SAMPLE_RATE, dtype=np.int16)])
        step = SAMPLE_RATE // 50
        for i in range(0, audio.size, step):
            clock["t"] += 0.02
            await seg.push(audio[i : i + step])
        await seg.flush()
        await seg.drain()
        await seg.close()

    asyncio.run(run())
    assert len(got) == 1 and got[0][0] > SAMPLE_RATE // 2 and got[0][2] > got[0][1]
