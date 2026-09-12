# Changelog

All notable changes to Marvin. Entries are dated; the newest is on top.

## 2026-09-12 — Projects: a room is a list of repos

Design and limits: `projects.md`. Roadmap item 2.

### Added
- `RoomConfig.repos: tuple[ProjectRepo]` (`path`, `role`, `git_url`, `branch`) is the source of truth for what a room
  works on; `repo`, `git_url`, `branch` and `linked` are derived from it, so existing code, `rooms.yaml` files and
  `rooms.json` records keep working unchanged. `rooms.yaml` accepts a `repos:` list per room.
- Join screen: **New project** = a name plus a list of repos, each picked **from your GitHub** (the connected account's
  repositories, searchable, role guessed from the name), from a **folder on this machine**, or by **git URL**; role
  and branch per repo, "↑ first" makes a repo the working directory. Missing repos are cloned with the requester's
  connected GitHub token (SSH URLs rewritten to HTTPS; the token travels through a one-off credential helper, never
  argv). `POST /api/rooms {name, repos: [...]}`.
- Settings → **This project**: the same list, editable (roles, branches, add, remove, reorder) with save/discard;
  `PATCH /api/rooms/{name} {repos: [...]}` swaps the harness and the conversation continues. The old `linked` PATCH
  still works and keeps the roles it knows.
- Changes pane: one tab per repo when the project has several; `GET /api/changes?room=&repo=<path>` and
  `/api/changes/file` accept any project repo (anything else is a 404). Commit / open PR prompts name the repo.
- `GET /api/github/repos[?q=]` (self-service): the repositories the caller's connected account can see, most recently
  pushed first, cached a minute; 409 with a hint when not connected. `GitHubConnect.list_repos`, `token_for`.
- The agent's instructions list the project's repos with roles and mark the working directory (`project_text()`);
  the "Linked repos" line in the ACP first prompt is replaced by it. Tests: `tests/test_project.py`.

### Changed
- Room list shows `N repos · frontend + api` for projects; `worker/marvin/room/manager.py` `create_room`/`update_room`
  take `repos=` and `clone_token=`; `ensure_repo` clones every project repo with a `git_url`.

## 2026-09-12 — Design explorations

Three clickable HTML prototypes of alternative looks (Control Room, Editorial, Signal), each with sign-in, room,
settings and a trimmed mobile layout: `design-explorations/index.html`, notes in `design-explorations/README.md`.
Nothing in `web/src` changed.

## 2026-09-12 — Connect GitHub from the browser

Design, operator setup and limits: `github.md`. Roadmap item 7, per-user half.

### Added
- Settings → **GitHub** → **Connect GitHub**: GitHub's device flow from the UI (`web/src/GitHubConnect.tsx`). The
  worker requests a device code, the panel shows it and opens github.com/login/device, the worker polls until
  approved and stores the token encrypted (Fernet, key from `MARVIN_SESSION_SECRET`) in `<state_dir>/github.json`.
  Status, verify-on-open and Disconnect. Needs the client id of an OAuth App with device flow enabled: an admin
  pastes it into the same panel (`PUT /api/github/config`, stored in `github.json`, no restart);
  `MARVIN_GITHUB_CLIENT_ID` in the environment overrides it.
- `worker/marvin/github.py`: `TokenStore`, `GitHubConnect` (flows, polling, `/user` lookup, revocation check) and
  `GitIdentity`: per-room `gitconfig`, `token` and `gh/hosts.yml` under the room HOME, rewritten at every turn start
  with the identity of the person who asked (their connected account → machine `GITHUB_TOKEN` → none). Harnesses get
  `GIT_CONFIG_GLOBAL` / `GH_CONFIG_DIR` pointing at them; both are forwarded into the sandbox.
- Admin API `/github/me` (GET/DELETE), `/github/connect` (POST), `/github/connect/{flow}` (GET), keyed by
  `X-Marvin-User`; the token server proxies `/api/github/*` as self-service (every signed-in user, own record only).
- `Conductor(on_turn_begin=…)`; `create_harness(env=…)`; `ClaudeCodeHarness(env=…)`.
- Direct dependencies `httpx`, `cryptography` (were transitive). Tests: `tests/test_github.py`.

## 2026-09-12 — Room sandbox

