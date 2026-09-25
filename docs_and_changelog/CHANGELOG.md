# Changelog

All notable changes to Marvin. Entries are dated; the newest is on top.

## 2026-09-25 — Colored diffs

### Changed
- A file’s diff shows additions in green and deletions in red, and formats TypeScript, Python, Go, Rust, C, C++, HTML, Markdown, and the other common languages.

## 2026-09-25 — A quiet room

### Changed
- Inside a room, changed files sit in a folder tree on the left, with search. Transcript and Marvin take the rest of the window.

## 2026-09-25 — Room settings stay with the room

### Changed
- Opening settings for a room shows only that room. The control is **Room settings**, next to the room name. Sign-in, GitHub, and the rest of the machine stay under Settings.
- A room you enter stays on the sidebar with Projects. Settings sits at the bottom of the sidebar, just above your name.
- Opening a room slides the sidebar away. The room fills the window, with Projects and Room settings in its top bar. Leaving the room brings the sidebar back.
- The sidebar is a normal size again. Inside a room, the Marvin logo and a back link sit in the top bar, and both return to Projects. Changes uses the same connected tab as Settings.

## 2026-09-25 — A fuller sidebar

### Changed
- Projects and Settings in the sidebar are large rows with much bigger icons. The mark, your name, and the role are larger too.

## 2026-09-25 — Settings has more room to read

### Changed
- Settings type is larger, and the page, tabs, and cards have more space between them.

## 2026-09-25 — Settings sections are tabs under the title

### Changed
- Settings no longer has a second sidebar. Sign-in, GitHub, coding agents, and the rest sit in one row under the title. The open section shares the card and is marked with a teal line.

## 2026-09-25 — One dark theme for the room and Settings

### Changed
- The project workspace (diff, room bar, transcript, people) uses the same dark canvas as Projects and Settings. Settings cards are dark panels, not white islands on a dark page.

## 2026-09-24 — Transcript lines have a name, a time, and the words

### Changed
- Each transcript line is a block: the time in a quiet column, the speaker’s name, then the words underneath. A person who keeps talking does not get their name repeated on every line.
- An email used to sign in shows as a name (`maria.santos@acme.com` → Maria Santos). The address is still there on hover, in the room list as well as the transcript.

## 2026-09-21 — Room First dark theme for Projects and Settings

