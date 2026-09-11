"""Real model, real chunking: stream macOS `say` audio through the Engine and compare with NeMo's offline transcribe.

Slow (downloads ~2.4 GB once, runs the 0.6B model on CPU/GPU). Opt in with MARVIN_STT_REAL=1.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import numpy as np
import pytest

from marvin_stt.engine import SAMPLE_RATE, Engine

pytestmark = pytest.mark.skipif(
    os.environ.get("MARVIN_STT_REAL") != "1" or shutil.which("say") is None or shutil.which("ffmpeg") is None,
    reason="set MARVIN_STT_REAL=1 on a Mac with say+ffmpeg (or a GPU box with a wav) to run",
)


def synth(text: str, path) -> np.ndarray:
    aiff = path / "u.aiff"
    subprocess.run(["say", "-o", str(aiff), text], check=True)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(aiff), "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"], check=True, capture_output=True
    ).stdout
    return np.frombuffer(raw, dtype=np.int16)


@pytest.fixture(scope="module")
def engine():
    e = Engine(chunk_ms=int(os.environ.get("MARVIN_STT_CHUNK_MS", "320")), precision=os.environ.get("MARVIN_STT_PRECISION", "auto"))
    e.load()
    return e


def words(s: str) -> set[str]:
    return {w.strip(".,?!;:").lower() for w in s.split()}


async def test_streaming_matches_offline(engine, tmp_path):
    text = "Marvin, is the retry logic exponential with a cap?"
    pcm = synth(text, tmp_path)
    st = engine.new_stream("en-US")
    partials = []
    step = SAMPLE_RATE // 50  # 20 ms frames like the room
    for i in range(0, pcm.size, step):
        t = await st.feed(pcm[i : i + step])
        if t is not None:
            partials.append(t)
    final = await st.finish()
    print("\npartials:", partials, "\nfinal:", final)

    offline = engine.model.transcribe([pcm.astype(np.float32) / 32768.0], batch_size=1, verbose=False)
    offline_text = offline[0].text if hasattr(offline[0], "text") else offline[0]
    print("offline:", offline_text)

    assert partials, "no partial transcripts came out while streaming"
    assert len(partials) >= 3, partials
    got = words(final)
    assert {"retry", "exponential", "cap"} & got, final
    # streaming and offline should agree on nearly all words (both are the same model; only right context differs)
    assert len(words(offline_text) & got) >= max(1, int(0.7 * len(words(offline_text)))), (final, offline_text)


async def test_auto_language_tag_and_reset(engine, tmp_path):
    pcm = synth("The deployment finished and the pod is healthy.", tmp_path)
    st = engine.new_stream("auto")
    await st.feed(pcm)
    final = await st.finish()
    print("\nauto:", final, st.detected_lang)
    assert "<" not in final and ">" not in final
    assert st.detected_lang is None or st.detected_lang.startswith("en")
    # a finished stream keeps its text, a new one starts clean
    st2 = engine.new_stream("en")
    assert st2.text == "" and st2.step == 0
