"""Append-only meeting log. A session starts when a room goes occupied and ends after it is empty.

Each JSONL line hashes the previous. The head is HMAC-signed at close. Worker logs carry session/turn/actor.
Docs: ee-company-pilot.md, security-and-compliance.md §7.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("marvin.audit")

GENESIS = "0" * 64
IDLE_SECONDS = 180
RETENTION_DAYS_DEFAULT = 90


def _canon(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class Meeting:
    id: str
    room: str
    started_at: float
    ended_at: float | None = None
    participants: dict[str, dict[str, Any]] = field(default_factory=dict)
    turn: int = 0
    prev: str = GENESIS
    path: Path | None = None


class Audit:
    """One JSONL per meeting under ``<state_dir>/audit/<room>/<id>.jsonl``."""

    def __init__(
        self,
        state_dir: str | None,
        secret: str,
        *,
        now: Callable[[], float] | None = None,
        idle_seconds: float = IDLE_SECONDS,
        on_close: Callable[[Meeting, Path], Any] | None = None,
    ) -> None:
        self.root = Path(state_dir) / "audit" if state_dir else None
        self.secret = (secret or "dev").encode()
        self._now = now or time.time
        self.idle_seconds = idle_seconds
        self.on_close = on_close
        self._open: dict[str, Meeting] = {}
        self._empty_since: dict[str, float] = {}
        self.retention_days = RETENTION_DAYS_DEFAULT
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            self._load_retention()

    def _load_retention(self) -> None:
        p = self.root / "retention.json" if self.root else None
        if p and p.exists():
            try:
                self.retention_days = int(json.loads(p.read_text()).get("days") or RETENTION_DAYS_DEFAULT)
            except Exception:
                pass

    def set_retention(self, days: int) -> int:
        self.retention_days = max(1, min(int(days), 3650))
        if self.root:
            (self.root / "retention.json").write_text(json.dumps({"days": self.retention_days}))
        return self.retention_days

    def current(self, room: str) -> Meeting | None:
        return self._open.get(room)

    def ensure(self, room: str, **meta: Any) -> Meeting:
        m = self._open.get(room)
        if m:
            return m
        sid = uuid.uuid4().hex
        path = self.root / room / f"{sid}.jsonl" if self.root else None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
        m = Meeting(id=sid, room=room, started_at=self._now(), path=path)
        self._open[room] = m
        self.append(room, "session_start", "marvin", {"room": room, **meta}, meeting=m)
        log.info("audit session=%s room=%s actor=marvin verb=session_start", sid, room)
        return m

    def append(
        self,
        room: str,
        verb: str,
        actor: str,
        payload: dict[str, Any] | None = None,
        *,
        turn: int | None = None,
        meeting: Meeting | None = None,
    ) -> dict[str, Any] | None:
        m = meeting or self._open.get(room)
        if not m:
            return None
        if verb == "turn":
            m.turn += 1
            turn = m.turn
        rec = {
            "ts": self._now(),
            "session": m.id,
            "room": room,
            "verb": verb,
            "actor": actor,
            "turn": turn if turn is not None else (m.turn or None),
            "payload": _small(payload or {}),
        }
        rec["prev"] = m.prev
        rec["hash"] = hashlib.sha256(m.prev.encode() + _canon({k: rec[k] for k in rec if k != "hash"})).hexdigest()
        m.prev = rec["hash"]
        if m.path:
            with m.path.open("a") as f:
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        log.info("audit session=%s room=%s turn=%s actor=%s verb=%s", m.id, room, rec["turn"], actor, verb)
        return rec

    def join(self, room: str, actor: str, **info: Any) -> Meeting:
        m = self.ensure(room)
        m.participants[actor] = {"id": actor, "joined_at": self._now(), **info, "left_at": None}
        self._empty_since.pop(room, None)
        self.append(room, "join", actor, info)
        return m

    def leave(self, room: str, actor: str) -> None:
        m = self._open.get(room)
        if not m:
            return
        if actor in m.participants:
            m.participants[actor]["left_at"] = self._now()
        self.append(room, "leave", actor, {})
        present = [p for p, inf in m.participants.items() if not inf.get("left_at")]
        if not present:
            self._empty_since[room] = self._now()

    def close_if_idle(self) -> list[str]:
        closed = []
        now = self._now()
        for room, since in list(self._empty_since.items()):
            if now - since >= self.idle_seconds:
                self.close(room)
                closed.append(room)
        return closed

    def close(self, room: str) -> Path | None:
        m = self._open.pop(room, None)
        self._empty_since.pop(room, None)
        if not m:
            return None
        m.ended_at = self._now()
        self.append(room, "session_end", "marvin", {"participants": list(m.participants)}, meeting=m)
        sig = None
        if m.path:
            sig_path = m.path.with_suffix(".sig")
            sig_path.write_text(hmac.new(self.secret, m.prev.encode(), hashlib.sha256).hexdigest())
            self._index_add(m)
            sig = m.path
            if self.on_close:
                try:
                    self.on_close(m, m.path)
                except Exception:
                    log.exception("audit export after close")
        log.info("audit session=%s room=%s actor=marvin verb=session_end", m.id, room)
        return sig

    def _index_add(self, m: Meeting) -> None:
        if not self.root:
            return
        idx = self.root / "index.json"
        try:
            rows = json.loads(idx.read_text()) if idx.exists() else []
        except Exception:
            rows = []
        rows.append({
            "id": m.id, "room": m.room, "started_at": m.started_at, "ended_at": m.ended_at,
            "participants": [p for p in m.participants],
        })
        idx.write_text(json.dumps(rows[-500:], indent=2))

    def list(self, *, room: str | None = None, who: str | None = None, admin: bool = False) -> list[dict[str, Any]]:
        self.prune()
        if not self.root:
            return []
        idx = self.root / "index.json"
        try:
            rows = json.loads(idx.read_text()) if idx.exists() else []
        except Exception:
            rows = []
        # live meetings
        for m in self._open.values():
            rows.append({
                "id": m.id, "room": m.room, "started_at": m.started_at, "ended_at": None,
                "participants": list(m.participants), "live": True,
            })
        out = []
        for r in reversed(rows):
            if room and r.get("room") != room:
                continue
            if not admin and who and who not in (r.get("participants") or []):
                continue
            out.append(r)
            if len(out) >= 80:
                break
        return out

    def read(self, session_id: str, *, who: str | None = None, admin: bool = False) -> dict[str, Any] | None:
        if not self.root:
            return None
        path = None
        for p in self.root.glob(f"*/{session_id}.jsonl"):
            path = p
            break
        live = next((m for m in self._open.values() if m.id == session_id), None)
        if live and live.path:
            path = live.path
        if not path or not path.exists():
            return None
        records = []
        prev = GENESIS
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            expect = hashlib.sha256(prev.encode() + _canon({k: rec[k] for k in rec if k != "hash"})).hexdigest()
            rec["chain_ok"] = rec.get("hash") == expect and rec.get("prev") == prev
            prev = rec.get("hash") or prev
            records.append(rec)
        people = []
        for rec in records:
            if rec.get("verb") == "join" and rec.get("actor") not in people:
                people.append(rec["actor"])
        if not admin and who and who not in people:
            return None
        sig_ok = None
        sig = path.with_suffix(".sig")
        if sig.exists() and records:
            sig_ok = hmac.compare_digest(sig.read_text().strip(), hmac.new(self.secret, prev.encode(), hashlib.sha256).hexdigest())
        return {
            "id": session_id,
            "room": records[0]["room"] if records else None,
            "records": records,
            "signed": sig_ok,
            "live": live is not None,
        }

    def prune(self) -> int:
        if not self.root or self.retention_days <= 0:
            return 0
        cutoff = self._now() - self.retention_days * 86400
        n = 0
        for p in self.root.glob("*/*.jsonl"):
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
                p.with_suffix(".sig").unlink(missing_ok=True)
                n += 1
        return n

    def verify_turn(self, session_id: str, actor: str, turn: int) -> bool:
        data = self.read(session_id, admin=True)
        if not data:
            return False
        for rec in data["records"]:
            if rec.get("verb") == "turn" and rec.get("actor") == actor and rec.get("turn") == turn:
                return True
        return False


def _small(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep the JSONL line short: hash big strings, keep names."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, str) and len(v) > 400:
            out[k] = v[:400]
            out[k + "_sha"] = _sha(v)
        elif isinstance(v, (dict, list)):
            raw = json.dumps(v, default=str)
            if len(raw) > 800:
                out[k + "_sha"] = _sha(raw)
                out[k + "_n"] = len(v) if isinstance(v, list) else len(v)
            else:
                out[k] = v
        else:
            out[k] = v
    return out
