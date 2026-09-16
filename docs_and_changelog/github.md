# GitHub on a Marvin machine

Marvin commits, pushes and opens pull requests on behalf of the people in the room. People are known by their
**Marvin login** (email, or SSO). GitHub is how the *machine* talks to repos, not how a person proves who they are.

Until the two required connections exist, Marvin is a dedicated setup page — not a locked projects list.
Projects, sessions, and machine settings stay hidden. Personal GitHub appears only after the machine is ready,
and never blocks Join.

| Step | Who | Required? |
|---|---|---|
| This machine’s GitHub | Admin, once | Yes. One shared account for the box. |
| A coding agent | Admin, once | Yes. Pick an agent, then sign in or paste a key. |
| Your GitHub | Anyone | No. Only if you want your name on the git author line. |

Roadmap item 7 (`roadmap.md`). Decided in `decisions-log.md` (2026-09-12 direction, 2026-09-13: ship the shared
machine account plus optional personal). The machine account is a **GitHub App** (manifest flow, Enterprise),
a pasted PAT, or `GITHUB_TOKEN`.

## What a person sees

1. Sign in with Marvin. Password mode asks for **email**. The join page says *You’re logged in as* that email
   (or the SSO name).
2. If the box is not ready, the workspace does not appear. Admins get two sequential steps: machine GitHub,
   then a coding-agent picker. Participants see a waiting page.
3. **Your GitHub** is skippable and only shows on the ready projects page. Alex with no GitHub joins. A
   programmer who wants the author line to be theirs connects (device flow, or **paste a token**). Disconnect
   returns their turns to the machine account.
4. Settings → GitHub and Settings → Coding agents are how you change those later, not the first-run surface.

`GET /api/setup` is what the setup page polls: `ready` is true only when the machine GitHub and a coding agent
are set. Personal GitHub is reported and ignored for `ready`.

## What an admin does once

On a fresh box the setup page is the place. Settings still works if you need to change it later.

**This machine’s GitHub.** One account every room uses to clone, push and open PRs. Author is the Marvin
identity who asked; committer is `marvin[bot]`. Three ways in:

- **Create a GitHub App** (Enterprise). On a fresh box, **Create a GitHub App** on the setup
  page asks for the license string if this machine does not have one yet; after save, GitHub
  opens. Later, Settings → Enterprise is the same paste. Marvin POSTs a manifest to GitHub;
  you name the app, create it, then install it on the org and pick repos. Hourly installation
  tokens replace a shared PAT. Redirects land on `/api/github/app/callback` and
  `/api/github/app/install`.

- **Paste a token.** Fine-grained PAT, no OAuth App, no client id. The setup form links to
  [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)
  and lists the clicks: name `Marvin`, pick the org or your account, **Only select repositories**,
  Contents read/write + Pull requests read/write, copy `github_pat_…`. A classic token with `repo`
  also works. This is also the escape hatch when GitHub’s device confirmation page is blank.
- **Connect this machine** (device flow). Needs the OAuth App client id below. The link Marvin opens already
  contains the user code (`verification_uri_complete`, or `?user_code=`). GitHub must show *that* code; if the
  page is blank or shows a different one, cancel and paste a token instead.

`GITHUB_TOKEN` / `GH_TOKEN` in the environment still wins and the UI says “from the environment”. Stored machine
tokens live encrypted in `<state_dir>/github.json` → `settings.machine` (`PUT /api/github/machine`, admin-only).

**A coding agent.** Sign in with Grok, or paste an Anthropic key on the same page. Other providers stay in
Settings → Coding agents. One provider is enough; Join unlocks.

**OAuth App client id** (device flow only). An admin registers one OAuth App per install and pastes the client id
on the join page or in Settings → GitHub. A pasted PAT does not need this.

1. GitHub → **Settings → Developer settings → OAuth Apps → New OAuth App** (for a company: *Organization settings
   → Developer settings → OAuth Apps*).
2. Application name: `Marvin`. Homepage URL and Authorization callback URL: the Marvin address (the device flow
   does not use the callback; the form just requires one).
3. Tick **Enable Device Flow**. Register. Copy the **Client ID** (`Ov23li…` or `Iv1.…`). Do not generate a client
   secret; Marvin does not want one.
4. Paste it → **save**. No restart. Stored in `<state_dir>/github.json` (`PUT /api/github/config`, admin-only).
   `MARVIN_GITHUB_CLIENT_ID` in the environment still wins (“from the environment”).

