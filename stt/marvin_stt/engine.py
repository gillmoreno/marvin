"""Cache-aware streaming ASR on NVIDIA Nemotron 3.5 (FastConformer-RNNT) through NeMo.

One `Engine` per process: one model on one device, one worker thread so GPU steps never interleave
(the language prompt is model-global state, so steps of different streams must not overlap anyway).

One `Stream` per utterance in progress: holds the encoder cache, the RNNT partial hypothesis, and the raw
audio of the utterance. `feed()` takes 16 kHz mono PCM of any size and returns the latest partial text
whenever a full chunk was processed; `finish()` pads the right context, flushes, and returns the final text.

The chunking reproduces `CacheAwareStreamingAudioBuffer.__iter__` (nemo/collections/asr/parts/utils/streaming_utils.py)
on a live signal: mel features are recomputed over the growing utterance and only frames whose STFT window
lies fully inside the received audio are handed to the encoder, so they equal the offline features exactly.
"""
from __future__ import annotations

import functools
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

MODEL_NAME = "nvidia/nemotron-3.5-asr-streaming-0.6b"
SAMPLE_RATE = 16_000
LANG_TAG_RE = re.compile(r"\s*<([a-z]{2}-[A-Z]{2})>")

# Right-context (in 80 ms encoder frames) for each supported chunk duration, from the model card.
CHUNK_MS_TO_RIGHT_CONTEXT = {80: 0, 160: 1, 320: 3, 560: 6, 1120: 13}
LEFT_CONTEXT = 56


def _pair(v) -> tuple[int, int]:
    """streaming_cfg fields are [first_chunk, later_chunks] lists for models with a two-stage subsampling, else scalars."""
    if isinstance(v, (list, tuple)):
        return int(v[0]), int(v[1])
    return int(v), int(v)


