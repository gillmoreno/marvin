"""Claude Code harness adapter, built on the Claude Agent SDK (one long-lived session per room)."""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    UserMessage,
)
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    TextBlock,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
)

from .base import HarnessEvent
from .permissions import PermissionBroker
from .prompt import ROOM_SYSTEM_PROMPT, _truncate

log = logging.getLogger(__name__)

__all__ = ["ClaudeCodeHarness", "ROOM_SYSTEM_PROMPT"]


class ClaudeCodeHarness:
    name = "claude-code"

    def __init__(
        self,
        cwd: str,
        permissions: PermissionBroker,
        *,
        agent_name: str = "Marvin",
        room: str = "room",
        model: str | None = None,
        resume: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 40,
        add_dirs: list[str] | None = None,
        cli_path: str | None = None,
        env: dict[str, str] | None = None,
        project: str = "",
    ) -> None:
        self.cwd = cwd
        self.permissions = permissions
        self.agent_name = agent_name
        self.session_id: str | None = resume
        self.model: str | None = model  # effective model, filled from the session init message
        self.add_dirs = list(add_dirs or [])
        self.cli_path = cli_path  # None: the SDK's bundled `claude`; set by the sandbox to a `docker exec` wrapper
        self.env = dict(env or {})
        self._client: ClaudeSDKClient | None = None
        self._options = ClaudeAgentOptions(
            cwd=cwd,
            cli_path=cli_path,
            env=self.env,
            model=model,
            resume=resume,
            max_turns=max_turns,
            permission_mode="default",
            # Read-only tools never bother the room; anything that writes or runs goes through the broker.
            allowed_tools=allowed_tools if allowed_tools is not None else ["Read", "Glob", "Grep", "WebFetch", "WebSearch"],
            can_use_tool=self._can_use_tool,
            setting_sources=["user", "project"],  # user = the machine notes in $HOME/.claude/CLAUDE.md
            add_dirs=self.add_dirs,
            system_prompt={"type": "preset", "preset": "claude_code", "append": ROOM_SYSTEM_PROMPT.format(agent_name=agent_name, room=room) + (f"\n{project}" if project else "")},
            include_partial_messages=True,
            # Tool results carry dropped screenshots as base64 (uploads allow 8 MB); the SDK default of 1 MB per message
            # raises CLIJSONDecodeError on anything bigger than a small image.
            max_buffer_size=32 * 1024 * 1024,
        )

    # -- permission routing ---------------------------------------------------
    async def _can_use_tool(self, tool_name: str, input_data: dict, context: ToolPermissionContext):
        allowed = await self.permissions.ask(tool_name, input_data)
        if allowed:
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(message="Denied by the room (nobody approved in time or someone declined).")

    # -- lifecycle ------------------------------------------------------------
    async def start(self) -> None:
        self._client = ClaudeSDKClient(options=self._options)
        await self._client.connect()
        log.info("claude code session started in %s", self.cwd)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def interrupt(self) -> None:
        if self._client is not None:
            await self._client.interrupt()

    # -- one turn -------------------------------------------------------------
    async def send(self, prompt: str) -> AsyncIterator[HarnessEvent]:
        assert self._client is not None, "call start() first"
        await self._client.query(prompt)
        yield HarnessEvent("turn_start", {"harness": self.name})
        async for msg in self._client.receive_response():
            for ev in self._translate(msg):
                yield ev

    def _translate(self, msg: Any) -> list[HarnessEvent]:
        out: list[HarnessEvent] = []
        if isinstance(msg, StreamEvent):
            ev = msg.event or {}
            delta = ev.get("delta") or {}
            if ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                out.append(HarnessEvent("text_delta", {"text": delta.get("text", "")}))
        elif isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    out.append(HarnessEvent("text", {"text": block.text}))
                elif isinstance(block, ToolUseBlock):
                    out.append(HarnessEvent("tool_use", {"id": block.id, "tool": block.name, "input": block.input}))
        elif isinstance(msg, UserMessage):
            content = msg.content if isinstance(msg.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock):
                    out.append(
                        HarnessEvent(
                            "tool_result",
                            {"id": block.tool_use_id, "output": _truncate(block.content), "is_error": bool(getattr(block, "is_error", False))},
                        )
                    )
        elif isinstance(msg, ResultMessage):
            self.session_id = msg.session_id or self.session_id
            out.append(
                HarnessEvent(
                    "result",
                    {
                        "subtype": msg.subtype,
                        "is_error": bool(msg.is_error),
                        "cost_usd": msg.total_cost_usd,
                        "duration_ms": msg.duration_ms,
                        "num_turns": msg.num_turns,
                        "session_id": msg.session_id,
                    },
                )
            )
        elif isinstance(msg, SystemMessage):
            if msg.subtype == "init":
                self.session_id = (msg.data or {}).get("session_id", self.session_id)
                self.model = (msg.data or {}).get("model", self.model)
        return out
