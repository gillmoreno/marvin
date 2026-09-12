"""Harness profiles: which coding agents a room can run, how each is launched and authenticated.

Two kinds: `claude-sdk` (the in-process Claude Agent SDK adapter) and `acp` (any agent speaking the Agent Client
Protocol over stdio). Commands were checked against the ACP registry (cdn.agentclientprotocol.com/registry/v1) and
the vendors' docs on 2026-09-11; see docs_and_changelog/harnesses.md for what could and could not be verified.
Operators override a launch command with MARVIN_HARNESS_CMD_<ID> (id upper-cased, dashes to underscores), e.g.
MARVIN_HARNESS_CMD_OPENCODE="/opt/opencode/opencode acp".
"""
from __future__ import annotations

import os
import shlex
from dataclasses import asdict, dataclass, field
from typing import Any

from .permissions import PermissionBroker
from .prompt import ROOM_SYSTEM_PROMPT

DEFAULT_HARNESS = "claude-code"
ANTHROPIC_AUTH = "ANTHROPIC_API_KEY (or Bedrock/Vertex commercial credentials); never a personal Pro/Max OAuth token on a shared server"

CLAUDE_MODELS = [
    {"id": "claude-fable-5-1", "label": "Fable 5.1", "note": "most capable"},
    {"id": "claude-opus-5", "label": "Opus 5", "note": "strong, cheaper"},
    {"id": "claude-sonnet-5", "label": "Sonnet 5", "note": "fast"},
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5", "note": "fastest, cheapest"},
]


@dataclass(frozen=True)
class HarnessProfile:
    id: str
    label: str
    kind: str  # "claude-sdk" | "acp"
    command: list[str]
    auth: str  # one line for the operator: how this agent gets its credentials
    models: list[dict[str, str]] = field(default_factory=list)  # empty: the agent decides (ACP agents report their own)
    default_model: str | None = None
    note: str = ""
    env: dict[str, str] = field(default_factory=dict)  # extra environment for the subprocess (never secrets)

    def to_wire(self) -> dict[str, Any]:
        d = asdict(self)
        d["command"] = effective_command(self)
        d.pop("env", None)
        return d


PROFILES: tuple[HarnessProfile, ...] = (
    HarnessProfile(
        id="claude-code", label="Claude Code (SDK)", kind="claude-sdk",
        command=["claude"],  # informational: the Claude Agent SDK spawns its bundled `claude` binary itself
        auth=ANTHROPIC_AUTH, models=CLAUDE_MODELS, default_model="claude-fable-5-1",
        note="In-process Claude Agent SDK adapter: system prompt, resume, cost reporting and per-tool pre-approval all native.",
    ),
    HarnessProfile(
        id="claude-acp", label="Claude Code (ACP)", kind="acp",
        command=["claude-agent-acp"],
        auth=ANTHROPIC_AUTH,
        note="npm i -g @agentclientprotocol/claude-agent-acp (the @zed-industries package of the same name is the old, unmaintained location).",
    ),
    HarnessProfile(
        id="codex", label="Codex CLI", kind="acp",
        command=["codex-acp"],
        auth="OPENAI_API_KEY, or `codex login` cached in ~/.codex",
        note="npm i -g @agentclientprotocol/codex-acp; wraps OpenAI's Codex CLI.",
    ),
    HarnessProfile(
        id="cursor", label="Cursor CLI", kind="acp",
        command=["agent", "acp"],
        auth="CURSOR_API_KEY, or `agent login` (cached token); the agent advertises the `cursor_login` auth method",
        note="curl https://cursor.com/install -fsS | bash installs `agent` (older installs call it `cursor-agent`; override with MARVIN_HARNESS_CMD_CURSOR).",
    ),
    HarnessProfile(
        id="gemini", label="Gemini CLI", kind="acp",
        command=["gemini", "--acp"],
        auth="GEMINI_API_KEY (or GOOGLE_API_KEY / Vertex ADC); interactive Google login is not usable headless",
        note="npm i -g @google/gemini-cli. Older releases used --experimental-acp.",
    ),
    HarnessProfile(
        id="opencode", label="OpenCode", kind="acp",
        command=["opencode", "acp"],
        auth="`opencode auth login` (stored under ~/.local/share/opencode), or provider keys such as ANTHROPIC_API_KEY / OPENAI_API_KEY",
        note="npm i -g opencode-ai, or the binary release. Model is picked in OpenCode's config (provider/model).",
    ),
    HarnessProfile(
        id="grok", label="Grok Build (xAI)", kind="acp",
        command=["grok", "agent", "stdio"],
        auth="XAI_API_KEY, or `grok login`",
        note="npm i -g @xai-official/grok (pin the version: 1.0.25 has no --no-auto-update flag, unknown flags abort the CLI). Model: `grok -m <id> agent stdio` via MARVIN_HARNESS_CMD_GROK.",
    ),
    HarnessProfile(
        id="copilot", label="GitHub Copilot CLI", kind="acp",
        command=["copilot", "--acp"],
        auth="COPILOT_GITHUB_TOKEN / GH_TOKEN of an account with Copilot, or `copilot login`",
        note="npm i -g @github/copilot.",
    ),
)
_BY_ID = {p.id: p for p in PROFILES}


