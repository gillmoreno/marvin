# Roadmap

Product direction and the order of work, as decided in conversation. Dated; newest decisions at the top of each
section. Security and compliance items are tracked in `security-and-compliance.md`; this file is about the product.

## Positioning (2026-09-12)

- Marvin is a voice room with a coding agent in it, for web development teams. Self-hosted first; the Enterprise
  Edition adds SSO, audit, policy and sandboxing (see `security-and-compliance.md` §7).
- The unit of work is the **project**, not the repository. A room is a project; a project may span several repos.
  This is the main differentiator against repo-centric agents (Cursor, Claude Code, Codex, Devin, Copilot).
- Marvin is **stack-agnostic in core**. It never tells a team how to build their app. It demands three properties of
  a project and is indifferent to how they are achieved: one command brings it up, one origin serves it, what was
  tested is what ships.
- Docker is the **room's runtime** (sandbox for the agent, generated compose stack for the project), not a rule about
  the app's stack. Inside the sandbox anything can run: Rails, Django, Go, Flutter web.
- Opinionated stacks are **blueprints** used when a project is created from nothing, never enforced on existing
  repos. First blueprint: React static behind nginx + backend of choice + Postgres in compose, backend not public.
- A consumer / vibe-coder product (hosted, blueprint mandatory) is **not** on the roadmap. It would need a hosted tier
  (own SOC 2, abuse handling, per-user sandboxes) which is deferred until the self-hosted business exists. If it ever
  happens it is the same blueprint made mandatory plus hosting, not a second codebase.

## Project shapes Marvin must handle

The axis is "where does the run-it-all knowledge live", not repo count.

1. Framework monolith (Django, Rails, Laravel, Symfony): the framework defines how it runs. Detection only.
2. Polyglot monolith with compose (React + Go/Python + db in one repo): the compose file is the manifest. Detection only.
3. Monorepo with several deployables (Turborepo, Nx, `apps/web` + `apps/api`): one repo, behaves like 4.
4. Multi-repo (frontend deployed as static site, one or more backend repos, database, externals): the manifest exists
   nowhere; it is spread across `.env.example`, CORS settings, IaC, CI and people's heads. **This is the product.**

## The project manifest

Lives in Marvin's state, not in any one repo (it spans them). Versioned, editable in the UI, assembled once per project.

- repos: url, branch, path, role (frontend, api, worker, shared-lib)
- services: how each runs (its Dockerfile, its compose file, or a command), port, health check
- wiring: env vars that connect services (`VITE_API_URL`, `DATABASE_URL`, `CORS_ORIGINS`, ...)
- data: db image, migrations command, seed/fixture, fake accounts
- externals: what the app talks to that is not yours (S3, Cognito/Auth0, Stripe, SES) and the local stand-in
  (LocalStack, mock issuer, sandbox tenant, stub)
- entrypoint: the one URL that is "the app"

From it Marvin generates one compose overlay per room: builds each repo, adds db and stand-ins, injects the wiring,
puts a small nginx/Caddy edge in front so the whole project is a single origin on one port (the preview in the middle of
the room). The same stack is the room's sandbox.

Sources, in order: discovery (Dockerfile, compose, `.env.example`, package scripts, framework config, OpenAPI, CORS,
CI workflows, IaC), then asking the room out loud for what discovery cannot settle, then persistence.

Known hard parts: auth between services (frontends pointing at a real IdP need a dev stand-in), externals (replicate
contracts, not infrastructure: no CloudFront/API Gateway locally), version pairing (branch per repo per room),
build time (N images per room; cache and rebuild-only-what-changed from day one).

## Order of work

Done: ACP adapter (one adapter, eight harness profiles), live model list, edge authentication and roles with Caddy,
screen share, transcript clock, Docker room sandbox (`sandbox.md`).

1. ~~**Docker room sandbox.**~~ Shipped 2026-09-12: one container per room, same-path mounts, credentials per exec,
   `host`/`container:`/`bridge` networks, limits; image in `deploy/sandbox`. Left for EE: egress allow-list,
   gVisor/Kata, rootless nested Docker for the agent, per-room image from the manifest.
2. **Project model.** `linked` repos become project repos with role, branch and their own Changes tab; the manifest
   exists and is editable, hand-written at first. Mostly a refactor of `linked` in `room/manager.py`, `RoomConfig`
   and the UI. Can be done without deciding anything about 3 and 4.
3. **Make it run.** Discovery + compose-overlay generation, the agent asks the room for the gaps. Start with
   frontend + one API + Postgres (covers most of shape 4). Shapes 1–3 fall out of the same manifest.
4. **Cross-repo change sets.** One story in the room, N pull requests out, cross-linked; Changes pane per repo.
5. **Blueprints.** "New project" from a template (admin-only, like clone); first one is the nginx monolith.
6. Two-origin preview: make the iframe preview handle SPA-on-one-port + API-on-another as well as it handles the
   single-origin shape (what Rails/Django teams will show up with). Small; can slot in anywhere.
7. **Connect GitHub from the browser** (decided 2026-09-12, `decisions-log.md`). No `.env`, no terminal:
   - ~~Per user~~ Shipped 2026-09-12 (`github.md`): "Connect GitHub" in Settings runs GitHub's device flow (show a
     code, confirm on github.com). The worker stores the user token encrypted and hands it to git/gh through per-room
     identity files rewritten at every turn for the person who asked, so commits and PRs are authored by the human
     who asked. Falls back to the machine identity. One operator step remains: `MARVIN_GITHUB_CLIENT_ID`.
   - Per machine: a GitHub App created through the manifest flow (one click creates it, a second installs it on the
     org with repo selection) replaces the PAT; installation tokens are minted per hour, scoped to selected repos.
   - Clone-by-URL on the join screen becomes a repo picker listing what the connected account/installation can see.
   Prerequisite for the multi-repo work (item 2 needs many repos per project) and the audit log (who did what).

Open decisions: core license (Apache 2.0 vs AGPL); trademark check on "Marvin".
