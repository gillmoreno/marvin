"""Machine notes: $HOME/.claude/CLAUDE.md, Claude Code's user-level memory. On the Pod HOME is on the /work volume,
so this file is loaded into every room's session: how repos on this machine relate, fake accounts, ports, recipes."""
from __future__ import annotations

from pathlib import Path

TEMPLATE = """# This machine

Notes that every room on this machine loads (Claude Code user memory). Keep repo-specific knowledge in that repo's
CLAUDE.md; put here what spans repos: which backend a frontend needs, fake accounts, ports, how to start things.

## Repos and how they connect

- (example) `abf-optimizer-frontend` (Vite, :3000) talks to `rw_srt_opt` (Dash, :8050) and authenticates against the
  Keycloak from `rw_srt_opt/auth-poc` (:8080, realm from realm-export.json, users alice / bob). Env in the frontend:
  VITE_OIDC_AUTHORITY, VITE_SERVER_BASE_URL.

## Recipes

- (example) Start the optimizer stack: `docker compose -f rw_srt_opt/auth-poc/docker-compose.yml up -d`, then in the
  frontend `vp install && vp dev`.
"""


def notes_path() -> Path:
    return Path.home() / ".claude" / "CLAUDE.md"


def read_notes() -> str:
    p = notes_path()
    return p.read_text() if p.exists() else TEMPLATE


def write_notes(text: str) -> None:
    p = notes_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text if text.endswith("\n") else text + "\n")
