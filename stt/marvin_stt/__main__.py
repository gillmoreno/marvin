"""python -m marvin_stt  — serve Nemotron 3.5 ASR streaming over WebSocket."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from .engine import CHUNK_MS_TO_RIGHT_CONTEXT, MODEL_NAME, Engine
from .server import serve


def main() -> None:
    p = argparse.ArgumentParser(description="Marvin streaming STT (NVIDIA Nemotron 3.5 ASR via NeMo)")
    p.add_argument("--host", default=os.environ.get("MARVIN_STT_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("MARVIN_STT_PORT", "8765")))
    p.add_argument("--model", default=os.environ.get("MARVIN_STT_MODEL", MODEL_NAME), help="HF name or path to a .nemo file")
    p.add_argument("--device", default=os.environ.get("MARVIN_STT_DEVICE"), help="cuda | cpu | mps (default: cuda if available)")
    p.add_argument("--precision", default=os.environ.get("MARVIN_STT_PRECISION", "auto"), choices=["auto", "fp32", "fp16", "bf16"])
    p.add_argument("--chunk-ms", type=int, default=int(os.environ.get("MARVIN_STT_CHUNK_MS", "320")), choices=sorted(CHUNK_MS_TO_RIGHT_CONTEXT))
    p.add_argument("--lang", default=os.environ.get("MARVIN_STT_LANG", "auto"), help="default language prompt when the client sends none")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("nemo_logger").setLevel(logging.WARNING)

    engine = Engine(args.model, device=args.device, precision=args.precision, chunk_ms=args.chunk_ms, default_lang=args.lang)
    try:
        asyncio.run(serve(engine, host=args.host, port=args.port, load=engine.load))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
