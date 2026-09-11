"""Silero VAD v5 on onnxruntime, no torch. Streaming logic vendored from the silero-vad package (MIT)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort

MODEL_PATH = Path(__file__).with_name("silero_vad.onnx")
CONTEXT = 64  # samples of the previous window the v5 model wants prepended at 16 kHz


class SileroVAD:
    def __init__(self, path: Path = MODEL_PATH) -> None:
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"], sess_options=opts)
        self.reset_states()

    def reset_states(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT), dtype=np.float32)

    def __call__(self, x: np.ndarray, sr: int = 16000) -> float:
        """Speech probability for one 512-sample float32 window."""
        x = np.asarray(x, dtype=np.float32).reshape(1, -1)
        if x.shape[1] != 512:
            raise ValueError(f"expected 512 samples, got {x.shape[1]}")
        inp = np.concatenate([self._context, x], axis=1)
        out, state = self.session.run(None, {"input": inp, "state": self._state, "sr": np.array(sr, dtype=np.int64)})
        self._state = state
        self._context = inp[:, -CONTEXT:]
        return float(out[0][0])


class VADIterator:
    """Emits {'start': sample} when speech begins and {'end': sample} after min_silence of non-speech."""

    def __init__(self, model: SileroVAD, threshold: float = 0.5, sampling_rate: int = 16000, min_silence_duration_ms: int = 100, speech_pad_ms: int = 30) -> None:
        self.model = model
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        self.min_silence_samples = sampling_rate * min_silence_duration_ms / 1000
        self.speech_pad_samples = sampling_rate * speech_pad_ms / 1000
        self.reset_states()

    def reset_states(self) -> None:
        self.model.reset_states()
        self.triggered = False
        self.temp_end = 0
        self.current_sample = 0

    def __call__(self, x: np.ndarray) -> dict | None:
        window = len(x)
        self.current_sample += window
        p = self.model(x, self.sampling_rate)
        if p >= self.threshold and self.temp_end:
            self.temp_end = 0
        if p >= self.threshold and not self.triggered:
            self.triggered = True
            return {"start": int(max(0, self.current_sample - self.speech_pad_samples - window))}
        if p < self.threshold - 0.15 and self.triggered:
            if not self.temp_end:
                self.temp_end = self.current_sample
            if self.current_sample - self.temp_end < self.min_silence_samples:
                return None
            end = self.temp_end + self.speech_pad_samples - window
            self.temp_end = 0
            self.triggered = False
            return {"end": int(end)}
        return None
