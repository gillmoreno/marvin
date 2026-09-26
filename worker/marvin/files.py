"""List, read, and write text files inside a room's repo. Paths stay relative to that repo."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

MAX_TEXT = 1_000_000
MAX_IMAGE = 20_000_000
IMAGES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".svg": "image/svg+xml", ".ico": "image/x-icon",
}


def safe_path(repo: str, rel: str) -> Path:
    if not rel or os.path.isabs(rel) or ".." in rel.split("/"):
        raise ValueError("bad path")
    root = Path(repo).resolve()
    path = (root / rel).resolve()
    if path != root and root not in path.parents:
        raise ValueError("bad path")
    return path


async def list_files(repo: str) -> list[str]:
    from marvin.changes import _git

    if not os.path.isdir(os.path.join(repo, ".git")):
        return []
    tracked = await _git(repo, "ls-files")
    others = await _git(repo, "ls-files", "--others", "--exclude-standard")
    names = [p for p in (tracked + "\n" + others).splitlines() if p]
    return sorted(set(names))


def read_text(repo: str, rel: str) -> dict:
    path = safe_path(repo, rel)
    if not path.is_file():
        raise ValueError("not a file")
    raw = path.read_bytes()
    if len(raw) > MAX_TEXT:
        raise ValueError("file is too large to open here")
    if b"\0" in raw[:8000]:
        raise ValueError("not a text file")
    text = raw.decode("utf-8", errors="replace")
    return {"text": text, "sha": hashlib.sha256(text.encode()).hexdigest()}


def read_image(repo: str, rel: str) -> tuple[bytes, str]:
    path = safe_path(repo, rel)
    kind = IMAGES.get(path.suffix.lower())
    if not kind:
        raise ValueError("not an image")
    if not path.is_file():
        raise ValueError("not a file")
    raw = path.read_bytes()
    if len(raw) > MAX_IMAGE:
        raise ValueError("image is too large to open here")
    return raw, kind


def write_text(repo: str, rel: str, text: str) -> dict:
    if len(text.encode()) > MAX_TEXT:
        raise ValueError("file is too large")
    path = safe_path(repo, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"sha": hashlib.sha256(text.encode()).hexdigest()}
