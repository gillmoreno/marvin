# Changelog

All notable changes to Marvin. Entries are dated; the newest is on top.

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
