# Security, compliance and the Enterprise Edition

Status: design decisions, 2026-09-11. This document is the source of truth for what Marvin must do before a public
release and what belongs in the paid Enterprise Edition (EE). Update it when a decision changes; do not fork it.

## 1. Product and business shape

- **Open core.** The public repo carries the free core under an OSI license (Apache 2.0 or AGPL, not yet decided) and
  an `ee/` directory under a Marvin Enterprise License: source visible, use requires a valid subscription.
- **Paid = organisation-only needs.** Everything an individual or a three-person team needs is free. Everything a
  security or compliance team asks for before approving the tool is EE. Never cripple the free tier to force upgrades.
- **Licensing mechanism.** Yearly subscription, per seat or per instance with a floor. Offline license key: a JWT signed
  by us, carrying expiry, seat count and enabled features, read from `MARVIN_LICENSE_KEY` and verified at worker start.
  No phone-home.
- **Self-hosted first.** Customers run Marvin in their own VPC/cluster/VM. We do not run a hosted tier until there is
  budget for our own SOC 2 Type II and a DPA with our own subprocessors.
- **Services** (installation, integration, support tiers) are sold on top of the license, not instead of it.

## 2. Vendor terms we must not violate

- **Anthropic.** OAuth tokens from Claude Free/Pro/Max are only for Claude Code and claude.ai; using them "in any other
  product, tool, or service, including the Agent SDK" violates the Consumer Terms (Feb 2026 update). Marvin drives the
  Agent SDK from a shared server for several people. Therefore: the Claude harness is documented and shipped for
  `ANTHROPIC_API_KEY` / commercial plan credentials only. Never market "share your Max plan with the room".
- **Other harnesses.** Each ACP-capable CLI (Codex, Cursor, Gemini, OpenCode, Grok Build, Copilot) has its own rules for
  subscription auth through a third-party client. Verify per vendor before advertising it; default to API-key auth in docs.
- **Enterprise data terms.** For the customer's compliance, the model provider must be under a commercial agreement
  (no training on inputs, zero data retention where offered, region pinning). Consumer plans do not provide this.

## 3. Current security findings (core, pre-release blockers)

Found in the code as of the spin-out. All must be fixed before the repo is public and marketed.

1. `GET /api/token?room=X&name=Y` mints a LiveKit token for any name: identity is self-asserted. Anyone can be anyone;
   `Requested-by:` trailers are unverifiable.
   **Status: addressed on `feat/edge-auth`** (identity from session cookie or trusted proxy headers, signed into the
   LiveKit token; see `authentication.md`). Password mode still lets two people pick the same name; header mode fixes that.
2. All `/api/*` routes proxy unauthenticated to the worker admin API: create/delete rooms, clone any git URL with the
   server's `GITHUB_TOKEN`, edit machine notes (`~/.claude/CLAUDE.md`, a prompt-injection point into every session).
   **Status: addressed on `feat/edge-auth`** (session required everywhere; `admin` for writes and for the notes).
3. Any participant can send `auto_approve`: arbitrary code execution in the pod for everyone in the room.
   **Status: addressed on `feat/edge-auth`** (`admin` role required, read from server-signed participant metadata).
4. The pod runs a **privileged Docker-in-Docker sidecar** with a GitHub token and a model-provider credential mounted.
   **Status: partly addressed on `feat/sandbox`** (`sandbox.md`): the agent no longer runs in the worker's process
   tree but in a per-room container with only its repos mounted and credentials forwarded per exec; the Docker
   daemon is not handed to the agent unless `MARVIN_SANDBOX_DOCKER_SOCKET=1`. Still open: the worker itself holds
   the daemon (compose: host socket; k8s: privileged dind), and the GitHub token is still the machine's, not the user's.
5. "Never commit on main" lives only in the system prompt. It must be enforced by branch protection / git hooks too. Open.

Fix order:

1. Identity at the edge (OIDC via oauth2-proxy/Caddy/ingress). The token endpoint takes the user from the
   authenticated header, never from the query string. Free tier: single shared password or basic OIDC; EE: full SSO.
   **Done** (`deploy/edge/`, password and header modes).
2. Roles on the wire: `viewer`, `participant`, `approver`, `admin`. Only approvers resolve write-tool permissions;
   `auto_approve` is admin-only (or removed); admin API requires `admin`.
   **Done for `participant`/`admin`**; `viewer`/`approver` remain EE.
3. Per-user git identity: GitHub App installation tokens or per-user device-flow login. Commits are authored by the
   requester. Removes the shared PAT.
4. Audit log: who asked, who approved, what tool ran with which arguments, what changed. Append-only, timestamped.
5. Agent isolation: per-room sandbox instead of the shared worker process (see section 6).
   **Done (core) on `feat/sandbox`**: `MARVIN_SANDBOX=docker`, one container per room, same-path mounts, credentials
   per exec, resource limits. Egress policy, gVisor/Kata runtime and per-room images remain EE (`sandbox.md`).

## 4. SOC 2 mapping (what a customer's auditor will ask)

SOC 2 certifies organisations, not software. Self-hosted Marvin is evaluated as an internal tool under the customer's
existing controls, which is much lighter than a SaaS vendor review. These are the criteria it touches and the required
answers.

