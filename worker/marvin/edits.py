"""A short log of who last changed a file: a person in the editor, or Marvin."""
from __future__ import annotations

import json
import time
from pathlib import Path

_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _file(state_dir: Path, room: str) -> Path:
    return state_dir / f"edits-{room}.jsonl"


def record(state_dir: Path | None, room: str, *, path: str, by: str, source: str) -> None:
    if not state_dir or not path:
        return
    state_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"path": path, "by": by, "source": source, "at": time.time()}, ensure_ascii=False)
    with _file(state_dir, room).open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def record_tool(state_dir: Path | None, room: str, event: dict, agent_name: str) -> None:
    if event.get("kind") != "tool_use" or event.get("tool") not in _TOOLS:
        return
    raw = event.get("input") or {}
    path = raw.get("file_path") or raw.get("path") or raw.get("notebook_path") or ""
    record(state_dir, room, path=str(path), by=agent_name, source="agent")


def recent(state_dir: Path | None, room: str, limit: int = 40) -> list[dict]:
    if not state_dir:
        return []
    path = _file(state_dir, room)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
