# Marvin

A voice room with a coding agent in it. Everyone talks; say **"Marvin"** and the agent answers on the shared screen.

Marvin is not a coding-agent harness. It is a bridge to one: each participant's audio is transcribed (Silero VAD +
faster-whisper, locally, no GPU needed), the transcript is merged with speaker labels, and when someone addresses
Marvin the conversation since the last turn plus the question is sent as one message to a long-lived coding-agent
session working in a repository on the same machine. Replies, tool calls and permission requests stream back to
everyone in the room.

```
browser (LiveKit React) ──audio──▶ livekit-server ──one track per human──▶ worker
                        ◀──data channel: transcript, agent events, approvals──┘
                                                                         worker ──▶ harness adapter ──▶ Claude Code session (repo on this machine)
```

## Run it locally

Requirements: Docker, [`uv`](https://docs.astral.sh/uv/), [`pnpm`](https://pnpm.io/), and an `ANTHROPIC_API_KEY`
(see [Authentication](#authentication)). The first worker start downloads the Whisper model (`small`, ~500 MB).

```sh
cp .env.example .env      # set MARVIN_REPO (the repo the agent works in) and NODE_IP (your LAN IP)
make install              # uv sync + pnpm install
make up                   # livekit-server in docker on :7880
make token                # terminal 2, token endpoint on :8080
make worker               # terminal 3, Marvin joins room "dev"
make web                  # terminal 4, http://localhost:5173
```

This loop runs with `MARVIN_AUTH=none` (the `.env.example` default): everything binds to localhost, the name you type
is your identity, and you are admin. Open the page, pick room `dev`, allow the mic.

Then say: *"Marvin, what does this repo do?"* You can also type to Marvin in the box at the bottom; that goes through
the same path as a spoken wake word.

## Run it for other people

Anything reachable from another machine goes through Caddy, which terminates TLS and is the only way in:

```sh
# .env: NODE_IP, LIVEKIT_API_KEY, LIVEKIT_API_SECRET (32+ chars), MARVIN_ROOM_PASSWORD, MARVIN_ADMIN_PASSWORD,
#       MARVIN_SESSION_SECRET, and MARVIN_DOMAIN + MARVIN_TLS=<your e-mail> for a real certificate
make edge-up              # livekit + worker + web + caddy in containers; https://<host>/
make edge-oidc-up         # same, with single sign-on through oauth2-proxy (OAUTH2_PROXY_* in .env)
```

People sign in with the room password (or their SSO account), admins with the admin password (or by group). Only
admins can create rooms, switch harness or model, edit machine notes, or turn on "always allow". Details, the role
matrix and the Kubernetes variant: [`docs_and_changelog/authentication.md`](docs_and_changelog/authentication.md).

## Authentication

Who may join is covered above and in `docs_and_changelog/authentication.md`. This section is about the agent's own
credentials.

The Claude Code adapter uses the Claude Agent SDK, which reads the usual Anthropic credentials from the environment:
set `ANTHROPIC_API_KEY` (or Bedrock / Vertex credentials, as documented by the SDK) for the worker process, in `.env`
locally or in the Kubernetes Secret on a cluster.

Do **not** use a personal Claude Pro/Max login or its OAuth token (`claude setup-token`) on a shared Marvin server.
Anthropic's consumer terms restrict those credentials to Claude Code and claude.ai; a room that several people drive
is neither. Use an API key or a commercial plan's credentials instead.

## How a turn works

1. Every finalized utterance lands in the timeline with speaker and timestamps, and in the Transcript pane.
2. An utterance with the name in its first or last three words triggers a turn (`worker/marvin/bridge/wake.py`).
   "Let's ask Marvin later" does not; "does that make sense, Marvin" does.
3. The turn's message is the transcript since the previous turn plus the addressed sentence
   (`worker/marvin/bridge/turns.py`). There is no time limit: an hour of talk without the wake word arrives whole,
   and the prompt tells the agent the latest lines weigh most. Earlier turns are already in the long-lived session,
   so over a meeting the agent has heard everything.
4. The harness streams text, tool calls and results; the worker fans them out over the data channel.
5. Anything that writes or runs (Bash, Edit, Write) comes back as a permission request. Anyone in the room can Allow
   or Deny. Read-only tools are pre-approved. Unanswered requests are denied after five minutes.
6. Turns run one at a time. A second "Marvin" while it is working queues.

## Harnesses

Marvin talks to coding agents through a small adapter contract, `worker/marvin/adapters/base.py`: a `Harness` is one
long-lived session bound to one repo; `send(prompt)` streams `HarnessEvent`s (`text_delta`, `tool_use`,
`permission_request`, `result`, ...). The room, the transcript and the approval flow know nothing else.

- **Claude Code** (via the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)) is the default:
  `worker/marvin/adapters/claude_code.py`. Sessions resume across restarts, tools go through the room's permission
  broker, the model can be switched per room.
- **Any [Agent Client Protocol](https://agentclientprotocol.com) agent** through `worker/marvin/adapters/acp.py`:
  profiles for Claude Code (`claude-acp`), Codex CLI (`codex`), Cursor CLI (`cursor`), Gemini CLI (`gemini`),
  OpenCode (`opencode`), Grok Build (`grok`) and GitHub Copilot CLI (`copilot`). Install the CLI you want in the
  image, give it its credentials, then pick it per room (`harness:` in `rooms.yaml` or the picker in the room header)
  or as the worker default (`MARVIN_HARNESS`). Details, verification status and limitations:
  [`docs_and_changelog/harnesses.md`](docs_and_changelog/harnesses.md).

## Layout

```
worker/marvin/bridge/      transcript timeline, wake word, turn assembly     (pure python, tested)
worker/marvin/stt/         Silero VAD + local whisper segmenter, one per speaker; optional remote streaming STT client
worker/marvin/adapters/    harness contract, permission broker, claude_code (SDK), acp (any ACP agent), registry (profiles)
worker/marvin/room/        wire protocol + conductor (queue, approvals, fan-out) + session + room manager
worker/marvin/main.py      LiveKit plumbing: tracks -> segmenters -> conductor; admin API for rooms/repos/ports
worker/marvin/token_server.py   token endpoint, /api proxy, serves the built UI in the image
worker/marvin/gate.py      optional "power switch" for clusters (sleep/wake page + schedule)
stt/                       optional GPU streaming STT service (NVIDIA Nemotron ASR over WebSocket), see stt/README.md
web/                       Vite + React + LiveKit components; MarvinPane, Transcript, People, Workspace
deploy/                    Dockerfile entrypoint, k8s manifests (deploy/k8s), apps ingress generator
docs_and_changelog/        changelog and design notes
```

## Knobs

- `--whisper-model` / `MARVIN_WHISPER`: `small` int8 is the latency/accuracy point on Apple Silicon CPU. `base` for a
  fast demo, `large-v3-turbo` if the machine has cores to spare. Multilingual by default; `--language en` to pin.
- Wake-word aliases and window: `worker/marvin/bridge/wake.py`. The Whisper `initial_prompt` biases spelling toward
  "Marvin". `MARVIN_NAME` changes the name everywhere (prompt, UI, wake word).
- Pre-approved tools and the room system prompt: `worker/marvin/adapters/claude_code.py`.
- `--resume <session id>` continues yesterday's Claude Code session for the same repo (done automatically per room
  when `--state-dir` is set).
- `--stt-url ws://host:8765/v1/stream` swaps local Whisper for the streaming STT service in `stt/` (partials while
  people speak). Unset = local Whisper.

## A second laptop on the LAN (two voices)

Browsers only allow the microphone on HTTPS or localhost, so the dev server serves TLS and proxies LiveKit's
signaling websocket. Media flows directly to this machine's LAN IP (`NODE_IP` in `.env`, passed to livekit-server).

1. One-time, on this machine: create a self-signed cert the dev server picks up automatically.
   ```sh
   IP=$(ipconfig getifaddr en0)
   mkdir -p web/certs
   openssl req -x509 -newkey rsa:2048 -nodes -days 825 -keyout web/certs/dev.key -out web/certs/dev.crt \
     -subj "/CN=marvin-dev" -addext "subjectAltName=IP:$IP,IP:127.0.0.1,DNS:localhost"
   ```
   Re-run it if the LAN IP changes, and restart `make web`.
2. On the other laptop open `https://<this machine's IP>:5173`, click through the certificate warning
   (Advanced, then Proceed), enter a different name, same room, allow the mic.
3. Both people show up in the People list; each gets their own transcription stream.

If the other laptop cannot connect at all, the macOS firewall is the usual cause: allow incoming connections for
Docker and node, or turn the firewall off for the test. Ports: 5173 TCP (page + signaling), 7882 UDP and 7881 TCP (media).

## Beyond the LAN

- Put a reverse proxy (Caddy, nginx) with a real certificate in front of the web page and LiveKit instead of the
  self-signed one.
- One worker process serves many rooms (`--config rooms.yaml`); each room is its own repo or worktree and its own
  agent session.
- Text to speech for short replies is deliberately absent.

## The workspace

The room is three columns: people, app links and controls on the left; a tabbed centre; the conversation on the right
(Marvin and Transcript tabs). Centre tabs:

- **Changes**: the room repo's files against the branch base (merge-base with main, or uncommitted work when on main),
  with per-file diffs and "commit" / "open PR" buttons that hand the request to Marvin. Backed by `/api/changes`.
- **App previews**: every app link (declared in `rooms.yaml`, or a detected listening port) opens as an embedded
  preview with reload and open-in-new-tab. On a cluster, app hostnames allow framing from the Marvin host only.
- **Shared screens**: a tab per screen someone shares, only while they share it.

## Where the agent runs

By default the agent is a child process of the worker, working directly in the repo directory. With
`MARVIN_SANDBOX=docker` each room's agent runs in its own container instead: the repo, the linked repos and a
per-room HOME are mounted at the same paths, credentials are passed per exec, and a bad tool call can reach the
repo and the container, not the machine or the other rooms.

```sh
make sandbox-image                 # marvin-sandbox:local, with the harness CLIs
MARVIN_SANDBOX=docker make worker  # or set it in .env; the edge stack has it on by default
```

Details, networking choices and limits: [`docs_and_changelog/sandbox.md`](docs_and_changelog/sandbox.md).

## Whose commits are they

Settings → **GitHub** → **Connect GitHub**: type an 8-character code on github.com and you are linked. From then on,
when *you* ask Marvin to commit, push or open a PR, it happens with your name and your token; someone else in the
same room gets theirs. People who have not connected fall back to the machine's `GITHUB_TOKEN`. The operator
registers one OAuth App with device flow enabled and sets `MARVIN_GITHUB_CLIENT_ID`; that is the whole setup.
Details: [`docs_and_changelog/github.md`](docs_and_changelog/github.md).

## Model, linked repos, machine notes

- **Model**: the conversation header shows what the room runs on and lets you switch (Fable 5.1, Opus 5, Sonnet 5,
  Haiku 4.5, or the harness default). The harness is swapped on the spot and the conversation resumes.
- **Linked repos** (Settings, "This room"): extra folders under the repos directory the agent may read and edit from
  this room, e.g. the backend next to a frontend. Persisted per room.
- **Machine notes** (Settings): `~/.claude/CLAUDE.md` on the machine, Claude Code's user memory, loaded into every
  room. Where cross-repo knowledge lives: which backend a frontend needs, fake accounts, ports, start recipes.
  Editable in the UI; the agent appends there when asked to "remember" something that is about the machine rather
  than one repo. Repo-specific rules stay in each repo's `CLAUDE.md`.

## Rooms, repos and ports

- The worker process is the machine. Repos live under `MARVIN_REPOS_DIR` (`/work/repos` in the image). The join
  screen lists rooms and can create one from an existing folder or by cloning a git URL (`GITHUB_TOKEN` in the
  environment makes `git` and `gh` work over HTTPS). Rooms created this way persist in `<state dir>/rooms.json`;
  `rooms.yaml` still declares static ones.
- Any TCP port an app opens on the machine shows up in the room's App panel. On a cluster it gets
  `https://marvin-<port>.<your domain>` if the port is in the `ports` list of `deploy/k8s/rooms.yaml` (one Ingress
  rule each, generated by `deploy/gen_apps.py`); locally it is `http://localhost:<port>`.
- Marvin's git rules (system prompt): branch `marvin/<room>/<topic>`, never commit on main, tests before push,
  PRs via `gh pr create`, commit trailer `Requested-by: <who asked>`.

## On Kubernetes

The production shape is one Pod with LiveKit + coturn, the worker, the web container, an nginx apps proxy and a
Docker-in-Docker sidecar, plus an optional GPU Deployment for streaming STT and a tiny "gate" that puts the whole
thing to sleep at night. `deploy/k8s/` is a `kubectl apply -k` example with a local `secrets.env`;
[`deploy/k8s/README.md`](deploy/k8s/README.md) has the runbook, including the TURN-by-hostname setup for clients
behind a VPN/firewall that only allows DNS names. CI builds `ghcr.io/<owner>/marvin` and `ghcr.io/<owner>/marvin-stt`
on every push to `main`.

## Contributing

`make test` runs the worker tests (44, no audio hardware needed). `cd web && pnpm exec tsc --noEmit && pnpm build`
checks the UI. Changes to features go with a note in `docs_and_changelog/CHANGELOG.md`.

License: to be decided.
