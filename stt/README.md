# marvin-stt: streaming speech-to-text

NVIDIA **Nemotron 3.5 ASR streaming 0.6B** (cache-aware FastConformer-RNNT, 40 languages, 80 ms to 1.12 s chunks)
served over WebSocket through NVIDIA NeMo (`nemo-toolkit 3.0.0`). The Marvin worker streams each speaker's audio here
while they talk and gets partial transcripts every chunk plus a final one when the speaker stops.

```
worker (CPU pod)                          marvin-stt (GPU pod, T4/L4)
  LiveKit track ─ Silero VAD ─┐            ┌─ mel features of the utterance so far
                 speech only ─┼─ ws ──────►│  cache-aware encoder step per 320 ms chunk
                              │◄── partial ┤  RNNT greedy decode with carried hypothesis
       VAD end ─ {"op":"end"} ┼─ ws ──────►│  pad right context, flush
                              │◄── final ──┘
```

## Protocol (`/v1/stream`)

| direction | message |
|---|---|
| → | `{"op":"start","lang":"it-IT" \| "en" \| "auto"}` once per connection |
| → | binary int16 LE mono 16 kHz PCM, any frame size |
| → | `{"op":"end"}` end of utterance |
| ← | `{"type":"ready","chunk_ms":320,"lang":"it-IT"}` |
| ← | `{"type":"partial","text":"..."}` |
| ← | `{"type":"final","text":"...","lang":"it-IT"\|null,"utterance":n}` |

`GET /healthz` is 503 while the model loads, 200 after. In `auto` mode the model appends a language tag that the
server strips and reports as `lang`.

## Run

```
make stt-local                       # CPU/MPS on this machine, functional but slow
make stt-bench URL=ws://...:8765/v1/stream   # streams a `say` sentence at real-time pace, prints partial + final latency
MARVIN_STT_REAL=1 uv run --no-sync pytest -s tests/test_engine_real.py   # real model vs offline transcribe
```

Options (flags or env): `--chunk-ms {80,160,320,560,1120}` (`MARVIN_STT_CHUNK_MS`), `--precision fp16|bf16|fp32`
(T4: fp16), `--lang` default prompt, `--model` HF name or `.nemo` path, `MARVIN_STT_NO_CUDA_GRAPHS=1` if the RNNT
CUDA-graph decoder misbehaves on a given driver.

## Deploy

`deploy/k8s/stt.yaml`: one-replica Deployment requesting `nvidia.com/gpu: 1` (a T4 or L4 is enough), a 10 Gi PVC
for the HuggingFace cache, `Service marvin-stt:8765`. The worker gets `MARVIN_STT_URL=ws://marvin-stt:8765/v1/stream`;
unset it to fall back to local faster-whisper. This service is optional: Marvin runs fine on CPU Whisper alone.

```
make stt-image        # build for amd64 and push ghcr.io/<owner>/marvin-stt:<tag> + :latest (REGISTRY=... to override)
make stt-off / stt-on # scale to 0 outside working hours; a cluster autoscaler then removes / recreates the GPU node
```

## How the live chunking works

NeMo's `CacheAwareStreamingAudioBuffer` chunks a *complete* file. Here the audio grows, so `engine.py` recomputes
mel features over the utterance so far and only hands the encoder frames whose STFT window lies fully inside the
received audio (`StreamingGeometry.exact_frames`). Chunk / shift / pre-encode-cache sizes are read from
`encoder.streaming_cfg`, so the frames fed per step are identical to NeMo's own streaming example. `finish()`
appends one chunk of silence so the right context of the last spoken frames is complete, then runs the last step
with `keep_all_outputs=True`.
