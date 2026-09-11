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
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv UV_PYTHON=/usr/local/bin/python3 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# git for the repos, docker CLI + compose for the apps (daemon is the dind sidecar), ripgrep for Claude Code, libgomp for CTranslate2
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates gnupg ripgrep libgomp1 openssh-client procps \
 && install -m 0755 -d /etc/apt/keyrings && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin docker-buildx-plugin gh \
 && rm -rf /var/lib/apt/lists/*
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
