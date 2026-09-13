"""Turn assembly: turn a wake-word segment plus the room's recent transcript into one harness message."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .transcript import Segment, Timeline
from .wake import WakeDetector, WakeMatch


@dataclass(frozen=True)
class Turn:
    asked_by: str
    question: str
    context: list[Segment]  # everything the room said since the previous turn
    trigger: Segment
    match: WakeMatch


class TurnAssembler:
    """Feed it every segment; it returns a Turn only when someone addressed the agent."""

    def __init__(
        self,
        timeline: Timeline,
        detector: WakeDetector | None = None,
        max_context_s: float | None = None,
        wake_hold_s: float = 8.0,
    ) -> None:
        """`max_context_s` caps how far back a turn's context reaches; None (the default) means everything since
        the previous turn, however long the room talked without addressing the agent.
        `wake_hold_s`: VAD often cuts after "Marvin,"; a name-only utterance waits this long for the rest."""
        self.timeline = timeline
        self.detector = detector or WakeDetector()
        self.max_context_s = max_context_s
        self.wake_hold_s = wake_hold_s
        self.last_turn_at: float = timeline.t0
        self._pending_wake: tuple[str, float, str] | None = None  # speaker, at, alias

    def on_segment(self, seg: Segment) -> Turn | None:
        self.timeline.add(seg)
        if not seg.final:
            return None
        if self._pending_wake and seg.speaker != self._pending_wake[0]:
            self._pending_wake = None
        match = self.detector.detect(seg.text)
        if match is None:
            hold = self._pending_wake
            if hold and (seg.start + 0.5) >= hold[1] and (seg.start - hold[1]) <= self.wake_hold_s and seg.text.strip():
                match = WakeMatch(position="start", alias=hold[2], question=seg.text.strip())
                self._pending_wake = None
            else:
                return None
        elif not match.question.strip():
            self._pending_wake = (seg.speaker, seg.end, match.alias)
            return None
        else:
            self._pending_wake = None
        floor = self.last_turn_at if self.max_context_s is None else max(self.last_turn_at, seg.end - self.max_context_s)
        context = [s for s in self.timeline.since(floor, exclude=seg) if s.start < seg.end]
        self.last_turn_at = seg.end
        return Turn(asked_by=seg.speaker, question=match.question or seg.text, context=context, trigger=seg, match=match)


def render_prompt(turn: Turn, timeline: Timeline, agent_name: str = "Marvin", attachments: Sequence[str] = ()) -> str:
    """The single message the harness receives for one invocation."""
    parts: list[str] = []
    if turn.context:
        parts.append(
            f"Voice room transcript since your last turn (several people talking, you are {agent_name}, "
            "you were not addressed until the end). Together with your earlier turns this is the whole meeting; "
            "the most recent lines carry the most weight, earlier ones are background:\n"
        )
        parts.append(timeline.render(turn.context))
        parts.append("")
    parts.append(f'{turn.asked_by} is now addressing you: "{turn.question}"')
    if attachments:
        listed = "\n".join(f"- {p}" for p in attachments)
        parts.append(f"\nImages shared in the room since your last turn, saved on disk — open them with the Read tool:\n{listed}")
    parts.append(
        f"\nRespond to {turn.asked_by}. Everyone in the room reads your reply on a shared screen, "
        "so lead with the answer in one or two short sentences, then details only if needed. "
        "If the request is ambiguous because people disagreed above, say who wanted what and ask. "
        f"If you commit, the trailer is `Requested-by: {turn.asked_by}`."
    )
    return "\n".join(parts)
