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
  (set from Settings → GitHub). Harness credentials followed the same day (Settings → Coding agents: API key
  paste for every vendor, plus Grok device-flow subscription login). Still open: `GITHUB_TOKEN`/machine identity,
  sandbox options, admin users. Rationale: Gil's own experience as the first user — copy-pasting into a form is less friction than
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
- **Themes paint; they do not rearrange the chrome.** Settings as a centered dialog and a wrapping left-footer
  (LiveKit's extra device-menu chevron) showed up in Editorial/Signal because those themes restyled layout, not just
  colour. Decision: the room chrome lives in `web/src/styles.css` (full-page Settings, four icon buttons in one row,
  phone one-pane). A theme recolours and retypes that skeleton. Enforcement is the contract + the skill ("do not set
  a max-width on `.modal`, do not wrap `.left-foot`"), not a CSS linter — theming is not a core product surface.
- **App preview hosts are children of this install, not a Marvin-wide domain.** A wildcard A record points at one
  IP. `*.marvin.aigil.dev` is the Frankfurt pilot, not every customer VM. Using `aigil.dev` for every install would
  make us the hosted edge for other people's running apps (name, abuse, GDPR). Deferred with the hosted tier.
  Formula: `https://p{port}.{MARVIN_DOMAIN}`. Each install sets its own hostname and `*.that-name` DNS (grey-cloud).
  TLS is one cert per preview name (Caddy on-demand, gated by `/tls-ask`), not a wildcard cert. Write-up:
  `app-previews.md`.
- **The room tells the truth about the agent.** First live Grok session: STT and “listening” / “working” stayed
  up while the harness was missing, unsigned-in, or on a dead network. Native `alert()` for `AcpError`. Decision:
  if the agent cannot answer, the pane says so in a sentence and points at the next click (Settings). No
  interactive CLI login from a headless room (device flow belongs in Settings). No browser `alert()` for room
  operations. A room that looks live with a dead turn queue is a bug, not a timeout.
- **Send is local first.** Clearing the composer and waiting for LiveKit + the harness to echo `turn_start`
  made typed asks look like they disappeared — worse when a turn was already running and the next one sat
  in the queue. The click paints the transcript line and the turn immediately; the worker also announces
  `turn_start` at enqueue (with `queued` if busy) so everyone else sees it too. Tool events still attach to
  the running turn, not the queued one.
- **Updates are in Settings, not SSH.** The appliance is a checkout; staying on the clone from first boot
  is how testers miss Send fixes. Admin Settings lists the commits on `main` this VM does not have and
  applies `deploy/edge/update.sh` (same as `make update`). `.env` stays. First box still needs one manual
  pull so the button exists; after that, the browser is enough. Write-up: `updates.md`.

## 2026-09-13

- **AWS installer is a Terraform root module, not a shell script.** First cut (`deploy/aws`): new throwaway
  stack (does not import the Frankfurt pilot); `apply` ends on a URL after cloud-init (`git_ref`, default `main`);
  Route 53 if you pass a zone, otherwise print the Elastic IP; passwords are Terraform variables stored in SSM
  and copied into `.env`; LiveKit keys and the session secret are generated on the disk only; tell the operator
  *where* those files are, never dump them in outputs. Default `c7i.xlarge`, `public` or `private` access,
  SSM always, SSH only with a CIDR. No baked AMI, no Cloudflare provider, no VPC creator, no blocking health
  wait. A private `git_repo` needs `git_token` in SSM (clone on first boot only; not in `.env` or user-data).
  Write-up: `aws-terraform.md`.
- **Join gate, not a wizard or an in-room takeover.** First-run lives on the join page. Three steps: this
  machine’s GitHub (required, admin, once), a coding agent (required, admin, once), your GitHub (optional,
  never blocks Join). People are identified by Marvin login (prefer email); GitHub is how the box talks to
  repos, plus an optional author line for programmers who want their name on commits. Rejected: “everyone
  must connect GitHub” (Alex has none) and “shared only” (programmers need the author line). Device flow
  opens the URI that already contains the user code; a pasted PAT is the escape when GitHub’s confirmation
  is blank. Write-up: `github.md`.

## 2026-09-14

- **Licenses are GitLab / PostHog, not a new text.** Root `LICENSE` is their
  preamble plus MIT (everything except `ee/`). `ee/LICENSE` is their
  Enterprise paragraph with the product name swapped: production needs a paid
  subscription; dev/test does not. Cal.com’s AGPL core and Mattermost’s
  AGPL-source / MIT-binary split were left alone. No terms URL yet (written
  agreement).   JWT verify and Settings → Enterprise shipped; `ee/` is still a
  skeleton (no compliance features yet). Write-up: `licensing.md`.
- **Company pack 0–5 in one run.** Paid = org-only. Free core keeps domain
  allow-lists and a local session JSONL (needed for authorship). License gates
  OIDC save, S3/webhook export, and the GitHub App. Identity of record stays
  Marvin login; personal GitHub stays optional. Machine GitHub App is the
  company shape; a PAT still works. Audit is hash-chained JSONL on disk, HMAC
  at close, export only to *their* S3 or webhook. AWS: Packer AMI + Terraform
  `ami_id`; Cosign skipped. Out: SAML, SCIM, Helm, gVisor, GPU STT,
  `viewer`/`approver`. Plan: `ee-company-pilot.md`.

## 2026-09-15

- **Appliance update is a sibling container, not a child of the worker.**
  `docker compose up --build` recreates the worker; a script running in that
  process dies (137) and Settings only saw 503. `marvin-update` shares the
  socket, the checkout, and `marvin_work`. The token server reads
  `update.json` / `update.log` from the volume so the page has a live log
  while the worker is gone. GitHub compare is skipped while applying (rate
  limit). Write-up: `updates.md`.
- **One Workspace design, no theme platform.** The Workspace prototype won:
  projects are the primary surface, machine readiness and personal GitHub are
  compact, and updates are visible before joining. Custom themes made visual
  quality impossible to maintain and distracted from the core workflow, so
  the picker, loader, API, sandbox mounts, and agent theme skill are removed.
  Presence remains a fixed product component.