Design and operations: `sandbox.md`. Roadmap item 1; addresses the agent-isolation half of finding 4 in
`security-and-compliance.md`.

### Added
- `worker/marvin/sandbox.py`: with `MARVIN_SANDBOX=docker` each room's agent runs in its own container
  (`marvin-sbx-<room>`, from `MARVIN_SANDBOX_IMAGE`). Repo, linked repos and a per-room HOME are mounted at the same
  absolute paths as on the worker; the machine notes are mounted read-only. Harness processes are `docker exec`s:
  ACP commands are prefixed, the Claude Agent SDK gets a `cli_path` wrapper. Credentials go in as environment on
  each exec (`DEFAULT_FORWARD_ENV` + `MARVIN_SANDBOX_ENV`), never onto the container's disk.
- Containers are recreated when image / mounts / network / limits change (label `marvin.sig`), restarted when
  stopped, removed with the room. `--memory`, `--cpus`, `--pids-limit`, `--init`, `no-new-privileges`,
  `MARVIN_SANDBOX_USER`, `MARVIN_SANDBOX_RUN_ARGS`. Networks: `host` (default), `container:<name>`, `bridge` with
  `MARVIN_SANDBOX_PORTS` published on loopback (the port watcher also reads `/proc/net/tcp` inside), `none`.
  `MARVIN_SANDBOX_DOCKER_SOCKET=1` opts the agent into the host daemon, with a warning.
- The worker checks daemon and image at start (`--sandbox`, `MARVIN_SANDBOX`) and pulls images that name a registry.
- `deploy/sandbox/Dockerfile` (Node 22, Python + uv, git, gh, ripgrep, Docker CLI, the eight harness CLIs selectable
  with `HARNESSES=`) and `marvin-sandbox-init`; `make sandbox-image` / `sandbox-ps` / `sandbox-clean`.
- Compose edge stack runs sandboxed by default (`container_name: marvin-worker`, volume `marvin_work`,
  `MARVIN_SANDBOX_MOUNTS=marvin_work:/work`, `MARVIN_SANDBOX_NETWORK=container:marvin-worker`); k8s worker env set
  for sandboxes inside the dind sidecar.
- `GET /api/rooms` reports `sandbox` per room; Settings → This room says where the agent runs.
- `ClaudeCodeHarness(cli_path=)`, `create_harness(sandbox=)`.

## 2026-09-12 — Shared screens in the middle column

### Fixed
- Transcript timestamps were minutes:seconds since the worker joined the room (`185:37` after three hours). Transcript
  events now also carry `at` (epoch seconds) and the UI shows local wall-clock time; session-relative `start` stays
  on the wire for prompt context and is shown as a tooltip.
- Screen share published fine (ControlBar) but nothing rendered it on either side. `web/src/ScreenShare.tsx` subscribes
  to `Track.Source.ScreenShare` tracks; the Workspace shows one tab per shared screen (yours included, as a preview),
  switches to a share when it starts and back to Changes when it stops.

## 2026-09-12 — Edge authentication and roles

Design and operations: `authentication.md`. Closes findings 1–3 of `security-and-compliance.md` §3.

### Added
- `worker/marvin/auth.py`: identity + roles (`participant`, `admin`) in three modes: `header` (trusted-proxy
  `X-Forwarded-User/-Email/-Preferred-Username/-Groups`, admins by group or user list), `password` (Marvin's own login,
  HMAC-signed HttpOnly cookie, constant-time compares, 0.5 s penalty and 10 failures/min/IP), `none` (loopback dev only).
- `GET /api/me`, `POST /api/login`, `POST /api/logout`. `GET /api/token` takes identity from the session and signs
  `{"roles": [...]}` into the LiveKit token metadata; the `name` query parameter is gone (except in `none` mode).
- The `/api/*` proxy requires a session; non-GET methods and the machine notes require `admin`; `X-Marvin-User` /
  `X-Marvin-Roles` are forwarded to the admin API. `--admin-host` / `MARVIN_ADMIN_HOST` for the worker.
- Worker: `roles_of(participant)` reads roles from server-signed metadata; `auto_approve` by a non-admin is refused
  and the room sees a `denied` event.
- UI: password login on the join screen, "signed in as" in header mode, admin-only controls hidden for participants
  (always-allow, new/delete room, harness and model pickers, linked repos, machine notes), role badge in People,
  log out in Settings.
