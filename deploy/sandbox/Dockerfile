# syntax=docker/dockerfile:1
# The room sandbox: where a room's coding agent runs when MARVIN_SANDBOX=docker (marvin/sandbox.py).
# One container per room is started from this image with `sleep infinity`; the worker `docker exec`s the harness
# into it. The repo is bind-mounted at its worker-side path, HOME is a per-room directory under the state dir.
#
#   make sandbox-image                              # marvin-sandbox:local with the default harness set
#   docker build --build-arg HARNESSES="claude-code grok" -t marvin-sandbox:local deploy/sandbox
#
# Teams can build their own image FROM this one (or from anything) with their toolchain; the only requirement is
# that the harness CLI the room uses is on PATH and `marvin-sandbox-init` exists (copy it from here).

FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    PATH=/opt/marvin/bin:/usr/local/bin:/usr/bin:/bin

# Toolchain a coding agent expects: git, gh, ripgrep, jq, python3 + uv, make, compilers for native deps, ssh client.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git openssh-client ripgrep jq make build-essential procps less unzip \
      python3 python3-venv python3-pip \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update && apt-get install -y --no-install-recommends gh \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /usr/local/bin/

# Docker CLI + compose plugin, used only when the operator sets MARVIN_SANDBOX_DOCKER_SOCKET=1 (otherwise harmless).
RUN install -m 0755 -d /etc/apt/keyrings && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
 && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin docker-buildx-plugin \
 && rm -rf /var/lib/apt/lists/*

# Harness CLIs. Space-separated ids from marvin/adapters/registry.py; each is installed only if listed.
# Versions checked against npm on 2026-09-12. grok is pinned to 1.0.25: newer builds auto-update on start, which
# an unattended agent must never do (see docs_and_changelog/harnesses.md).
ARG HARNESSES="claude-code claude-acp codex gemini opencode grok copilot cursor"
ARG CLAUDE_CODE_VERSION=2.1.269
ARG CLAUDE_ACP_VERSION=0.76.0
ARG CODEX_ACP_VERSION=1.11.0
ARG GEMINI_CLI_VERSION=0.59.0
ARG OPENCODE_VERSION=1.18.30
ARG GROK_VERSION=1.0.25
ARG COPILOT_VERSION=1.0.83
RUN set -eux; has() { case " $HARNESSES " in *" $1 "*) return 0;; *) return 1;; esac; }; \
    pkgs=""; \
    has claude-code && pkgs="$pkgs @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"; \
    has claude-acp  && pkgs="$pkgs @agentclientprotocol/claude-agent-acp@${CLAUDE_ACP_VERSION}"; \
    has codex       && pkgs="$pkgs @agentclientprotocol/codex-acp@${CODEX_ACP_VERSION}"; \
    has gemini      && pkgs="$pkgs @google/gemini-cli@${GEMINI_CLI_VERSION}"; \
    has opencode    && pkgs="$pkgs opencode-ai@${OPENCODE_VERSION}"; \
    has grok        && pkgs="$pkgs @xai-official/grok@${GROK_VERSION}"; \
    has copilot     && pkgs="$pkgs @github/copilot@${COPILOT_VERSION}"; \
    [ -z "$pkgs" ] || npm install -g $pkgs; \
    npm cache clean --force; \
    if has cursor; then \
      mkdir -p /opt/marvin/bin && HOME=/tmp/cursor-install sh -c 'curl -fsS https://cursor.com/install | bash' \
      && cp /tmp/cursor-install/.local/bin/agent /opt/marvin/bin/agent 2>/dev/null || cp /tmp/cursor-install/.local/bin/cursor-agent /opt/marvin/bin/agent; \
      rm -rf /tmp/cursor-install; \
    fi

COPY marvin-sandbox-init /usr/local/bin/marvin-sandbox-init
RUN chmod +x /usr/local/bin/marvin-sandbox-init

# HOME is set per room by the worker (-e HOME=...), the working directory per exec (-w). Nothing runs by default:
# the worker keeps the container alive with `sleep infinity` and execs into it.
CMD ["sleep", "infinity"]