def profiles() -> list[HarnessProfile]:
    return list(PROFILES)


def get(harness_id: str | None) -> HarnessProfile:
    hid = harness_id or default_id()
    try:
        return _BY_ID[hid]
    except KeyError:
        raise KeyError(f"unknown harness {hid!r}; known: {', '.join(_BY_ID)}") from None


def ids() -> list[str]:
    return list(_BY_ID)


def default_id() -> str:
    hid = os.environ.get("MARVIN_HARNESS", "").strip() or DEFAULT_HARNESS
    return hid if hid in _BY_ID else DEFAULT_HARNESS


def command_env_var(harness_id: str) -> str:
    return "MARVIN_HARNESS_CMD_" + harness_id.upper().replace("-", "_")


def effective_command(profile: HarnessProfile) -> list[str]:
    override = os.environ.get(command_env_var(profile.id), "").strip()
    return shlex.split(override) if override else list(profile.command)


def create_harness(
    profile: HarnessProfile | str,
    cwd: str,
    *,
    agent_name: str = "Marvin",
    room: str = "room",
    model: str | None = None,
    resume: str | None = None,
    add_dirs: list[str] | None = None,
    permissions: PermissionBroker | None = None,
    sandbox: Any | None = None,
    env: dict[str, str] | None = None,
    project: str = "",
):
    """Build the adapter for a profile. `permissions` may be None: RoomSession assigns the broker after construction.
    `sandbox` (marvin.sandbox.RoomSandbox) makes the agent process run inside the room's container: ACP commands are
    prefixed with `docker exec`, the Claude SDK is pointed at a wrapper that does the same for its `claude` binary.
    `env` is extra per-room environment for the agent process (the git/gh identity files, marvin.github).
    `project` is the room's repo layout with roles (RoomConfig.project_text), appended to the agent's instructions."""
    p = get(profile) if isinstance(profile, str) else profile
    extra = {**p.env, **(env or {})}
    if p.kind == "claude-sdk":
        from .claude_code import ClaudeCodeHarness  # heavy import (SDK), only when used

        return ClaudeCodeHarness(
            cwd, permissions=permissions, agent_name=agent_name, room=room, model=model, resume=resume, add_dirs=list(add_dirs or []),  # type: ignore[arg-type]
            cli_path=sandbox.cli_path("claude") if sandbox else None, env=extra, project=project,
        )
    if p.kind == "acp":
        from .acp import AcpHarness

        command = effective_command(p)
        if sandbox:
            command = sandbox.wrap(command, env=extra)
        return AcpHarness(
            cwd, permissions, agent_name=agent_name, room=room, command=command, env=extra, model=model, resume=resume,
            add_dirs=list(add_dirs or []), name=p.id, system_prompt=ROOM_SYSTEM_PROMPT, project=project,
        )
    raise ValueError(f"harness {p.id!r} has unknown kind {p.kind!r}")
