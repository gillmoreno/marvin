"""Reference client + benchmark: stream a WAV (or macOS `say` text) at real-time pace and print partials.

  python -m marvin_stt.client ws://localhost:8765/v1/stream --wav utterance.wav --lang it-IT
  python -m marvin_stt.client ws://localhost:8765/v1/stream --say "Marvin, what does the retry logic do?"
  python -m marvin_stt.client ... --fast      # no pacing: measures pure throughput

Prints each partial with the wall-clock offset from the first audio frame, then the final with its latency
after the last frame (the number that matters for the room).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

import aiohttp
import numpy as np

SAMPLE_RATE = 16_000


def load_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SAMPLE_RATE, "need 16 kHz mono int16 wav"
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def synth(text: str, voice: str | None = None) -> np.ndarray:
    aiff = Path("/tmp/marvin_stt_say.aiff")
    subprocess.run(["say", *(["-v", voice] if voice else []), "-o", str(aiff), text], check=True)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(aiff), "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"], check=True, capture_output=True
    ).stdout
    return np.frombuffer(raw, dtype=np.int16)


async def run(url: str, pcm: np.ndarray, lang: str, *, frame_ms: int = 20, fast: bool = False, repeat: int = 1) -> dict:
    step = SAMPLE_RATE * frame_ms // 1000
    out: dict = {"partials": [], "final": None}
    async with aiohttp.ClientSession() as sess, sess.ws_connect(url, max_msg_size=0) as ws:
        await ws.send_json({"op": "start", "lang": lang})
        ready = await ws.receive_json()
        print("ready:", ready)

        async def reader():
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                ev = json.loads(msg.data)
                if ev["type"] == "partial":
                    out["partials"].append((time.monotonic() - t0, ev["text"]))
                    print(f"  {time.monotonic() - t0:6.2f}s  {ev['text']}")
                elif ev["type"] == "final":
                    out["final"] = (time.monotonic() - t0, ev)
                    print(f"FINAL {time.monotonic() - t_end:.2f}s after last frame [{ev.get('lang')}]: {ev['text']}")
                    if ev["utterance"] >= repeat:
                        return
                elif ev["type"] == "error":
                    print("error:", ev["message"], file=sys.stderr)
                    return

        rd = asyncio.create_task(reader())
        for _ in range(repeat):
            t0 = time.monotonic()
            for i in range(0, pcm.size, step):
                await ws.send_bytes(pcm[i : i + step].tobytes())
                if not fast:
                    target = t0 + (i + step) / SAMPLE_RATE
                    await asyncio.sleep(max(0.0, target - time.monotonic()))
            t_end = time.monotonic()
            await ws.send_json({"op": "end"})
        await asyncio.wait_for(rd, timeout=60)
        await ws.send_json({"op": "close"})
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--wav")
    p.add_argument("--say")
    p.add_argument("--voice")
    p.add_argument("--lang", default="auto")
    p.add_argument("--fast", action="store_true")
    p.add_argument("--repeat", type=int, default=1)
    a = p.parse_args()
    pcm = load_wav(a.wav) if a.wav else synth(a.say or "Marvin, is the retry logic exponential with a cap?", a.voice)
    print(f"audio: {pcm.size / SAMPLE_RATE:.2f}s")
    asyncio.run(run(a.url, pcm, a.lang, fast=a.fast, repeat=a.repeat))


if __name__ == "__main__":
    main()