- **CC6 Logical access.** Unique identities, no shared accounts, least privilege. Requires: SSO, roles, per-user git
  identity, repo-scoped tokens, no `auto_approve` for non-admins.
- **CC7 Monitoring.** Complete, tamper-evident audit trail. Requires: audit log with SIEM export (Splunk, Datadog,
  Elastic; syslog/JSON lines/webhook).
- **CC8 Change management.** Authorised, tested, reviewed changes. Requires: PR-only workflow, protected branches
  enforced by the git host, `Requested-by` + `Approved-by` trailers, tests before push.
- **CC9 Vendor management.** The model provider is the real third party. Requires: clear data-flow documentation of
  exactly what leaves the boundary (transcript since last turn, code the agent reads, machine notes, attachments),
  configurable provider/harness, option of self-hosted open-weight models via an ACP harness for regulated customers.
- **Supply chain.** Pinned dependencies, signed images (cosign), SBOM (CycloneDX/SPDX), dependency scanning in CI,
  `SECURITY.md` with a disclosure process, signed releases.

## 5. GDPR and privacy

Marvin's owner and early customers are in the EU. Transcripts are personal data; audio is more sensitive still.

- **Audio never leaves the customer boundary.** STT runs locally (faster-whisper in the pod, or Nemotron on the
  customer's GPU node). Keep this as a hard product property and a headline claim.
- **No audio storage by default.** Only transcripts and session state are persisted.
- **Transcription notice.** A visible "this room is transcribed and sent to <provider>" notice on join. Several
  jurisdictions require consent for recording.
- **Retention and deletion.** Configurable retention for transcripts, uploads (`/work/uploads`) and per-room session
  state; a "delete this room's data" action; documented data locations on the volume.
- **Data flow to the model provider** is covered by the customer's DPA with that provider; Marvin documents what is
  sent and lets the customer choose provider and region.
- **EU AI Act.** Coding assistants are not high-risk. Transparency obligations for AI interacting with people apply;
  Marvin announces itself as an agent in the room. State this in the security overview.

## 6. Deployment and isolation

- **Docker for the agent is a legitimate requirement** (build images, run compose stacks, test like production). The
  problem is *privileged Docker-in-Docker inside a shared Kubernetes pod*, not Docker itself.
- **Primary packaging: single-VM appliance.** One VM per team (any cloud or on-prem), Docker installed on the host,
  Marvin services via `docker compose`, the agent uses the host Docker daemon. The VM is the blast radius. Perimeter via
  OIDC at a reverse proxy (Caddy/oauth2-proxy), VPN (Tailscale, Firezone, WireGuard) optional. AWS Terraform lives in
  `deploy/aws` (`aws-terraform.md`); GCP and Hetzner examples still to write. This is what most buyers can actually
  install and what procurement understands ("deploy in your VPC").
- **Kubernetes stays as the EE/large-team option.** Remove the privileged sidecar by one of:
  - Sysbox runtime (unprivileged system containers that run Docker inside; needs a node-level install), or
  - Kata / gVisor sandboxed pods, or
  - no Docker daemon: builds via rootless BuildKit, runtime via ephemeral pods/Jobs created through a scoped
    ServiceAccount. Changes the developer experience; document the trade-off.
- **Per-room sandbox.** Core (shipped): each room's agent in its own container with its repos, its HOME and
  forwarded credentials only; the worker orchestrates (`sandbox.md`). EE: its own Docker (sysbox/Firecracker,
  rootless nested daemon) instead of the host socket, gVisor/Kata runtime, egress allow-list, per-room image.
- **Secrets** live in the platform's secret store (Kubernetes Secrets from Vault/ESO, cloud secret manager on a VM),
  never plaintext env files in the repo. Rotation documented.
- **Pod Security Standards.** Target `restricted` for all Marvin containers except the sandbox runtime.

## 7. Enterprise Edition feature list (the "compliance pack")

The compliance list and the EE list are the same list.

- SSO / OIDC / SAML, SCIM provisioning
- Roles and approval policies (who may approve which tool classes, per room and per repo)
- Per-user git identity via GitHub/GitLab App
- Audit log with SIEM export and retention policies
- Data retention / deletion controls, transcription consent banner text
- Multi-team / multi-tenant rooms with per-room sandboxes
- Hardened deployment: Helm chart, sysbox/Kata option, Pod Security Standards `restricted`
- GPU streaming STT deployment
- Signed images, SBOM, support SLA

## 8. What we, the vendor, must provide

- A two-page **security overview**: architecture, data flow, what leaves the cluster, credential handling.
- A pre-filled **CAIQ** (or SIG Lite) questionnaire.
- `SECURITY.md` in the repo with a disclosure process and response times.
- Release process: signed tags, signed images, changelog, CVE handling.
- No SOC 2 needed while self-hosted only. Required before any hosted tier: SOC 2 Type II plus GDPR DPA and
  subprocessor list.

## 9. Open decisions

- Core license: Apache 2.0 (friendlier to adoption) vs AGPL (protects against a third party hosting it first).
- Name/trademark check for "Marvin" before it appears on a pricing page.
- Which harnesses may be advertised with subscription auth (per-vendor verification pending).