- Edge stack: `deploy/edge/Caddyfile` (TLS, security headers, CSP, strips client-sent identity headers, `/rtc` →
  LiveKit, rest → token server), `deploy/edge/Caddyfile.oidc` (oauth2-proxy via `forward_auth`, header mapping),
  `deploy/edge/rooms.yaml`, `docker-compose.edge.yml` (livekit, web, worker, caddy; profile `oidc`), Makefile
  `edge-up` / `edge-oidc-up` / `edge-down` / `edge-logs` / `edge-ps`. Only Caddy and LiveKit media ports are published.
- k8s: `MARVIN_AUTH=header` in the web container with the oauth2-proxy ingress annotations and header renames documented.

### Changed
- `.env.example` documents `MARVIN_AUTH*`, the edge stack and `OAUTH2_PROXY_*`; local dev defaults to `MARVIN_AUTH=none`.
- The token server exits at startup when `MARVIN_AUTH` is unset and no room password is configured.

## 2026-09-11 — Live model list and picker polish

- The model picker lists the models a running ACP agent reports about itself: `GET /models?room=<name>` prefers the
  live harness's `available_models` over the profile's static list (response carries `live: true`); the web hook
  re-fetches when the harness or its effective model changes. Pinning one goes through the agent's own model selector
  and resumes the same session. Verified with Grok Build (grok-4.6 / grok-4.5).
- The harness picker no longer flashes "default ( )" before `/api/harnesses` and the room info have loaded.
- Dev: the Vite `/api` proxy follows `MARVIN_TOKEN_PORT`, so the token server can run off 8080.

## 2026-09-11 — ACP harness adapter and per-room harness choice

See `harnesses.md` for the full design, the profile table and the decisions to review.

### Added
- `worker/marvin/adapters/acp.py`: `AcpHarness`, a generic adapter speaking the Agent Client Protocol over stdio
  (JSON-RPC 2.0, newline-delimited). Streams `text_delta`/`text`, `tool_use`/`tool_result`, routes
  `session/request_permission` through the room's `PermissionBroker`, `interrupt()` → `session/cancel`, resumes via
  `session/resume` or `session/load`, applies a pinned model through `session/set_config_option` (or the legacy
  `session/set_model`), restarts the agent after a crash, and surfaces JSON-RPC errors as `error` + `result(is_error)`.
- `worker/marvin/adapters/registry.py`: `HarnessProfile` and eight profiles: `claude-code` (SDK, default),
  `claude-acp`, `codex`, `cursor`, `gemini`, `opencode`, `grok`, `copilot`. `MARVIN_HARNESS` picks the default,
  `MARVIN_HARNESS_CMD_<ID>` overrides a launch command, `create_harness()` builds the right adapter.
- `RoomConfig.harness` (`rooms.yaml` key `harness`), `RoomManager.update_room(harness=, clear_harness=)`,
  `harness`/`harness_pinned` in `GET /rooms`, `PATCH /rooms/{name}` accepts `harness` (`""` clears),
  `GET /harnesses`, `GET /models?harness=<id>`, `/api/harnesses` in the web proxy, `--harness` CLI flag.
- Web: a harness picker next to the model picker; the model list reloads when the harness changes and shows
  "harness default" for agents that report their own models.
- Tests: `tests/fake_acp_agent.py` (a scriptable stdio ACP agent), `test_acp.py`, `test_registry.py`, and harness
  cases in `test_config.py`, `test_room_update.py`, `test_admin.py`, `test_session_resume.py`.
- Dockerfile: Node 22 + npm, and a commented block showing how to install the ACP CLIs a deployment needs.

### Changed
- `ROOM_SYSTEM_PROMPT` and `_truncate` moved to `worker/marvin/adapters/prompt.py` (text unchanged; the Claude adapter
  re-exports `ROOM_SYSTEM_PROMPT`). `MODELS`/`DEFAULT_MODEL` moved from `admin.py` into the `claude-code` profile.
- Changing a room's harness starts a new conversation (the saved session id is dropped); model and linked-repo changes
  still resume.
- `.env.example` and `rooms.local.yaml` document `MARVIN_HARNESS`, `harness:` and the credential each agent needs.

## 2026-09-11 — Spin-out as Marvin

Marvin starts here as an independent open-source project. It was previously an internal tool called **Albi**; the
agent's wake word was already "Marvin", now the project, the Python packages and the UI carry the same name.

