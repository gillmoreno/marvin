# The room sandbox

Status: shipped on `feat/sandbox` (2026-09-12). Code: `worker/marvin/sandbox.py`, hooks in
`adapters/registry.py` (`create_harness(..., sandbox=)`), `room/session.py`, `room/manager.py`, `main.py`; image in
`deploy/sandbox/`. Roadmap item 1 in `roadmap.md`.

## What it is

With `MARVIN_SANDBOX=docker`, each room's coding agent runs inside its own Docker container instead of as a child
process of the worker. Everything the agent does, shell commands, file edits, package installs, test runs, happens
in that container. The worker, LiveKit, the speech-to-text and the admin API stay outside.

```
worker (host or container)
  ├─ room "frontend"  ──docker exec──▶  marvin-sbx-frontend   (repo + linked repos + HOME mounted)
  ├─ room "api"       ──docker exec──▶  marvin-sbx-api
  └─ room "sandbox"   ──docker exec──▶  marvin-sbx-sandbox
```

One container per room, created on the room's first start from `MARVIN_SANDBOX_IMAGE` with `sleep infinity`; every
harness process (the Claude Code CLI, an ACP agent) is a `docker exec` into it. The container is recreated when
anything fixed at `docker run` time changes (image, linked repos, network, limits), restarted if it stopped, and
removed when the room is deleted.

The blast radius of a bad tool call, a prompt injection in a repo, or a runaway `rm -rf` is: the container's own
filesystem, the repo and linked repos mounted into it, and the credentials forwarded to that exec. Not the worker,
not the other rooms, not the machine.

## Same paths on both sides

The repo, the linked repos and the room's HOME are mounted at the *same absolute paths* inside the container as the
worker sees them. Nothing in Marvin translates paths: tool events name the same files, the Changes pane (which runs
git on the worker side) shows the same tree, the agent's `pwd` is the worker's `cfg.repo`.

- Repo and linked repos: bind mounts (`-v /path:/path`).
- HOME: `<state_dir>/sandbox/<room>/home`, bind-mounted at that path and set as `HOME`. This is where the agent's
  session store lives, so `resume` works across container recreation and worker restarts.
- Machine notes (`~/.claude/CLAUDE.md` on the worker): mounted read-only into the sandbox HOME, so every room still
  loads them and the agent cannot rewrite them from inside (the admin API is the only writer).

When the worker itself runs in a container (compose edge stack, Kubernetes), its paths are not host paths.
`MARVIN_SANDBOX_MOUNTS=marvin_work:/work` says "mount this named volume at `/work` in every sandbox too"; anything
under a destination listed there is then not bind-mounted separately, and the notes become a symlink instead of a
mount. In the k8s StatefulSet the dind sidecar already shares `/work` at the same path, so no extra mounts are needed.

## Credentials

Nothing secret is written into the container. Provider keys, the GitHub token, proxies and the git identity are
forwarded as environment variables on each `docker exec` (`DEFAULT_FORWARD_ENV` in `sandbox.py`, plus
`MARVIN_SANDBOX_ENV`), and only those present in the worker's environment. LiveKit secrets, Marvin passwords and the
session secret are never in the list.

Inside the container, `marvin-sandbox-init` (run once after creation) configures git to read the GitHub token from
the environment at use time, so `git push` and `gh` work without a credentials file. Per-user git identity (a
GitHub App token per human) is a later item; today the agent still commits as the machine.

## Network and app ports

`MARVIN_SANDBOX_NETWORK`:

- `host` (default): the container shares the worker's network namespace (the machine in dev, the Pod in k8s). A dev
  server the agent starts on :5173 is reachable exactly as before and shows up as an app link. Weakest isolation:
  the agent can reach anything on localhost, including the admin API, which is the status quo without a sandbox.
  On Docker Desktop (macOS/Windows) host networking must be enabled in Settings → Resources → Network (4.34+).
- `container:<name>`: share a specific container's namespace. The compose edge stack uses `container:marvin-worker`
  so the agent's ports land in the worker container, where the port scanner and the apps proxy already look.
  Restarting that peer (`docker restart marvin-worker`) leaves the sandbox in the **old** netns: DNS dies and
  Grok/Claude cannot reach their APIs. `ensure()` compares `/proc/1/ns/net` and recreates when they diverge.
- `bridge`: own namespace; ports listed in `MARVIN_SANDBOX_PORTS` (e.g. `3000-3010,5173,8000-8010`) are published
  on `127.0.0.1`. The worker also reads `/proc/net/tcp` inside each container so app links still appear. Strongest
  isolation; two rooms cannot both publish the same port.
