"""Speaker-labeled transcript timeline merged from many per-participant STT streams."""
from __future__ import annotations

import bisect
import time
from dataclasses import dataclass, field


@dataclass(frozen=True, order=True)
class Segment:
    """One finalized (or interim) utterance from one speaker.

    `start`/`end` are seconds on a shared clock (time.monotonic() of the worker).
    Ordering is by start time so segments from different tracks interleave naturally.
    """

    start: float
    end: float = field(compare=False)
    speaker: str = field(compare=False)
    text: str = field(compare=False)
    final: bool = field(default=True, compare=False)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


class Timeline:
    """Append-mostly, time-ordered list of final segments.

    Segments can arrive out of order (one track's STT is slower than another's),
    so we insert by start time instead of appending blindly.
    """

    def __init__(self, t0: float | None = None) -> None:
        self.t0 = time.monotonic() if t0 is None else t0
        self._segments: list[Segment] = []

    def add(self, seg: Segment) -> None:
        if not seg.final:
            return  # interim results never enter the timeline
        bisect.insort(self._segments, seg)

    def since(self, t: float, *, exclude: Segment | None = None) -> list[Segment]:
        """All segments that end after `t`, oldest first."""
        return [s for s in self._segments if s.end > t and s is not exclude]

    def all(self) -> list[Segment]:
        return list(self._segments)

    def __len__(self) -> int:
        return len(self._segments)

    def clock(self, seconds: float) -> str:
        """Render a timeline-relative timestamp as mm:ss."""
        rel = max(0.0, seconds - self.t0)
        m, s = divmod(int(rel), 60)
        return f"{m:02d}:{s:02d}"

    def render(self, segments: list[Segment]) -> str:
        return "\n".join(f"[{self.clock(s.start)}] {s.speaker}: {s.text.strip()}" for s in segments)