@dataclass
class StreamingGeometry:
    """Frame counts (mel frames, 10 ms each) that drive the live chunker. Derived from encoder.streaming_cfg."""

    chunk: tuple[int, int]  # frames fed per step (first step, later steps)
    shift: tuple[int, int]  # frames the read pointer advances per step
    pre_encode_cache: tuple[int, int]  # frames re-fed before the chunk (zeros on the first step)
    sampling_frames: tuple[int, int]  # minimum frames for the subsampling to yield one output
    drop_extra_pre_encoded: int
    hop: int = 160
    n_fft: int = 512

    def exact_frames(self, n_samples: int) -> int:
        """How many leading mel frames are final given `n_samples` (center=True STFT, reflect pad n_fft//2)."""
        if n_samples < self.n_fft:
            return 0
        return (n_samples - self.n_fft // 2) // self.hop + 1


class Engine:
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        *,
        device: str | None = None,
        precision: str = "auto",
        chunk_ms: int = 320,
        default_lang: str = "auto",
    ) -> None:
        import torch

        self.torch = torch
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        if precision == "auto":
            precision = "fp16" if self.device.startswith("cuda") else "fp32"
        self.precision = precision
        self.chunk_ms = chunk_ms
        self.default_lang = default_lang
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="asr")
        self._lock = threading.Lock()
        self.model: Any = None
        self.geometry: StreamingGeometry | None = None
        self.preprocessor: Any = None
        self.langs: list[str] = []
        self._normalize: str | None = None

    # -- setup ----------------------------------------------------------------------
    def load(self) -> None:
        """Blocking. Downloads the checkpoint to HF_HOME on first use."""
        import nemo.collections.asr as nemo_asr
        import torch
        from omegaconf import OmegaConf, open_dict

        t0 = time.monotonic()
        if os.path.exists(self.model_name_or_path):
            model = nemo_asr.models.ASRModel.restore_from(self.model_name_or_path, map_location=self.device)
        else:
            model = nemo_asr.models.ASRModel.from_pretrained(model_name=self.model_name_or_path, map_location=self.device)
        model.eval()
        model.to(self.device)

        right = CHUNK_MS_TO_RIGHT_CONTEXT[self.chunk_ms]
        model.encoder.set_default_att_context_size([LEFT_CONTEXT, right])

        # Greedy batched RNNT decoding with partial-hypothesis carry-over between steps (what the NeMo streaming example uses).
        dec = OmegaConf.create(OmegaConf.to_container(model.cfg.decoding, resolve=True))
        with open_dict(dec):
            dec.strategy = "greedy_batch"
            dec.fused_batch_size = -1
            if os.environ.get("MARVIN_STT_NO_CUDA_GRAPHS"):
                dec.greedy.use_cuda_graph_decoder = False
        model.change_decoding_strategy(dec)
        model.decoding.set_strip_lang_tags(False)  # we parse the tag ourselves to report the detected language

        # Same preprocessor the streaming buffer builds: no dither, no padding to multiples of 16 frames.
        pcfg = OmegaConf.create(OmegaConf.to_container(model.cfg.preprocessor, resolve=True))
        self._normalize = str(pcfg.get("normalize", "NA"))
        with open_dict(pcfg):
            pcfg.dither = 0.0
            pcfg.pad_to = 0
            if self._normalize not in ("NA", "None", "none"):
                pcfg.normalize = "None"  # normalize per chunk instead (online normalization), see _features()
        self.preprocessor = model.from_config_dict(pcfg).to(self.device).eval()

        scfg = model.encoder.streaming_cfg
        pre = model.encoder.pre_encode
        sampling = pre.get_sampling_frames() if hasattr(pre, "get_sampling_frames") else 1
        self.geometry = StreamingGeometry(
            chunk=_pair(scfg.chunk_size),
            shift=_pair(scfg.shift_size),
            pre_encode_cache=_pair(scfg.pre_encode_cache_size),
            sampling_frames=_pair(sampling),
            drop_extra_pre_encoded=int(scfg.drop_extra_pre_encoded),
            hop=round(float(pcfg.get("window_stride", 0.01)) * int(pcfg.get("sample_rate", SAMPLE_RATE))),
            n_fft=int(pcfg.get("n_fft") or 512),
        )
        self._prompt_index = dict(model.cfg.model_defaults.get("prompt_dictionary", {}))
        self.langs = sorted(self._prompt_index)
        self._current_prompt: str | None = None
        self.model = model
        log.info(
            "loaded %s on %s (%s), chunk %d ms, geometry %s, normalize=%s, %d prompt languages, %.1fs",
            self.model_name_or_path, self.device, self.precision, self.chunk_ms, self.geometry, self._normalize, len(self.langs), time.monotonic() - t0,
        )

    @property
    def model_name_or_path(self) -> str:
        return os.environ.get("MARVIN_STT_MODEL") or self.model_name

    def resolve_lang(self, lang: str | None) -> str:
        lang = (lang or self.default_lang or "auto").strip()
        if lang in self.langs:
            return lang
        # "it" -> "it-IT" style fallback when the dictionary only has the locale form
        for cand in self.langs:
            if cand.lower().startswith(lang.lower()):
                return cand
        raise ValueError(f"unsupported language {lang!r}; known: {self.langs[:20]}...")

    def new_stream(self, lang: str | None = None) -> "Stream":
        if self.model is None:
            raise RuntimeError("engine not loaded")
        return Stream(self, self.resolve_lang(lang))

    # -- inference primitives (worker thread only) ----------------------------------------
    def _autocast(self):
        torch = self.torch
        if self.precision == "fp16":
            return torch.autocast(device_type="cuda" if self.device.startswith("cuda") else "cpu", dtype=torch.float16)
        if self.precision == "bf16":
            return torch.autocast(device_type="cuda" if self.device.startswith("cuda") else "cpu", dtype=torch.bfloat16)
        return torch.autocast(device_type="cuda", enabled=False) if self.device.startswith("cuda") else _nullcontext()

    def _features(self, audio: np.ndarray):
        """Mel features (1, D, T) for the whole utterance so far."""
        torch = self.torch
        sig = torch.from_numpy(audio).unsqueeze(0).to(self.device)
        length = torch.tensor([audio.shape[0]], device=self.device)
        with torch.inference_mode():
            feats, _ = self.preprocessor(input_signal=sig, length=length)
        return feats

    def _normalize_chunk(self, x):
        if self._normalize in ("NA", "None", "none"):
            return x
        from nemo.collections.asr.parts.preprocessing.features import normalize_batch

        seq_len = self.torch.tensor([x.size(-1)] * x.size(0), device=x.device)
        x, _, _ = normalize_batch(x=x, seq_len=seq_len, normalize_type=self._normalize)
        return x

    def _step(self, st: "Stream", chunk, length: int, *, last: bool):
        torch = self.torch
        m = self.model
        with self._lock, torch.inference_mode(), self._autocast():
            if st.lang != self._current_prompt:  # model-global; cheap int, but avoid NeMo's per-call info log
                m._inference_prompt_index = self._prompt_index[st.lang]
                self._current_prompt = st.lang
            if st.cache is None:
                st.cache = m.encoder.get_initial_cache_state(batch_size=1)
            c_channel, c_time, c_len = st.cache
            (_, hyps, c_channel, c_time, c_len, _) = m.conformer_stream_step(
                processed_signal=chunk,
                processed_signal_length=torch.tensor([length], device=chunk.device),
                cache_last_channel=c_channel,
                cache_last_time=c_time,
                cache_last_channel_len=c_len,
                keep_all_outputs=last,
                previous_hypotheses=st.hyps,
                previous_pred_out=None,
                drop_extra_pre_encoded=0 if st.step == 0 else self.geometry.drop_extra_pre_encoded,
                return_transcription=True,
            )
        st.cache = (c_channel, c_time, c_len)
        st.hyps = hyps
        st.step += 1
        h = hyps[0]
        return h.text if hasattr(h, "text") else str(h)

    def _advance(self, st: "Stream", *, finishing: bool) -> str | None:
        """Run every step the buffered audio allows. Returns the latest text if at least one step ran."""
        g = self.geometry
        audio = st.audio_array()
        n_exact = g.exact_frames(audio.shape[0])
        text = None
        feats = None
        while True:
            first = st.step == 0
            chunk_n = g.chunk[0] if first else g.chunk[1]
            shift_n = g.shift[0] if first else g.shift[1]
            avail = n_exact - st.pos
            if avail <= 0:
                break
            if avail < chunk_n and not finishing:
                break
            min_frames = g.sampling_frames[0] if first else g.sampling_frames[1]
            if avail < min_frames:
                break
            if feats is None:
                feats = self._features(audio)[:, :, :n_exact]
            take = min(chunk_n, avail)
            body = feats[:, :, st.pos : st.pos + take]
            if first:
                pre_n = g.pre_encode_cache[0]
                pre = self.torch.zeros((1, body.size(1), pre_n), device=body.device, dtype=body.dtype)
            else:
                pre_n = g.pre_encode_cache[1]
                start = max(0, st.pos - pre_n)
                pre = feats[:, :, start : st.pos]
                if pre.size(-1) < pre_n:
                    pad = self.torch.zeros((1, body.size(1), pre_n - pre.size(-1)), device=body.device, dtype=body.dtype)
                    pre = self.torch.cat((pad, pre), dim=-1)
            x = self._normalize_chunk(self.torch.cat((pre, body), dim=-1))
            last = finishing and (st.pos + take >= n_exact or avail - shift_n < min_frames)
            text = self._step(st, x, x.size(-1), last=last)
            st.pos += shift_n
            if last:
                break
        return text

    # -- public async API ----------------------------------------------------------------
    async def advance(self, st: "Stream", *, finishing: bool = False) -> str | None:
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, functools.partial(self._advance, st, finishing=finishing))

    def close(self) -> None:
        self._executor.shutdown(wait=False)