- `none`: no network at all. Useful for audits of untrusted repos; most agents need the network for their model API.

## Limits and hardening

Per container: `--memory` (`MARVIN_SANDBOX_MEMORY`, 4g), `--cpus` (2), `--pids-limit` (2048), `--init`,
`--security-opt no-new-privileges`. `MARVIN_SANDBOX_RUN_ARGS` appends anything else (`--cap-drop ALL`,
`--read-only`, a seccomp profile, `--gpus`).

`MARVIN_SANDBOX_USER`: on Linux the default is the worker's own uid:gid, so files the agent writes into the
bind-mounted repo stay owned by the operator. On macOS Docker Desktop maps ownership itself and the default is root
inside the container. In the compose edge stack the worker runs as root, so `0:0`.

`MARVIN_SANDBOX_DOCKER_SOCKET=1` mounts the host's Docker socket into every sandbox so the agent can run
`docker compose` for the app it works on. That is root-equivalent on that host and undoes most of the isolation;
the worker logs a warning at start. Off by default. The roadmap's "make it run" step (`roadmap.md` item 3) is the
intended replacement: the *worker* runs the project's compose stack from a manifest, the agent never touches the
daemon.

## The image

`deploy/sandbox/Dockerfile` → `marvin-sandbox:local` (`make sandbox-image`). Debian bookworm with Node 22, Python 3
+ uv, git, gh, ripgrep, jq, make, build tools, the Docker CLI (inert unless the socket is mounted), and the harness
CLIs. `HARNESSES` picks which agents to install:

```sh
make sandbox-image                                              # all eight
make sandbox-image SANDBOX_HARNESSES="claude-code grok"         # smaller
docker build --build-arg HARNESSES="codex" -t acme/sbx deploy/sandbox
```

Teams bring their own toolchain by building `FROM marvin-sandbox:local` (or from anything, as long as the harness
CLI is on `PATH` and `/usr/local/bin/marvin-sandbox-init` exists), and set `MARVIN_SANDBOX_IMAGE`. A per-room image
is roadmap material (it belongs in the project manifest).

If `MARVIN_SANDBOX_IMAGE` names a registry (`ghcr.io/acme/marvin-sandbox:1.2`) and the image is missing, the worker
pulls it at start. A bare name that is missing fails fast with a pointer to `make sandbox-image`.

## Operating it

```sh
make sandbox-ps        # room containers and their status
make sandbox-clean     # remove them all; recreated on the next worker start (HOME under the state dir survives)
docker logs marvin-sbx-<room>      # empty by design: harness stdout/stderr go to the worker's log
docker exec -it marvin-sbx-<room> bash   # look around as the agent would
```

The worker checks the daemon and the image at start and exits with a clear message if either is missing; set
`MARVIN_SANDBOX=off` to run without (the four-terminal dev loop default).

Per room the UI shows, in Settings → This room, whether the agent is sandboxed and in which container.

## Deployments

- Dev (`make worker`): `MARVIN_SANDBOX=off` by default. To try it: `make sandbox-image`, then
  `MARVIN_SANDBOX=docker make worker`. On macOS enable host networking in Docker Desktop, or use
  `MARVIN_SANDBOX_NETWORK=bridge MARVIN_SANDBOX_PORTS=5173,3000-3010`.
- Compose edge stack: on by default (`MARVIN_SANDBOX=docker`), `make edge-up` builds the sandbox image first.
  Worker container is named `marvin-worker`, the volume `marvin_work`; the sandboxes mount the volume and join the
  worker's network namespace.
- Kubernetes: `MARVIN_SANDBOX=docker` in the worker container; the sandboxes are containers inside the dind sidecar
  (`DOCKER_HOST=tcp://localhost:2375`), `/work` is the shared PVC, `host` network inside dind is the Pod. Publish the
  sandbox image to a registry dind can pull from and set `MARVIN_SANDBOX_IMAGE`.

## Not yet

- Per-room image and resource limits from the project manifest.
- gVisor / Kata runtime (`MARVIN_SANDBOX_RUN_ARGS=--runtime=runsc` works today if the host has it; not tested).
- Rootless nested daemon per sandbox as an alternative to the socket, for teams that want the agent to run compose.
- Egress policy (allow-list of hosts the agent may reach) — needs a proxy or network policy; EE.
- Audit log of every exec.
