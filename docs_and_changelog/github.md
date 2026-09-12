# Connect GitHub from the browser

Marvin commits, pushes and opens pull requests on behalf of the people in the room. This page is about **whose name
that happens under** and how a person links their GitHub account without touching a terminal or a `.env` file.

Roadmap item 7 (`roadmap.md`), decided in `decisions-log.md`. Shipped 2026-09-12 for the per-user half; the
per-machine GitHub App (manifest flow) and the repo picker are still to do.

## What a person sees

1. Open **Settings** (the gear in the room header) → section **GitHub** → **Connect GitHub**.
2. Marvin shows an 8-character code and opens `https://github.com/login/device` in a new tab. Type the code, approve.
3. Within a few seconds the panel says *Connected as @login*. Done. From now on, when this person asks Marvin to
   commit, push or `gh pr create`, git and gh run with their identity and their token. **Disconnect** forgets the
   token.

Nothing is typed into Marvin except the code on GitHub's page; Marvin never sees a password and there is no client
secret anywhere (this is OAuth's *device flow*, the same thing `gh auth login` does).

## What an admin does once (from the same Settings panel)

GitHub needs to know which application is asking. An admin registers one OAuth App per Marvin installation (five
minutes, no server, no callback of ours involved) and pastes its client id into Settings → GitHub; the panel
walks through it:

1. GitHub → **Settings → Developer settings → OAuth Apps → New OAuth App** (for a company, do it under the org:
   *Organization settings → Developer settings → OAuth Apps*).
2. Application name: `Marvin`. Homepage URL and Authorization callback URL: the Marvin address (the device flow does
   not use the callback, the form just requires one).
3. Tick **Enable Device Flow**. Register. Copy the **Client ID** (starts with `Ov23li…` or `Iv1.…`). Do not generate a
   client secret; Marvin does not want one.
4. Paste it into Settings → GitHub → **save**. No restart. It is stored in `<state_dir>/github.json` next to the
   tokens (`PUT /api/github/config`, admin-only, validated as a plausible client id). `MARVIN_GITHUB_CLIENT_ID` in the
   environment still works and, when set, wins over the stored value (the panel then shows "from the environment").

The client id is a **public identifier**, not a secret: GitHub puts it in every OAuth URL, and the device flow has no
client secret at all. The UI masks it out of habit; there is nothing to protect. What *is* sensitive is
`MARVIN_SESSION_SECRET`, the key the user tokens are encrypted with (falls back to `LIVEKIT_API_SECRET`).

Until an admin has done this the GitHub section tells non-admins so, and rooms keep working with whatever they had:
the machine's `GITHUB_TOKEN` if set, otherwise the git credentials of the machine (on a developer's Mac, the keychain).

Scopes requested: `repo read:org workflow` (what `gh auth login` asks for, minus gists). If your organization
restricts third-party OAuth apps, an org owner approves the app once under *Third-party access*.

## How it works

```
Settings ──POST /api/github/connect──▶ token server ──▶ worker admin  ──▶ github.com/login/device/code
          ◀── {user_code, verification_uri, flow} ──                     (client_id, scope)
          ──GET /api/github/connect/<flow>── poll ──▶ worker polls github.com/login/oauth/access_token
                                                      on success: GET /user (+ /user/emails), store encrypted
```

- **Identity.** The token server (`token_server.py`) already knows who is signed in (password, SSO header or the
  dev name) and stamps `X-Marvin-User` on every proxied call. `/api/github/*` is *self-service*: any signed-in
  person may call it, and it only ever touches the record of the identity in that header. Other users cannot read
  or poll someone else's flow (`404`).
- **Storage.** `<state_dir>/github.json`: `settings.client_id` (plain, public) and one `users` record per Marvin
  identity: login, name, e-mail, scopes, and the token encrypted with Fernet under
  `sha256("marvin-github:" + MARVIN_SESSION_SECRET)`. File mode `0600`. A copied state
  directory without the secret is not a copied credential; if the secret changes, the records become undecryptable
  and are dropped on first read (people simply connect again).
- **Per-turn identity** (`marvin/github.py`, `GitIdentity`). Each room's harness is started with two environment
  variables pointing into the room's directory (`<state_dir>/sandbox/<room>/home/.marvin/`, the same directory the
  sandbox mounts as the room's HOME, so the paths are identical inside the container):
  - `GIT_CONFIG_GLOBAL=…/gitconfig`: git's global config for that process tree. It includes the real `~/.gitconfig`
    underneath (aliases etc. survive), then sets `user.name`/`user.email`, `safe.directory=*`, and, when a token is
    available, resets the credential helper list and installs one that reads `…/token`; `git@github.com:` URLs are
    rewritten to HTTPS.
  - `GH_CONFIG_DIR=…/gh`: gh's config directory, with a `hosts.yml` carrying the same token.

  When a turn starts, the conductor calls `RoomSession._on_turn_begin(asked_by)`; the session maps the speaker's
  display name to their Marvin identity (the LiveKit participant identity), and `GitIdentity.apply(room, user_id)`
  rewrites the three files: the requester's connected account if they have one, else the machine identity
  (`GITHUB_TOKEN`, `MARVIN_GIT_NAME/EMAIL`), else no credentials at all (the token file is removed, git falls back to
  the system's helpers). git and gh read those files at every invocation, so the switch is immediate even though the
  agent process is long-lived. In the room log: `turn by Gil, git identity: @gil (gil)`.
- **Sandbox.** Both variables are in `DEFAULT_FORWARD_ENV`, so `docker exec` carries them into the container, where
  the same paths exist because the room HOME is bind-mounted. `marvin-sandbox-init`'s own credential helper (reading
  `GITHUB_TOKEN` from the exec environment) remains the fallback when the worker has no state dir.

## Limits, honestly

- A turn is attributed to the person who *asked*. If two people talk during one turn, the requester is the one whose
  words woke Marvin. Parallel work by different people in the same room is sequential turns anyway.
- The token file is readable by the agent (that is the point). In sandbox mode it is only mounted into that room's
  container; without the sandbox all rooms run as the worker's user and could read each other's files, which is the
  existing trust model of unsandboxed mode (`sandbox.md`, `security-and-compliance.md` finding 4).
- OAuth App user tokens do not expire on their own; **Disconnect** (or revoking the app under GitHub → Settings →
  Applications) ends them. Tokens are re-checked against GitHub when the Settings panel opens; a revoked one is
  forgotten.
- The scopes are broad (`repo`). The per-machine GitHub App (next step) is what narrows access to selected
  repositories and gives short-lived installation tokens; user tokens remain for attribution.

## Next

- GitHub App through the manifest flow: one click creates the app under the org, a second installs it with repo
  selection; the worker mints hourly installation tokens for clones and the fallback identity.
- Repo picker on the join screen, listing what the connected account (and the installation) can see.
- Audit line per turn: who asked, which identity acted, what was pushed.
