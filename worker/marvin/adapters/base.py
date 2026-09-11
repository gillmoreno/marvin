"""Harness-agnostic adapter contract. Claude Code, OpenCode, anything: text in, events out."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol

EventKind = Literal[
    "turn_start",  # harness accepted the message
    "text_delta",  # streamed assistant text chunk
    "text",  # a complete assistant text block
    "tool_use",  # harness is calling a tool (name + input)
    "tool_result",  # tool finished (truncated output)
    "permission_request",  # a human must approve; see PermissionBroker
    "result",  # turn finished (cost, duration, session id)
    "error",
]


@dataclass(frozen=True)
class HarnessEvent:
    kind: EventKind
    data: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.data}


class Harness(Protocol):
    """One long-lived coding-agent session bound to one repo/worktree."""

    name: str

    async def start(self) -> None: ...

    def send(self, prompt: str) -> AsyncIterator[HarnessEvent]:
        """Send one user message and stream the events of the resulting turn."""
        ...

    async def interrupt(self) -> None: ...

    async def close(self) -> None: ...
