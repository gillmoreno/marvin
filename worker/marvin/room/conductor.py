"""Room orchestration, independent of LiveKit: segments in, turns run one at a time, events out."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from marvin.adapters.base import Harness
from marvin.adapters.permissions import PermissionBroker, PermissionRequest
from marvin.bridge import Segment, Timeline, Turn, TurnAssembler, WakeDetector, render_prompt

from .protocol import split_text_event
from .uploads import Attachment, ImageInbox

log = logging.getLogger(__name__)
Publish = Callable[[dict[str, Any]], Awaitable[None]]


class Conductor:
    def __init__(
        self,
        harness: Harness,
        publish: Publish,
        *,
        agent_name: str = "Marvin",
        timeline: Timeline | None = None,
        uploads_dir: str | Path | None = None,
        app_links: list[dict] | None = None,
        on_turn_begin: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.harness = harness
        self.publish = publish
        self.agent_name = agent_name
        self.app_links = app_links or []
        self.on_turn_begin = on_turn_begin  # called with the requester's name before the harness sees the prompt (git identity)
        self.timeline = timeline if timeline is not None else Timeline()  # an empty Timeline is falsy (__len__)
        self.assembler = TurnAssembler(self.timeline, WakeDetector(name=agent_name))
        self.permissions = PermissionBroker(self._notify_permission)
        self.uploads = ImageInbox(uploads_dir)
        self._attachments: list[Attachment] = []  # dropped images waiting for the next turn
        self._queue: asyncio.Queue[tuple[Turn, list[Attachment]]] = asyncio.Queue()
        self._runner: asyncio.Task | None = None
        self._state = "idle"

    # -- lifecycle --------------------------------------------------------------
    async def start(self) -> None:
        try:
            await self.harness.start()
        except Exception as e:
            # STT / LiveKit are already up by the time we get here. If the agent is not ready (Grok still
            # signing in, timeout, missing binary), keep the turn runner so a later message retries.
            log.exception("harness failed to start")
            await self.publish({"kind": "error", "message": f"{type(e).__name__}: {e or 'harness failed to start'}"})
        self._runner = asyncio.create_task(self._run_turns())
        await self._set_state("idle")
        if self.app_links:
            await self.publish({"kind": "app_links", "links": self.app_links})

    async def close(self) -> None:
        if self._runner:
            self._runner.cancel()
        await self.harness.close()

    async def set_app_links(self, links: list[dict]) -> None:
        """Replace the app links (static from config + ports detected on the machine) and tell the room."""
        if links == self.app_links:
            return
        self.app_links = links
        await self.publish({"kind": "app_links", "links": links})

    async def announce(self) -> None:
        """Re-send current state (and any open approvals) so a participant who just joined sees them."""
        await self.publish({"kind": "status", "state": self._state})
        await self.publish({"kind": "auto_approve", "on": self.permissions.auto_approve, "by": self.agent_name})
        if self.app_links:
            await self.publish({"kind": "app_links", "links": self.app_links})
        for req in self.permissions.pending:
            await self.publish({"kind": "permission_request", **req.to_wire()})
        for att in self._attachments:
            await self.publish(self._attachment_event(att))

    # -- inputs -----------------------------------------------------------------
    async def on_segment(self, seg: Segment) -> None:
        """An utterance from one speaker's STT: interim (final=False, UI only) or final (becomes a turn candidate)."""
        # start/end are session-relative seconds (what the prompt context uses); `at` is wall-clock for the UI.
        at = time.time() - (time.monotonic() - seg.start)
        await self.publish(
            {"kind": "transcript", "speaker": seg.speaker, "text": seg.text, "start": seg.start - self.timeline.t0, "end": seg.end - self.timeline.t0, "at": at, "final": seg.final}
        )
        turn = self.assembler.on_segment(seg)
        if turn:
            log.info("turn from %s: %s", turn.asked_by, turn.question)
            await self._enqueue(turn)

    async def on_control(self, sender: str, msg: dict[str, Any], roles: frozenset[str] = frozenset()) -> None:
        """A JSON control message from a client (approve/deny/ask/image/interrupt for everyone; auto_approve for admins).
        `roles` come from the participant's server-signed LiveKit metadata (see session.roles_of)."""
        action = msg.get("action")
        if action in ("approve", "deny"):
            ok = self.permissions.resolve(str(msg.get("id")), action == "approve")
            if ok:
                await self.publish({"kind": "permission_resolved", "id": msg["id"], "allow": action == "approve", "by": sender})
        elif action == "ask":
            # Typed question: same path as a spoken "Marvin, ...", context is whatever the room said since the last turn.
            t = time.monotonic()
            seg = Segment(start=t, end=t, speaker=sender, text=f"{self.agent_name}, {msg.get('text', '')}", final=True)
            turn = self.assembler.on_segment(seg)
            if turn:
                await self._enqueue(turn)
        elif action == "image":
            # An image dropped into the pane; it rides along with the next thing anyone asks.
            att = self.uploads.add(sender, msg)
            if att:
                self._attachments.append(att)
                await self.publish(self._attachment_event(att))
        elif action == "auto_approve":
            # "Always allow": everything runs without asking, until someone flips it back off. Arbitrary code execution
            # for the whole room, so admins only.
            if "admin" not in roles:
                log.warning("%s tried to toggle auto_approve without the admin role", sender)
                await self.publish({"kind": "denied", "action": "auto_approve", "by": sender, "reason": "admin role required"})
                return
            on = bool(msg.get("on", True))
            self.permissions.auto_approve = on
            await self.publish({"kind": "auto_approve", "on": on, "by": sender})
            if on:
                for req_id in self.permissions.approve_all_pending():
                    await self.publish({"kind": "permission_resolved", "id": req_id, "allow": True, "by": sender})
        elif action == "interrupt":
            await self.harness.interrupt()

    # -- turns ------------------------------------------------------------------
    async def _enqueue(self, turn: Turn) -> None:
        """Claim whatever images are waiting now, so a later drop can't attach itself to this turn."""
        attachments, self._attachments = self._attachments, []
        await self._queue.put((turn, attachments))

    async def _run_turns(self) -> None:
        while True:
            turn, attachments = await self._queue.get()
            await self._set_state("thinking")
            await self.publish({"kind": "turn_start", "asked_by": turn.asked_by, "question": turn.question})
            try:
                if self.on_turn_begin:
                    try:
                        await self.on_turn_begin(turn.asked_by)
                    except Exception:
                        log.exception("on_turn_begin")
                prompt = render_prompt(turn, self.timeline, agent_name=self.agent_name, attachments=[str(a.path) for a in attachments])
                async for ev in self.harness.send(prompt):
                    if ev.kind == "turn_start":
                        continue  # we already announced it with the speaker's name
                    for wire in split_text_event(ev.to_wire()):
                        await self.publish(wire)
            except Exception as e:  # keep the room alive whatever the harness does
                log.exception("turn failed")
                await self.publish({"kind": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                await self._set_state("idle")

    def _attachment_event(self, att: Attachment) -> dict[str, Any]:
        return {"kind": "attachment", "name": att.name, "path": str(att.path), "by": att.sender}

    async def _notify_permission(self, req: PermissionRequest) -> None:
        await self._set_state("waiting_approval")
        await self.publish({"kind": "permission_request", **req.to_wire()})

    async def _set_state(self, state: str) -> None:
        self._state = state
        await self.publish({"kind": "status", "state": state})
