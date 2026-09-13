# Pilot findings

Running log of what broke (or surprised us) putting Marvin on a real VM. This is the product backlog
that only exists once other people can reach the box. Newest at the top.

Pilot hostname: `https://marvin.aigil.dev`. Box: `c7i.2xlarge` in `eu-central-1a` (Frankfurt), Elastic IP
`63.185.15.12`. DNS is Cloudflare, grey-cloud (not proxied) so WebRTC and Caddy's HTTP-01 hit the VM.
App-preview wildcard reserved as `*.marvin.aigil.dev`.

## 2026-09-13

- **Typed Send had no immediate feedback.** The box cleared, then nothing until Grok finished the current
  turn (and LiveKit rounded the trip). Cause: typed `ask` never published a transcript line, and `turn_start`
  waited for the runner. Fix: paint locally on click; worker publishes transcript + `turn_start` at enqueue
  (`queued` if busy).
- **No in-app upgrade.** A new `main` on GitHub stayed off the VM until someone SSHed. Settings → This
  machine now lists the missing commits and updates from the browser (`updates.md`). The first box still
  needs one manual pull so that panel exists.

## 2026-09-12

- **Preview hosts stay under this install.** `*.marvin.aigil.dev` is this VM. It cannot be the preview domain
  for every Marvin customer: a wildcard has one IP, and riding on `aigil.dev` would make us their hosted edge.
  General rule: `p{port}.{MARVIN_DOMAIN}`.
- **Leading "Marvin" on CPU Whisper.** Not Super Whisper: this box is faster-whisper `small` plus Silero VAD
  (NVIDIA streaming STT is the other path, and it is not running here). Two failures showed up in the worker
  log: `turn from gil: Marvin.` then a later line that was not a wake. (1) VAD ends the utterance after the
  name, so the worker used to start a turn whose question was just `Marvin.` and drop the rest. (2)
  `initial_prompt="Marvin, Marvin."` made Whisper treat the name as already said and omit it at the start of
  the next sentence. Fix: latch a name-only utterance onto the next line from the same speaker; change the
  prompt and pass `hotwords=Marvin`. "Marvin, how does X work?" in one breath still strips the name.
- **Smoothness bar (first real Grok session).** Signing in, switching harness, and the first turns
  looked alive (listening / working / `…`) while the agent was dead, missing, or retrying DNS. A
  native `alert()` said `AcpError: agent exited (rc=127)`. That is not shippable: a visitor would
  think Marvin is broken. The room must fail in the pane, in a sentence, with the next click
  (Settings → Sign in, or wait). Fixes in this pass: no interactive ACP login from the room
  (Grok unauthenticated → banner, not a 90s hang); rc=127 and start timeouts are plain language;
  harness/model switch errors stay in the pane; agent errors with no open turn still show; a turn
  that sits on `…` for 8s says “Still waiting on the agent…”.
- `docker restart marvin-worker` orphans `marvin-sbx-*` containers that joined
  `container:marvin-worker`: same container id, new netns. Grok then spends a minute on
  `dns error: failed to lookup address information: Try again` for `cli-chat-proxy.grok.com`
  (15 retries). `ensure()` now recreates a sandbox whose `/proc/1/ns/net` does not match the worker.
- Room can look live (STT, "listening") while the harness never started. Grok hung on ACP
  `authenticate` for 90s (`START_TIMEOUT_S`); `TimeoutError` stringifies to empty so the log said
  `failed to start:`. LiveKit was already connected, the turn runner never started, so spoken and
  typed turns queued and vanished. Fix: keep the turn runner even when the agent is not ready;
  bounce the room after Grok signs in.
- Grok "Sign in" wrote `auth.json` on the **host** (`docker run -v /work/state/...` is a host path when the
  worker uses the host socket), so Marvin never saw the session. Fixed: mount the `marvin_work` volume at
  `/work` and set `HOME` to the path inside it. Gil's completed login was imported from the stray host file.
- First sandbox image on the box was built with `SANDBOX_HARNESSES=claude-code` only. Grok subscription
  login needs the grok CLI in that image (`make sandbox-image SANDBOX_HARNESSES="claude-code grok"`).
- First `edge-up` on a live daemon worked: Let's Encrypt (tls-alpn-01) issued `marvin.aigil.dev`, login
  (`password` mode) returns participant vs admin cookies, `/api/me` and `/api/rooms` answer, and the
  default `sandbox` room came up in `marvin-sbx-sandbox` (`container:marvin-worker`, 4g/2cpu, image
  `marvin-sandbox:local`). Same-path `/work` mounts and `/work` ownership were not a problem on this
  first contact. Whisper `small` started downloading into `marvin_work` immediately.
- Local `.env` had no `ANTHROPIC_API_KEY` or `GITHUB_TOKEN`. The worker started a Claude Code session
  anyway; the first real turn will fail until a key is on the box. GitHub Connect is off until an
  admin pastes a client id in Settings.
- From Gil's laptop, `marvin.aigil.dev` does not resolve: Tailscale's resolver (`100.100.100.100`) returns
  NXDOMAIN even when querying `@1.1.1.1`. The same name answers `63.185.15.12` from the VM and from
  Let's Encrypt validators. Local browser checks from this Mac need Tailscale bypassed or a hosts entry
  (`63.185.15.12 marvin.aigil.dev`). A phone off Tailscale should just work.
- Chose Frankfurt over `us-east-1`: Gil is near Frankfurt. Unused US Elastic IP / SG / key pair from the
  interrupted first attempt were deleted the same afternoon.
- No `*.aigil.dev` wildcard: that zone already hosts many tunnel subdomains. Room URL is `marvin.aigil.dev`;
  app hosts will be under `*.marvin.aigil.dev` (section D), not `marvin-*.aigil.dev`.
