"""Routes a harness's permission prompt to humans in the room and waits for a decision."""
from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class PermissionRequest:
    id: str
    tool: str
    input: dict[str, Any]
    _future: asyncio.Future[bool] = field(repr=False)

    def to_wire(self) -> dict[str, Any]:
        return {"id": self.id, "tool": self.tool, "input": self.input}


class PermissionBroker:
    """Ask once, resolve from anywhere (a UI button, a voice "yes Marvin", a test)."""

    def __init__(self, notify: Callable[[PermissionRequest], Awaitable[None]], timeout_s: float = 300) -> None:
        self._notify = notify
        self._timeout_s = timeout_s
        self._pending: dict[str, PermissionRequest] = {}
        self._ids = itertools.count(1)
        self.auto_approve = False  # "always allow": stop asking the room until someone turns it back off

    @property
    def pending(self) -> list[PermissionRequest]:
        return list(self._pending.values())

    def approve_all_pending(self) -> list[str]:
        """Let anything already waiting through; returns the ids that were actually resolved."""
        return [req.id for req in self.pending if self.resolve(req.id, True)]

    async def ask(self, tool: str, tool_input: dict[str, Any]) -> bool:
        if self.auto_approve:
            return True
        loop = asyncio.get_running_loop()
        req = PermissionRequest(id=f"perm-{next(self._ids)}", tool=tool, input=tool_input, _future=loop.create_future())
        self._pending[req.id] = req
        try:
            await self._notify(req)
            return await asyncio.wait_for(req._future, timeout=self._timeout_s)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending.pop(req.id, None)

    def resolve(self, request_id: str, allow: bool) -> bool:
        req = self._pending.get(request_id)
        if req is None or req._future.done():
            return False
        req._future.set_result(allow)
        return True
