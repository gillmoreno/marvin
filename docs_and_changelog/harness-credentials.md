# Coding-agent credentials (Settings, not `.env`)

Status: shipped 2026-09-12. Code: `worker/marvin/harness_creds.py`, `web/src/HarnessConnect.tsx`.
The design principle is the same as GitHub's client id: if it can be entered in the browser, it is
(`decisions-log.md`, configuration in the UI).

## What a person sees

Settings → **Coding agents** (admin). For each provider Marvin knows (Anthropic, xAI/Grok, OpenAI, Gemini,
Cursor, Copilot):

- a short "open this page, click this, paste that" list with a link to the vendor's exact console;
- an API-key field, masked, validated (prefix + length), stored encrypted;
- for **Grok only**: **Sign in with Grok**, the device-code flow (`grok login --device-auth`). A tab opens
  on accounts.x.ai; type the code; Marvin stores `~/.grok/auth.json`. That is your grok.com subscription,
  not an API key billed at API rates.

The default harness for rooms that do not pin one is a select at the top of the same panel. No restart.

Non-admins see a one-line "an admin connects the agents here".

## Why Grok has a subscription button and Claude does not

- **xAI** documents `grok login --device-auth` for headless machines and stores a session in
  `~/.grok/auth.json`. That session is what a grok.com / SuperGrok account uses. Official:
  [Authentication](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/02-authentication.md).
- **Anthropic** forbids using a Claude Pro/Max OAuth token to drive the Agent SDK from a shared service
  (`security-and-compliance.md` §2). Claude in a room takes an API key from
  [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).

Codex, Cursor, Gemini, Copilot are API-key (or token) paste today. Their CLIs also have interactive
`login` commands; those can grow a device-flow button the same way Grok did, once we have a headless
path as clean as xAI's.

## Storage and precedence

`<state_dir>/harness.json` (mode `0600`):

- `keys.<id>.enc` — Fernet, key `sha256("marvin-harness:" + MARVIN_SESSION_SECRET)`
- `sessions.grok.enc` — the whole `auth.json`
- `settings.default_harness`

A copied state dir without the session secret is not a copied credential.

When a harness process starts, environment variables already set on the worker **win** (automation /
image-baked installs). Otherwise the stored key is forwarded (`DEFAULT_FORWARD_ENV`). The Grok session
is written into each room HOME as `.grok/auth.json` (`GROK_HOME`); Grok hot-reloads that file.

The UI says where the current value comes from: "from the environment" or "set here".

## The sandbox image must include the CLI

`grok login` is run with `grok` on PATH, or `docker run` of `marvin-sandbox:local`. When the worker talks
to the host Docker socket, that `docker run` must mount the **named volume** (`marvin_work:/work`) and
set `HOME` to the path inside it. A bind of the worker-container path `/work/state/...` writes `auth.json`
on the host, where Marvin cannot see it.

Build the sandbox with grok in the harness list:

```
make sandbox-image SANDBOX_HARNESSES="claude-code grok"
```

A box that was first built with only `claude-code` will not be able to start the Grok sign-in until that
image is rebuilt. Rebuilding the image does not refresh an already-running `marvin-sbx-*` container —
recreate it (or restart the worker so `ensure()` builds a new one) or `grok` will be missing and the
room dies with `agent exited (rc=127)`.
