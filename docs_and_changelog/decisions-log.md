# Decisions log

Compact record of what was decided and why, so a new session (human or agent) can pick up without the chat history.
Newest at the bottom of each day. Product direction lives in `roadmap.md`, security in `security-and-compliance.md`;
this file is the "why we did it this way" layer on top.

## 2026-09-11

- **Spin-out.** The code started as CardoAI/albi. It is now an independent project, Marvin, at
  github.com/gillmoreno/marvin, with no company references, a fresh history and no CardoAI origin. Name check on
  "Marvin" (trademark) still open.
- **Business model: open core.** Core in the open (license undecided: Apache 2.0 vs AGPL), Enterprise Edition under
  `ee/` with a commercial license and an offline JWT license key. Self-hosted first. No hosted tier until Marvin has
  its own SOC 2. What enterprises pay for is the compliance list: SSO, audit, policy, isolation, support.
- **Compliance stance.** Audio never leaves the customer boundary (STT runs on their machine); transcription notice
  and retention are the customer's GDPR controls; Marvin's EE roadmap is the SOC 2 CC6-CC9 mapping. EU AI Act:
  minimal-risk. Written up in `security-and-compliance.md`.
- **Anthropic terms.** Pro/Max OAuth tokens are not allowed outside Claude Code/claude.ai; Marvin ships API-key auth
  only and never markets "share your Max plan".
- **VM before Kubernetes.** Gil used k8s only to get behind the VPN; DinD was for testing with containers. Decision:
  VM appliance (compose) is the primary package, Helm/k8s an EE option on demand.
- **ACP adapter.** One adapter, eight harness profiles (Claude SDK, Claude ACP, Codex, Cursor, Gemini, OpenCode,
  Grok Build, Copilot). Grok verified live. Live model list from the running agent.

## 2026-09-12

- **Identity at the edge with Caddy.** Modes `password` / `header` (oauth2-proxy) / `none` (loopback dev). Roles
  `participant` / `admin` signed into the LiveKit token; admin-only for writes, notes, "always allow". Chosen over
  building a user database: the identity provider is the customer's.
- **Screen share** was published but never rendered; now a tab per shared screen in the middle column.
- **Transcript timestamps** are wall clock (they were seconds since the worker joined the room).
- **Positioning.** The unit of work is the project, not the repo; multi-repo web apps run as one testable unit is the
  differentiator. Core is stack-agnostic; Docker is the room runtime, not a rule about the app; Gil's nginx-static +
  backend + Postgres monolith is a blueprint for new projects, never enforced. No consumer/vibe-coder hosted product
  for now. Full text and order of work in `roadmap.md`.
- **Room sandbox** (roadmap item 1) shipped on `feat/sandbox`: one container per room, same-path mounts,
  credentials per exec; `host` network by default so app ports keep working. Egress policy, gVisor, rootless Docker
  for the agent are EE. Not yet verified against a live daemon (Docker Desktop would not start from the CLI).
- **GitHub identity today**: one token per machine (`GITHUB_TOKEN`), or the operator's own keychain in local dev;
  humans appear only in the `Requested-by` trailer. Different accounts are not handled.
- **GitHub identity, decided direction**: connect from the browser, nothing in `.env`. Per-user tokens via GitHub's
  device flow ("Connect GitHub" in Settings shows a code, the user confirms on github.com), stored encrypted by the
  worker, handed to git/gh per turn through a credential helper that asks the worker who is requesting; machine
  identity via a GitHub App created with the manifest flow (create + install in the browser) instead of a PAT.
  Commits and PRs are then authored by the human who asked, which is also the audit answer. See roadmap item 7.