class _nullcontext:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


@dataclass
class Stream:
    engine: Engine
    lang: str
    chunks: list[np.ndarray] = field(default_factory=list)
    n_samples: int = 0
    pos: int = 0  # mel frames already consumed by the encoder (the buffer_idx of the NeMo streaming buffer)
    step: int = 0
    cache: Any = None
    hyps: Any = None
    text: str = ""
    detected_lang: str | None = None
    finished: bool = False

    def audio_array(self) -> np.ndarray:
        if len(self.chunks) > 1:
            self.chunks = [np.concatenate(self.chunks)]
        return self.chunks[0] if self.chunks else np.empty(0, dtype=np.float32)

    def _accept(self, pcm: np.ndarray) -> np.ndarray:
        if pcm.dtype == np.int16:
            pcm = pcm.astype(np.float32) / 32768.0
        elif pcm.dtype != np.float32:
            pcm = pcm.astype(np.float32)
        return pcm

    def ready_for_step(self) -> bool:
        """Cheap check the server uses to avoid a thread hop when no full chunk is available yet."""
        g = self.engine.geometry
        chunk_n = g.chunk[0] if self.step == 0 else g.chunk[1]
        return g.exact_frames(self.n_samples) - self.pos >= chunk_n

    async def feed(self, pcm: np.ndarray) -> str | None:
        """Append audio; returns the new partial text when at least one chunk was processed."""
        if self.finished:
            raise RuntimeError("stream already finished")
        pcm = self._accept(pcm)
        if pcm.size:
            self.chunks.append(pcm)
            self.n_samples += pcm.size
        if not self.ready_for_step():
            return None
        text = await self.engine.advance(self)
        if text is not None:
            self._set_text(text)
            return self.text
        return None

    async def finish(self) -> str:
        """Flush: pad right context with silence, run the remaining steps, return the final text."""
        if self.finished:
            return self.text
        self.finished = True
        g = self.engine.geometry
        pad_frames = g.chunk[1] + g.shift[1] + g.pre_encode_cache[1]
        pad = np.zeros(pad_frames * g.hop + g.n_fft, dtype=np.float32)
        self.chunks.append(pad)
        self.n_samples += pad.size
        if self.n_samples >= g.n_fft:
            text = await self.engine.advance(self, finishing=True)
            if text is not None:
                self._set_text(text)
        self.cache = None
        self.hyps = None
        self.chunks = []
        return self.text

    def _set_text(self, raw: str) -> None:
        tags = LANG_TAG_RE.findall(raw)
        if tags:
            self.detected_lang = tags[-1]
        self.text = LANG_TAG_RE.sub("", raw).strip()
