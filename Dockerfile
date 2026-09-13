# syntax=docker/dockerfile:1
# Marvin worker + web UI. One image, two commands:
#   python -m marvin.main           (worker: joins every room in /etc/marvin/rooms.yaml)
#   python -m marvin.token_server   (web: token endpoint + built UI on :8080)

FROM node:22-alpine AS web
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ .
RUN pnpm build

FROM python:3.12-slim
ARG MARVIN_GIT_SHA=
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv UV_PYTHON=/usr/local/bin/python3 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    MARVIN_GIT_SHA=$MARVIN_GIT_SHA
# git for the repos, docker CLI + compose for the apps (daemon is the dind sidecar), ripgrep for Claude Code, libgomp for CTranslate2
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates gnupg ripgrep libgomp1 openssh-client procps \
 && install -m 0755 -d /etc/apt/keyrings && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin docker-buildx-plugin gh \
 && rm -rf /var/lib/apt/lists/*
# Node 22 + npm: the Claude Agent SDK ships its own `claude` binary and needs neither, but every ACP harness except
# Cursor and the OpenCode binary release is distributed through npm (see docs_and_changelog/harnesses.md).
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/* \
 && npm config set update-notifier false
# Install only the ACP agents this deployment will actually use; each also needs its credentials at runtime.
# Pin versions. harness id -> package (credential):
#   claude-acp -> @agentclientprotocol/claude-agent-acp (ANTHROPIC_API_KEY)     codex   -> @agentclientprotocol/codex-acp (OPENAI_API_KEY)
#   gemini     -> @google/gemini-cli (GEMINI_API_KEY)                            opencode -> opencode-ai (`opencode auth login` / provider keys)
#   grok       -> @xai-official/grok (XAI_API_KEY)                               copilot -> @github/copilot (COPILOT_GITHUB_TOKEN)
#   cursor     -> `curl -fsS https://cursor.com/install | bash` puts `agent` in ~/.local/bin (CURSOR_API_KEY)
# RUN npm i -g @agentclientprotocol/codex-acp@1.11.0 opencode-ai@1.18.30 @google/gemini-cli@0.59.0
# RUN npm i -g @agentclientprotocol/claude-agent-acp@0.76.0 @xai-official/grok@1.0.25 @github/copilot@1.0.83
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /usr/local/bin/
WORKDIR /app
COPY worker/pyproject.toml worker/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY worker/ .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
COPY --from=web /web/dist /app/web-dist
COPY deploy/docker-entrypoint.sh /usr/local/bin/marvin-entrypoint
RUN chmod +x /usr/local/bin/marvin-entrypoint
ENV PATH=/app/.venv/bin:$PATH \
    MARVIN_WEB_DIST=/app/web-dist MARVIN_TOKEN_HOST=0.0.0.0 \
    HOME=/work/home HF_HOME=/work/cache/hf MARVIN_STATE_DIR=/work/state MARVIN_REPOS_DIR=/work/repos MARVIN_CONFIG=/etc/marvin/rooms.yaml
ENTRYPOINT ["marvin-entrypoint"]
CMD ["python", "-m", "marvin.main"]
