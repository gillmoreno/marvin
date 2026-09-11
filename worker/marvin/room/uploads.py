"""Images dropped into the room: chunked control messages in, one file on disk out.

LiveKit data packets are small, so a client splits a base64 image across many `image` control
messages sharing one id. We reassemble them here and hand the harness a path it can Read.
"""
from __future__ import annotations

import base64
import binascii
import logging
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 8_000_000
CHUNK_TIMEOUT_S = 60.0  # a client that dropped off mid-upload stops holding memory
SUFFIXES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


@dataclass(frozen=True)
class Attachment:
    path: Path
    name: str
    sender: str


@dataclass
class _Pending:
    total: int
    mime: str
    name: str
    sender: str
    started: float
    chunks: dict[int, str] = field(default_factory=dict)


class ImageInbox:
    def __init__(self, directory: str | Path | None = None, *, max_bytes: int = MAX_IMAGE_BYTES) -> None:
        self.dir = Path(directory) if directory else Path(tempfile.gettempdir()) / "marvin-uploads"
        self.max_bytes = max_bytes
        self._pending: dict[str, _Pending] = {}

    def add(self, sender: str, msg: dict[str, Any]) -> Attachment | None:
        """Absorb one chunk; returns the Attachment once the last chunk of an upload lands."""
        try:
            upload_id = _slug(str(msg["id"]))
            seq, total = int(msg["seq"]), int(msg["total"])
            data = str(msg["data"])
        except (KeyError, TypeError, ValueError):
            log.warning("bad image chunk from %s", sender)
            return None
        if not upload_id or total <= 0 or not 0 <= seq < total:
            log.warning("out-of-range image chunk %s/%s from %s", seq, total, sender)
            return None

        self._expire()
        p = self._pending.get(upload_id)
        if p is None:
            p = _Pending(total=total, mime=str(msg.get("mime") or ""), name=str(msg.get("name") or "image"), sender=sender, started=time.monotonic())
            self._pending[upload_id] = p
        p.chunks[seq] = data
        if sum(len(c) for c in p.chunks.values()) > self.max_bytes * 4 // 3 + 4096:  # base64 inflates by 4/3
            del self._pending[upload_id]
            log.warning("image from %s exceeds %d bytes, dropped", sender, self.max_bytes)
            return None
        if len(p.chunks) < p.total:
            return None

        del self._pending[upload_id]
        try:
            raw = base64.b64decode("".join(p.chunks[i] for i in range(p.total)), validate=True)
        except (KeyError, binascii.Error):
            log.warning("image from %s failed to decode", sender)
            return None

        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{upload_id[:12]}{_suffix(p.mime, p.name)}"
        path.write_bytes(raw)
        log.info("%s attached %s (%d bytes) -> %s", p.sender, p.name, len(raw), path)
        return Attachment(path=path, name=p.name, sender=p.sender)

    def _expire(self) -> None:
        now = time.monotonic()
        for key in [k for k, p in self._pending.items() if now - p.started > CHUNK_TIMEOUT_S]:
            log.warning("incomplete image upload %s timed out", key)
            del self._pending[key]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "", s)[:64]


def _suffix(mime: str, name: str) -> str:
    if mime in SUFFIXES:
        return SUFFIXES[mime]
    ext = Path(_slug(name)).suffix.lower()
    return ext if ext in SUFFIXES.values() else ".png"
