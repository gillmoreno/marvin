# Changelog

All notable changes to Marvin. Entries are dated; the newest is on top.

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