### Renamed
- Project, package and agent: Albi -> Marvin. `worker/albi/` -> `worker/marvin/` (pyproject name `marvin`, console
  scripts `marvin`, `marvin-web`, `marvin-gate`), `stt/albi_stt/` -> `stt/marvin_stt/` (`marvin-stt`), web
  `AlbiPane` -> `MarvinPane`, `useAlbi` -> `useMarvin`, `AlbiEvent` -> `MarvinEvent`, package `marvin-web`.
- Every `ALBI_*` environment variable is now `MARVIN_*` (worker, STT service, Dockerfile, compose, Makefile,
  Kubernetes manifests, CI).
- Wire protocol identifiers: data-channel topics `marvin` / `marvin-control`, agent identity `marvin`.
- Kubernetes namespace, labels, Service / StatefulSet / Deployment / PVC names: `albi*` -> `marvin*`.
- Makefile targets `albi-up/down/status` -> `marvin-up/down/status`; `deploy/albi-onoff.sh` -> `deploy/marvin-onoff.sh`.
- Agent git branch convention in the system prompt: `marvin/<room>/<topic>`.
- Local storage keys in the web UI (`marvin.room`, `marvin.name`, `marvin.columns`): saved room/name and column
  widths from the old UI are not carried over.

### Removed (company-specific integrations)
- **Private npm registry (AWS CodeArtifact)**: the `albi-npm-login` script, `deploy/aws/` (IRSA role script and
  domain policy), `worker/albi/settings.py` and its tests, the `/api/settings` and `/api/settings/codeartifact`
  routes, the "Private package registry" section and its warning in the web Settings panel, the CodeArtifact
  paragraph in the room system prompt, the AWS CLI layer in the Dockerfile, and the token refresh loop in the
  entrypoint.
- **AWS/ECR/Karpenter cluster specifics**: ECR image names and Makefile `ecr-*` targets, Karpenter node pool
  tolerations/affinity, the IRSA annotation on the service account, the internal ALB external-dns targets, the
  pinned company ClusterIP, private-zone Route53 record files (`deploy/k8s/turn-record.json`, `deploy/test/udp-*`).
- **Internal GitOps pipeline**: the CI no longer stamps image digests into a company GitOps repository; references to
  Argo CD, Vault and internal cluster names are gone from the READMEs.
- Company hostnames and VPN product names (replaced by `marvin.example.com`-style placeholders and a generic
  "clients behind a VPN/firewall that only allows hostnames" description of the relay-only ICE mechanism).
- The `CLAUDE_CODE_OAUTH_TOKEN` option in `deploy/k8s/secrets.env.example`; README and secrets example now say to
  use an `ANTHROPIC_API_KEY` (or commercial credentials) and not a personal Pro/Max OAuth token on a shared server.

### Changed
- **CI moved to GitHub Container Registry**: `.github/workflows/workflow.yaml` runs worker tests + web build, then
  builds and pushes `ghcr.io/<owner>/marvin` (`:latest` on `main`, `:sha-<short>`); `workflow-stt.yaml` does the
  same for `ghcr.io/<owner>/marvin-stt` and only when `stt/` changes. Both use `GITHUB_TOKEN`; pull requests build
  without pushing.
- Makefile: `image` / `stt-image` push to `$(REGISTRY)` (default `ghcr.io/<owner>` derived from the git remote, or
  override `REGISTRY=...`).
- `deploy/gen_apps.py` reads `domain`, `ui_host` and `ingress_class` from `rooms.yaml` instead of hardcoding them;
  `deploy/k8s/apps.yaml` regenerated.
- Gate (`worker/marvin/gate.py`) default timezone is `UTC` (still `TZ`-configurable); `gate.yaml` sets `TZ: UTC`.
- Entrypoint default git identity: `Marvin <marvin@example.com>` (override with `MARVIN_GIT_NAME` / `MARVIN_GIT_EMAIL`).
- README rewritten for a public audience; `deploy/k8s/README.md` rewritten as a generic `kubectl apply -k` example.

### Housekeeping
- Git history restarted: the public repository begins with a single initial commit. The previous history stays in
  the original internal repository.
- `worker/uv.lock` regenerated for the renamed package.
- No license yet ("License: to be decided" in the README).