The client id is a **public identifier**, not a secret. What *is* sensitive is `MARVIN_SESSION_SECRET`, the key
tokens are encrypted with (falls back to `LIVEKIT_API_SECRET`).

Scopes requested: `repo read:org workflow` (what `gh auth login` asks for, minus gists). If the organization
restricts third-party OAuth apps, an org owner approves the app once under *Third-party access*.

## How it works

```
join / Settings
  POST /api/github/connect[?dest=machine] ──▶ token server ──▶ worker  ──▶ github.com/login/device/code
       ◀── {user_code, verification_uri (already has the code), flow}
  GET  /api/github/connect/<flow>  poll until connected
  PUT  /api/github/machine | /api/github/me   pasted PAT (no client id)
  GET  /api/setup   {ready, machine_github, agent, personal}
```

- **Identity of record.** Marvin login (email + password, or SSO headers). GitHub is optional attribution.
  `Requested-by:` / `Marvin-Session` / `Marvin-Turn` are stamped by `deploy/sandbox/hooks/commit-msg`.
  The `git` wrapper on PATH drops `--author`. `pre-push` refuses a push whose turn is not on the
  audit JSONL. Commits are SSH-signed with `<state_dir>/git-signing` when `ssh-keygen` is available;
  upload the `.pub` (Settings → GitHub) to the GitHub App for the Verified badge.
- **Two stored accounts.** `<state_dir>/github.json`: `settings.client_id` (plain), `settings.machine` (encrypted
  token + public login/name/email), and one `users` record per Marvin identity. Fernet key
  `sha256("marvin-github:" + MARVIN_SESSION_SECRET)`. File mode `0600`. A copied state directory without the
  secret is not a copied credential; if the secret changes, records become undecryptable and are dropped on
  first read.
- **Who may write.** `/api/github/me` and `/api/github/connect` (personal) are self-service: they only touch the
  identity in `X-Marvin-User`. `/api/github/machine` and `/api/github/config` are admin-only (token server
  `ADMIN_ONLY_PREFIXES` and a second check in `admin.py`). `POST /api/github/connect?dest=machine` is the same
  admin check inside the worker.
- **Per-turn identity** (`marvin/github.py`, `GitIdentity`). Each room's harness sees two env vars pointing into
  the room directory (`<state_dir>/sandbox/<room>/home/.marvin/`, the same path the sandbox mounts as HOME):
  - `GIT_CONFIG_GLOBAL=…/gitconfig`: includes `~/.gitconfig`, then sets `user.name` / `user.email`,
    `safe.directory=*`, and a credential helper that reads `…/token`. `git@github.com:` is rewritten to HTTPS.
  - `GH_CONFIG_DIR=…/gh`: `hosts.yml` with the same token.

  At turn start the conductor calls `RoomSession._on_turn_begin(asked_by)` → `GitIdentity.apply(room, user_id)`:
  the asker's connected account if they have one, else the stored machine account (`machine @login`), else the
  env token / `MARVIN_GIT_NAME`/`EMAIL` (“machine identity”), else no credentials (system git helpers). git and
  gh reread the files every time, so the switch is immediate. Room log: `turn by Gil, git identity: @gil (gil)`.
- **Sandbox.** Both variables are in `DEFAULT_FORWARD_ENV`. `marvin-sandbox-init`'s helper (reading
  `GITHUB_TOKEN` from the exec environment) remains the fallback when the worker has no state dir.

## Limits, honestly

- A turn is attributed to the person who *asked*. If two people talk during one turn, the requester is the one
  whose words woke Marvin. Parallel work is sequential turns anyway.
- The token file is readable by the agent (that is the point). In sandbox mode it is only mounted into that
  room's container; without the sandbox all rooms run as the worker's user and could read each other's files
  (`sandbox.md`, `security-and-compliance.md` finding 4).
- OAuth App user tokens do not expire on their own; disconnect (or revoking the app under GitHub → Settings →
  Applications) ends them. Tokens are re-checked when Settings → GitHub opens; a revoked one is forgotten.
- User-token scopes are still broad (`repo`). The GitHub App installation is what narrows access to
  selected repositories and gives short-lived tokens; user tokens remain for attribution.
- GitHub’s device confirmation page has been blank on the Frankfurt pilot and has shown a *different* code
  than Marvin. The join page opens the URI that already contains Marvin’s code, and **GitHub went blank**
  switches to a PAT. See `pilot-findings.md`.

## Next

- Repo picker on the join screen, listing what the installation (or the connected account) can see.
- `Approved-by` trailer from the last tool approval.
