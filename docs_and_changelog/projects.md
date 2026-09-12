# Projects: a room is a list of repos

Shipped 2026-09-12. Roadmap item 2; the `repos:` section of the project manifest described in `roadmap.md`.

## Why

The unit of work is the project, not the repository. A frontend deployed as a static site, an API behind it and a
shared schema library are one thing to the people in the room ("make the checkout show the new discount"), and the
knowledge of how they fit together lives nowhere in any single repo. Marvin's differentiator is treating that as one
testable unit. `linked` repos (extra folders the agent could see) were the first step; they had no roles, no branches,
no source, and the UI created rooms from exactly one repo.

## What a project is

`worker/marvin/config.py`:

```python
@dataclass(frozen=True)
class ProjectRepo:
    path: str            # absolute directory on the machine (mounted at the same path in the sandbox)
    role: str = ""       # frontend | api | worker | lib | infra | docs | other | ""
    git_url: str | None  # cloned into `path` when the directory is missing
    branch: str | None

@dataclass(frozen=True)
class RoomConfig:
    name: str
    repos: tuple[ProjectRepo, ...]   # source of truth; first = the agent's working directory
    # derived, kept for code and configs that predate projects:
    repo, git_url, branch  ->  repos[0]
    linked                 ->  (r.path for r in repos[1:])
```

`RoomConfig(name=..., repo=..., linked=(...))` still works and builds a one-or-more-repo project; `RoomConfig(name=...,
repos=(...))` is the new form. `rooms.yaml` accepts either:

```yaml
rooms:
  - name: shop
    repos:
      - {path: /work/repos/shop-web, role: frontend, git_url: git@github.com:acme/shop-web.git}
      - {path: /work/repos/shop-api, role: api, git_url: git@github.com:acme/shop-api.git, branch: develop}
      - {path: /work/repos/acme-schema, role: lib}
  - name: legacy          # the old form still reads fine
    repo: /work/repos/legacy
    linked: [/work/repos/legacy-docs]
```

Dynamic rooms are persisted in `<state_dir>/rooms.json` with a `repos` list; records written by older workers (with
`repo` + `linked` only) load unchanged. UI edits live in the `overrides` section as `repos`; an old `linked` override
is read as "primary + those" with the roles the record already knows.

## Creating a project (join screen)

**New project** (admins): a name and a list of repos. Each repo is added:

- **from your GitHub**: the repositories the signed-in person's connected account can see (`GET /api/github/repos`,
  owner + collaborator + org member, most recently pushed first, searchable). Requires Settings → GitHub → Connect
  GitHub; the panel links there when not connected. The role is guessed from the name and language (`shop-web` →
  frontend, `*-api` → api, `*-worker` → worker, `*-schema` → lib, `infra` → infra, `docs` → docs) and can be changed.
- **folder on this machine**: what is under `MARVIN_REPOS_DIR` (`GET /api/repos`).
- **git URL**: anything `git clone` accepts.

Per repo: role and branch. "↑ first" makes a repo the working directory. "Create and join" posts
`{name, repos: [{path | git_url, role, branch}, ...]}` to `POST /api/rooms`. Repos with a `git_url` whose directory is
missing are cloned before the room starts, using the requester's connected GitHub token when they have one (else the
machine's `GITHUB_TOKEN`, else anonymous). `git@github.com:` URLs are rewritten to HTTPS when a token is available so
the token can authenticate. The token reaches git through `MARVIN_CLONE_TOKEN` in the environment and a one-off
`credential.helper` passed via `GIT_CONFIG_*`, never on the command line or in logs; clone errors have it redacted.

No repos at all creates an empty folder named after the project (the agent can `git clone` or `git init` on request).

## Editing a project (Settings → This project)

The same list, for the room you are in: change roles and branches, add (same three sources), remove, reorder.
"Save project" sends `PATCH /api/rooms/{name} {repos: [...]}`: the harness is swapped with the new directories (the
sandbox container is recreated with the new mounts when enabled) and the conversation resumes. Admin-only, like every
change to what the agent can see. `{linked: [...]}` is still accepted.

## Changes per repo

The Changes pane shows one tab per repo when the project has several (`name · role`). `GET /api/changes?room=&repo=<path>`
and `GET /api/changes/file?...&repo=<path>` accept any of the project's repo paths; the primary when omitted; anything
else is a 404. "Commit" and "open PR" name the repo in the request they send the agent.

## What the agent is told

`RoomConfig.project_text()` is appended to the room instructions for both harness kinds (Claude Agent SDK system
prompt append; ACP first-prompt preamble):

```
This room is a project of several repos; all of them are readable and editable:
- shop-web (frontend): /work/repos/shop-web <- your working directory
- shop-api (api): /work/repos/shop-api [branch develop]
- acme-schema (lib): /work/repos/acme-schema
```

plus the rule to commit in the repo a change belongs to, one branch per repo, and to mention every repo touched.
Every repo path is also passed as an additional directory (`add_dirs` / ACP `additionalDirectories`) so the harness
lets the agent edit there.

## Limits, next

- Roles are labels for people and the agent; nothing runs yet. Roadmap item 3 ("make it run") adds the
  `services`/`wiring`/`data`/`externals` sections of the manifest on top of this list and generates the compose
  overlay from it.
- One branch per repo per room is recorded but not enforced (the agent is told; `ensure_repo` clones the branch).
- Cross-repo change sets (roadmap item 4): today each repo's Changes tab is independent; "one story in the room, N
  linked pull requests out" is the next step on the same model.
- The GitHub repo list is per token, cached for a minute, up to 300 repos; organizations with more need the search box
  (filtering is local) or a URL.