### Changed
- Projects, join screen, setup, and settings pages now use the Room First dark canvas: near-black backgrounds (#0f1115), dark cards (#161920), light text (#e8eaef), and teal accent (#2dd4bf).
- Ready/ok indicators switched from green to teal to match the unified palette.
- Room conversation chrome (center workspace and right transcript) remain intentionally light in this version.

## 2026-09-20 — Empty language still transcribes

### Fixed
- Leaving `MARVIN_LANGUAGE` blank (autodetect) no longer crashes local Whisper, so the transcript pane fills while you talk.

## 2026-09-20 — Stale saved conversation starts a new one

### Fixed
- If a room’s saved coding-agent session id is gone (new volume, pruned history), the room starts a fresh conversation instead of joining LiveKit with a dead agent. Other harness start failures (not signed in, missing binary) still keep the room up so a later message can retry.

## 2026-09-20 — AWS AMI: seed .env and fix docker group

### Fixed
- Packer AMI bake now seeds `.env` from `.env.example` before running `make sandbox-image`, fixing the `Makefile:2: .env: No such file or directory` error.
- Image builds now run with `sg docker -c '...'` after `usermod -aG docker ubuntu` to ensure docker group membership is active.

## 2026-09-19 — Marvin mark

### Changed
- The sidebar and sign-in rail use the Marvin lockup: gold speech circle, cream word, live gold pip on the i. Fold the rail and the square mark stays. The browser tab uses the mark.

## 2026-09-19 — Refined icon-only rail

### Changed
- Collapsed sidebar is now a cleaner icon-only rail (~60px instead of 72px) with better icon centering, clearer expand affordance, and improved visual hierarchy. Expanded rail remains unchanged.

## 2026-09-17 — Coding agents lead with Grok

### Changed
- Settings → Coding agents opens on Grok. Sign in with grok.com is the first action; an API key is a secondary paste. Other providers are under Add another.
- When Grok is the only connected agent, it becomes the default for rooms that do not pin one.
- The default picker is no longer locked by `MARVIN_HARNESS=claude-code` in `.env`. Claude Code stays the built-in default in code. Settings wins; the environment only seeds a default when Settings has not picked one.

## 2026-09-17 — Enterprise settings lock

### Changed
- Without a license, Settings locks who may join, company sign-in, audit export, and creating a GitHub App. A 🔒 sits on the title, the body dims, and a gold line points at Enterprise to paste a key. A pasted GitHub token, coding agents, and the local session log stay open.

## 2026-09-17 — Company name under Marvin

### Changed
- The sidebar is one reusable rail (`Sidebar`) on every page.
- On an Enterprise machine the company name sits under Marvin, as the gold badge. There is no company line without a license.
- Collapse is a chevron to the right of Marvin. The company badge sits under Marvin, left-aligned.
- Projects and Settings keep their labels when the rail is open.
- Settings → Sign-in stacks each field under its label, so words and inputs are not jammed on one line.
- Settings forms share one UI kit (card, field, button). GitHub, coding agents, sessions, audit, Enterprise, and this machine use the same card.
- Settings → Enterprise shows the company, seats, and expiry when a license is already on the machine. The paste box stays hidden until you replace it. The string is masked like an API key. A pasted key has no “set here” label; the page only names the origin when `MARVIN_LICENSE_KEY` is holding it.

## 2026-09-16 — One sidebar, and projects are pages

### Changed
- Projects, the room, setup, and Settings share the same sidebar (Marvin, Projects, Settings, who you are).
- The sidebar can be collapsed to icons. This browser remembers the choice.
- A project is an address (`/projects/dev`). Settings stays `/settings`. The browser Back button leaves a room the same way it leaves Settings.

## 2026-09-16 — Enterprise mark and Back from Settings

### Added
- A licensed machine shows a gold company badge next to Marvin (projects rail, setup, the room, and Settings).
- Settings is a real address (`/settings`, `/settings/github`, …). The browser Back button, and a Back link in the header, leave it the way a page would.

## 2026-09-16 — Settings is a guided Sign-in page

### Changed
- The projects rail has one **Settings** item. Sessions live inside that page, not as a second button that opened the same place.
- Settings is one pane at a time, with a dark rail: Sign-in, GitHub, coding agents, sessions,
  audit, Enterprise, this machine.
- Sign-in walks through the identity provider (Entra, Okta, Google, GitHub, Keycloak, or a
  local test login): the clicks, the redirect URL to copy, then issuer / client / secret.
- Admins can open Settings from the setup page, so company sign-in and the license are
  reachable before the machine is ready.
- `make sso-dev` puts Dex + Caddy on `http://127.0.0.1:8088` in front of the host Vite / token
  loop so SSO can be tried without a real tenant. `maria@acme.com` / `maria` is admin;
  `alex@acme.com` / `alex` is a participant.

## 2026-09-16 — Setup is a hard gate

### Changed
- A fresh machine is a dedicated setup page until it has a shared GitHub account and at least
  one coding agent. Projects and sessions stay hidden. Admins can still open Settings to
  connect company sign-in or paste a license. Participants see a waiting page. After both
  connections exist, the projects workspace comes back with those two as quiet status;
  personal GitHub stays optional.
- **Create a GitHub App** on that setup page accepts the Enterprise license there, so you do
  not need Machine settings first.
- **Paste a token** walks through creating a fine-grained GitHub PAT: the exact page, which
  owner and repos to pick, and the two permissions Marvin needs.

## 2026-09-15 — Workspace UI and updates you can follow

### Added
- The join screen puts projects first, with compact machine-readiness checks,
  update availability, **What changed**, and **Update now** in a narrow rail.
- Human-readable product updates live in `product-updates.json` and appear
  inside Marvin rather than requiring people to read commit messages.

### Changed
- Sign-in, project selection, the room, and Settings now use one fixed
  Workspace design: a dark navigation rail with quiet light work surfaces.

### Fixed
- Settings → Update no longer runs `update.sh` inside the worker. Compose was
  killing that process mid-rebuild (exit 137), so the page only showed
  “worker unreachable”. A sibling container writes `update.log`; the web
  process serves it even while the worker is down. Docs: `updates.md`.

### Removed
- Built-in and custom themes, the Appearance picker, theme API, sandbox theme
  mounts, and theme-writing agent instructions. Marvin now has one maintained
  visual system.

## 2026-09-14 — Company pack: SSO, audit, GitHub App, AWS AMI

### Added
- Settings → **Sign-in and notice**: allowed email domains, allow-list, admin groups, recording notice,
  OIDC issuer / client (writes `.oauth2-proxy.env` for `make edge-oidc-up`). Env still wins.
- Password and header login refuse addresses outside the domain list (403, not 401).
- Hash-chained session JSONL under the state dir, HMAC at close, Settings → **Sessions**, retention.
- Settings → **Audit export**: S3 and/or a JSON webhook when a meeting closes. No phone-home.
- GitHub App manifest flow (Settings / join gate). Installation tokens replace a shared PAT.
  Sandbox `git` wrapper + `commit-msg` / `pre-push`: author is the Marvin identity, committer
  `marvin[bot]`, trailers we stamp, push refused if the turn is not on the audit log.
- Packer AMI (`deploy/aws/ami.pkr.hcl`) and Terraform `ami_id` so first boot skips the 15-minute build.

### Changed
- The web container mounts `marvin_work` so the token server reads the same `access.json` as the worker.
- oauth2-proxy reads `.oauth2-proxy.env` (Settings), not only `.env`.
- LiveKit participant metadata now includes `email` when Marvin knows it (commit author).

## 2026-09-14 — Open core licenses and an empty `ee/`

### Added
- Same license split as GitLab / PostHog: MIT outside `ee/` (`LICENSE`),
  Enterprise license in `ee/LICENSE`. The folder is a skeleton (no SSO / audit
  / isolation code yet).
- Offline license JWT: Settings → **Enterprise** (admin) or `MARVIN_LICENSE_KEY`.
  We mint keys with `make issue-license`; the worker verifies with
  `worker/marvin/license.pub`. No phone-home. Docs: `licensing.md`.

## 2026-09-13 — Join gate: machine GitHub, an agent, optional personal GitHub

### Added
- Join page is a three-step gate. **This machine’s GitHub** and **a coding agent** are required (admin, once).
  **Your GitHub** is optional and never blocks Join. The page says who you are logged in as (email, else name).
  Password login asks for email. `GET /api/setup` is what the page polls.
- Machine GitHub account (`PUT /api/github/machine`, or `GITHUB_TOKEN`): shared clone/push/PR identity. Commits
  say Marvin unless the asker attached their own GitHub. Personal PAT (`PUT /api/github/me`) is self-service.
- Device-flow links include the user code. **GitHub went blank** / **paste a token** is the escape hatch (no
  client id needed for a PAT). Docs: `github.md`.

## 2026-09-13 — Immediate feedback and in-app updates

### Added
- Settings → **This machine** (admin): commits on `main` that this VM does not have, and **Update this
  machine** (`git pull` + rebuild). Same script as `make update`. Docs: `updates.md`.

### Fixed
- Typing a question and hitting Send paints the line and the turn at once (and on the transcript). A follow-up
  while Marvin is still working shows as queued instead of vanishing until the current turn ends. Allow/Deny
  also clear the banner on click.
- Caddy `caddy:2` no longer accepts `on_demand_tls interval` / `burst`; the preview catch-all only uses `ask`.

## 2026-09-13 — AWS Terraform appliance

### Added
- `deploy/aws`: Terraform root module that boots a new VM (Elastic IP, optional Route 53, SSM, cloud-init
  `edge-up`). Apply returns when the AWS objects exist; the room is ready when `/healthz` is 200. Outputs say
  where secrets live, never the values. Private origin repos take `git_token` (SSM, clone-only). Docs:
  `aws-terraform.md`.

## 2026-09-12 — HTTPS app previews under this install's hostname

### Added
- Edge stack: a listening port becomes `https://p{port}.{MARVIN_DOMAIN}` (Caddy on-demand TLS, nginx to the worker).
  Settings → **App previews** shows the pattern. Docs: `app-previews.md`.
- `GET /tls-ask` (unauthenticated): Caddy may issue a certificate only for a preview host of this machine.

### Changed
- App links prefer `MARVIN_DOMAIN` (child hosts) over the older k8s `marvin-{port}.{parent}` shape, which still
  works when only `MARVIN_APPS_DOMAIN` is set.

## 2026-09-12 — Leading "Marvin" after a pause

### Fixed
- Saying "Marvin," then pausing no longer starts a junk turn on the name alone. The next utterance from the same
  speaker (about 8s) is the question.
- Local Whisper no longer prompts with `"Marvin, Marvin."`, which made the `small` model omit a leading spoken
  "Marvin". It now uses a full-sentence prompt and the `Marvin` hotword.

## 2026-09-12 — Coding agents from Settings

### Added
- Settings → **Coding agents**: connect Anthropic, xAI/Grok, OpenAI, Gemini, Cursor and Copilot from the
  browser. API keys are encrypted in the worker state dir; the environment is only an override. Grok also
  has **Sign in with Grok** (device-code flow, your grok.com subscription). Default harness is a select on
  the same panel. Docs: `harness-credentials.md`.

### Fixed
- Grok device login now mounts the `marvin_work` volume (the host Docker daemon cannot see the worker's
  `/work/state/...` path). Without that, xAI signed in and Marvin never stored the session.
- A harness that fails to start (Grok waiting for sign-in, 90s timeout) no longer leaves the room
  listening with a dead turn queue. Signing in with Grok restarts rooms that are on Grok.
- Restarting the worker no longer leaves room sandboxes on a dead network namespace (Grok DNS
  retries of `cli-chat-proxy.grok.com`).
- The room no longer hangs 90s on Grok’s interactive login, nor pops a browser `alert()` when a
  harness fails to start. Failures show in the pane (“Sign in with Grok”, “not installed”, “still
  waiting”).

## 2026-09-12 — Themes paint; the chrome stays put

### Changed
- Settings is a full-page screen and the left footer is four icon buttons in every theme, not just Control Room.
  That structure lives in `web/src/styles.css`. Themes recolour it; the skill and the theme contract say not to
  turn Settings back into a dialog or wrap the footer.

## 2026-09-12 — Control Room matches the prototype

### Changed
- Control Room is now a close port of `design-explorations/a-control-room.html`: Settings is a full-page screen with
  a two-column card grid; the left column pins a footer of square controls (settings / mic / share / leave); the
  status rail shows branch, harness, model, live and the session clock around a full-width oscilloscope; the
  transcript is a time · speaker · line grid; Marvin's header is two rows with harness/model tags. Shared hooks
  (`.left-head`, `.left-foot`, `.rail-cell`, `.sgrid`, `.role`, `.who-st`) so the other themes keep their own layout.

## 2026-09-12 — Themes: three built in, the rest vibe-coded

Design: `theming.md`. Contract: `worker/marvin/theme_docs/README.md`. Prototypes: `design-explorations/`.

### Added
- A theme system for the web UI. A theme is `theme.json` (name, dark/light, Google Fonts, presence variant, tokens)
  plus an optional `theme.css`, scoped to `html[data-theme="<id>"]` by the loader through the CSSOM. Data and CSS
  only, never code. `web/src/theme/{themes.ts,ThemeContext.tsx,Presence.tsx,ThemeSection.tsx}`.
- Built-in themes **Control Room** (default: dark instrument panel, status rail with an oscilloscope, JetBrains Mono
  + IBM Plex Sans Condensed, amber), **Editorial** (light paper, Fraunces, voice as ink) and **Signal** (graphite glass,
  one mint radial signal element). `web/src/theme/builtin/`.
- Voice presence drawings driven by the agent state and the real audio level: `dot`, `scope`, `bars`, `ink`,
  `orb`, `ring`; themes pick one for Marvin and one for speakers. `--level` is kept live on the element.
- Settings → **Appearance**: pick a theme for this browser, follow the machine default, admins set the default and
  remove custom themes; invalid themes are listed with the reason and cannot be turned on.
- Custom themes under `<state_dir>/themes/<id>/`, validated by the worker (`marvin/themes.py`): reserved ids, schema,
  token values, CSS size, `@import`, `url()` (data: and Google Fonts only), `expression(`, `javascript:`.
  `GET /api/themes`, `GET /api/themes/{id}/theme.css`, `PUT /api/themes/default` (admin), `DELETE /api/themes/{id}`
  (admin). `MARVIN_THEME` overrides the default. Tests: `tests/test_themes.py`.
- **"Marvin, make me a theme."** The themes directory is mounted into every room sandbox and named by
  `MARVIN_THEMES_DIR`; the worker writes the contract into it as `README.md` and installs a Claude Code skill
  (`~/.claude/skills/marvin-theme/SKILL.md`) into each room HOME; the room prompt points other harnesses at the
  README. The UI re-reads the theme list when a turn ends and offers "New theme X · try it".
- A phone layout for the room (`web/src/Mobile.tsx`): one pane at a time (Marvin, Transcript, Changes, apps, shared
  screens), a bottom bar with a large talk/mute button and leave.
- A status rail across the top of the room (`.rail`: room, state lamp, presence, who is speaking, session clock),
  shown by themes that want it.

### Changed
- `web/src/styles.css` is now a token-based base stylesheet (`--bg --panel --panel-2 --line --fg --fg-2 --dim
  --accent --accent-fg --sel --ok --warn --warn-bg --bad --exec --read --write --ins-bg --del-bg --glow --font-ui
  --font-display --font-mono --text --radius --radius-lg --shadow --left-w --right-w`). Class names are the stable
  theme contract from now on.
- `People` rows carry `data-speaking` / `data-away` and a presence drawing per person; the room `.layout` carries
  `data-state`.

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
