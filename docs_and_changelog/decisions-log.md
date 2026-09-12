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
- **Audit trail and authorship, refined the same morning** (roadmap item 8). `Requested-by:` written by the model is
  not evidence: the model can get it wrong or be talked into it, and git metadata is freely editable. Decisions:
  - The identity of record is what Marvin verifies at login (SSO, or email + password), not a GitHub account.
    Non-developers take part without one; the per-user GitHub token is optional.
  - Password mode asks for email; `Identity.id` is the email in every mode. Self-asserted there, constrained by
    allowed domains / an allow-list; verified in header mode.
  - Every commit is authored by the human who asked (author), committed by `marvin[bot]` (committer), signed with
    Marvin's key; trailers `Requested-by`, `Approved-by`, `Marvin-Session`, `Marvin-Turn` stamped by a git wrapper
    and a commit-msg hook the model does not control. Enforcement at push: author and turn must match the log.
  - Git carries pointers, Marvin holds the content: a session is a meeting (room goes occupied → empty), with an
    id; a hash-chained, signed JSONL per session records participants and presence, transcript, turns and prompts,
    tool calls, approvals, commits/pushes/PRs. Never a transcript in a commit or PR (privacy, and GDPR deletion is
    impossible in git history). Recording notice, configurable retention, per-person redaction.
  - Order: email identity → sessions + audit log → git wrapper/hooks/signing → push verification → GitHub App as
    machine identity → repo picker. This goes before the multi-repo project work.
- **Design principle: configuration happens in the browser, not in `.env`.** Anything that can safely be entered
  from the UI is entered from the UI (admin-only where it matters, masked when it looks like a credential, stored by
  the worker in its state dir, encrypted when it is a secret). Environment variables remain as an override for
  automation and for the handful of things that must exist before the UI does (LiveKit keys, the auth mode, the
  session secret). Guided steps beat instructions: when Marvin needs something from an external service, Settings
  links to the exact page, says what to click, and takes the paste. First applied to the GitHub OAuth client id
  (set from Settings → GitHub); next candidates: harness API keys, `GITHUB_TOKEN`/machine identity, sandbox options,
  admin users. Rationale: Gil's own experience as the first user — copy-pasting into a form is less friction than
  editing a file and restarting, and a hosted or appliance install has no `.env` to hand.
- **Themes are data + CSS, never code; Marvin writes them.** Of the three design prototypes (`design-explorations/`)
  Control Room is the default and the other two ship as choices. To make new themes "vibe codable" without letting
  a theme break the app, a theme is `theme.json` (tokens, fonts, presence variant) plus plain CSS that the loader
  scopes to `html[data-theme=id]` via the CSSOM; the app keeps a fixed, documented set of class names as the
  contract and draws the voice-presence variants itself (`scope`, `bars`, `ink`, `orb`, `ring`, `dot`) from the
  agent state and audio level. Custom themes live in `<state_dir>/themes/`, which is mounted into every room
  sandbox (`MARVIN_THEMES_DIR`) with the contract as its README; the worker validates (reserved ids, schema, no
  `@import`/foreign `url()`), lists invalid ones with the reason and never serves their CSS. Claude Code gets a
  user-level skill in each room HOME; other harnesses get one line in the room prompt. Choice is per browser,
  default per machine from Settings (admin), `MARVIN_THEME` as the env override. Rejected: tokens-only themes (could
  not carry the three prototypes' character), JS/React themes (unbounded blast radius), themes inside the project
  repo (pollutes the customer's code). Write-up: `theming.md`.
