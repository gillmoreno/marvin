"""Wire protocol between the worker and the web clients. Mirrors web/src/protocol.ts."""
from __future__ import annotations

import json
from typing import Any

TOPIC_EVENTS = "marvin"  # worker -> everyone
TOPIC_CONTROL = "marvin-control"  # clients -> worker
AGENT_IDENTITY = "marvin"
MAX_PACKET = 12_000  # LiveKit reliable packets cap at 15 KiB; leave headroom


def encode(event: dict[str, Any]) -> bytes:
    return json.dumps(event, ensure_ascii=False).encode()


def decode(payload: bytes) -> dict[str, Any]:
    return json.loads(payload.decode())


def split_text_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    """A long `text` event becomes many `text_delta` events so each packet fits."""
    if event.get("kind") != "text" or len(encode(event)) <= MAX_PACKET:
        return [event]
    text = event["text"]
    step = MAX_PACKET // 2
    return [{"kind": "text_delta", "text": text[i : i + step]} for i in range(0, len(text), step)]
