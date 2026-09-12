# Harnesses: one room, any coding agent

A *harness* is the coding agent a room talks to. Marvin has two adapter kinds behind the same `Harness` contract
(`worker/marvin/adapters/base.py`):

| kind | adapter | what it is |
|---|---|---|
| `claude-sdk` | `worker/marvin/adapters/claude_code.py` | Claude Code through the Claude Agent SDK, in-process. Unchanged. |
| `acp` | `worker/marvin/adapters/acp.py` | Any agent speaking the [Agent Client Protocol](https://agentclientprotocol.com) over stdio: one subprocess per room, JSON-RPC 2.0, newline-delimited JSON. |

Profiles (which agent, how it is launched, how it authenticates) live in `worker/marvin/adapters/registry.py`.
`registry.create_harness(profile, cwd, ...)` is the only place that knows which class to build; `RoomSession`,
the admin API and the UI only deal in profile ids.

## Choosing the harness

- Worker default: `--harness <id>` / `MARVIN_HARNESS=<id>` (default `claude-code`). An unknown id falls back to
  `claude-code` with a warning rather than taking every room down.
- Per room: `harness: <id>` in `rooms.yaml`, or the harness picker in the room header (next to the model picker),
  which calls `PATCH /rooms/{name}` with `{"harness": "<id>"}` (`""` clears the pin). Pins persist in
  `<state_dir>/rooms.json` like model pins.
- `GET /harnesses` lists the profiles (`id`, `label`, `kind`, `command` after env override, `auth`, `models`,
  `default_model`, `note`) and the default. `GET /models?harness=<id>` returns that profile's model list; the UI
  reloads the model picker whenever the room's harness changes, and shows only "harness default" when the list is
  empty.
- Switching a room to a different harness starts a **new conversation**: session ids are not portable across agents,
  so `RoomSession.reconfigure` passes no `resume` and clears the saved session id. Switching model or linked repos
  within the same harness still resumes.
- `GET /rooms` exposes `harness` (effective: the running adapter's profile id, else the pin, else the default) and
  `harness_pinned`.

## Profiles

Verified on 2026-09-11 against the ACP registry (`https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json`,
registry version 1.0.0), `npm view <pkg> bin`, and a live `initialize` + `session/new` handshake from this client
where noted. No model provider was called and no credentials were involved.

| id | kind | command | auth | verified |
|---|---|---|---|---|
| `claude-code` | claude-sdk | (SDK spawns its bundled `claude`; `command` is informational) | `ANTHROPIC_API_KEY` or Bedrock/Vertex commercial credentials | existing adapter, tests pass |
| `claude-acp` | acp | `claude-agent-acp` | as above | registry: `npx @agentclientprotocol/claude-agent-acp@0.76.0`; bin name `claude-agent-acp`; **live handshake OK** (initialize + session/new, `loadSession`, `resume`, `additionalDirectories` advertised, `authMethods: []`) |
| `codex` | acp | `codex-acp` | `OPENAI_API_KEY` or `codex login` | registry: `npx @agentclientprotocol/codex-acp@1.11.0`; bin `codex-acp`; **live handshake OK** (auth methods `api-key`, `chat-gpt`; `session/new` returns the legacy `models` field) |
| `cursor` | acp | `agent acp` | `CURSOR_API_KEY` or `agent login`; advertises auth method `cursor_login` | registry ships a binary tarball (`cursor-agent acp`); [cursor.com/docs/cli/acp](https://cursor.com/docs/cli/acp) documents `agent acp`. Not run locally. |
| `gemini` | acp | `gemini --acp` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY` / Vertex ADC) | registry: `npx @google/gemini-cli@0.59.0 --acp`; bin `gemini`. Not run locally. Older releases used `--experimental-acp`. |
| `opencode` | acp | `opencode acp` | `opencode auth login` or provider keys | registry: binary release `opencode acp`; npm `opencode-ai` bin `opencode`; **live handshake OK** (`configOptions` with a `model` selector, `loadSession`, `resume`) |
| `grok` | acp | `grok agent stdio` | Settings → Coding agents: **Sign in with Grok** (`grok login --device-auth`) or an `XAI_API_KEY` | registry: `npx @xai-official/grok@1.0.29 agent stdio` (npm latest is 1.0.25); `grok agent stdio --help` run locally. **`--no-auto-update` does not exist** in 1.0.25 (clap would abort on it), so it is not in the command; pin the npm version instead. See `harness-credentials.md`. |
| `copilot` | acp | `copilot --acp` | `COPILOT_GITHUB_TOKEN` / `GH_TOKEN` of an account with Copilot, or `copilot login` | registry: `npx @github/copilot@1.0.83 --acp`; bin `copilot`. Not run locally. |

Notes:

- The `@zed-industries/claude-agent-acp` (0.23.1) and `@zed-industries/codex-acp` (0.16.0) packages still exist on
  npm but are stale; the registry points at `@agentclientprotocol/*`. The profiles use the latter.
- Every command can be overridden with `MARVIN_HARNESS_CMD_<ID>` (id upper-cased, `-` → `_`, value split like a shell
  line), e.g. `MARVIN_HARNESS_CMD_CURSOR="/work/home/.local/bin/cursor-agent acp"` or
  `MARVIN_HARNESS_CMD_GROK="grok -m grok-4 agent stdio"`. The override is what `GET /harnesses` reports.
- Model lists: only `claude-code` ships a static list (moved here from `admin.py`). ACP profiles have an empty list
  because each agent reports its own models at session start (`AcpHarness.available_models`); the UI shows
  "harness default" for them. A `model:` pin is still applied (see below).

### Anthropic credentials

On a shared server use an `ANTHROPIC_API_KEY` or commercial (Bedrock/Vertex) credentials for `claude-code` and
`claude-acp`. Do not use a personal Claude Pro/Max OAuth token (`CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`):
Anthropic's consumer terms tie those subscriptions to one person and forbid using them to power a shared service.

## How the ACP adapter maps the protocol to Marvin events

| ACP | `HarnessEvent` |
|---|---|
| `session/prompt` sent | `turn_start {harness}` |
| `session/update` `agent_message_chunk` (text) | `text_delta {text}`; chunks are accumulated and emitted as one `text {text}` when the `messageId` changes, when a tool call starts, and at the end of the turn (the Claude adapter also emits both) |
| `agent_thought_chunk` | dropped: reasoning is not shown on the shared screen (it would also be spoken over the transcript of a meeting). |
| `tool_call` | `tool_use {id: toolCallId, tool: title or kind, input: rawInput or {title, kind, locations}}`; if it already carries `status: completed/failed`, a `tool_result` follows immediately |
| `tool_call_update` with `status: completed` / `failed` | `tool_result {id, output, is_error}`; `output` is the text of `content` blocks (`diff` → `diff <path>: N chars`, `terminal` → `[terminal id]`), else `rawOutput` as JSON, truncated to 800 chars |
| `tool_call_update` with other statuses, `plan`, `available_commands_update`, `current_mode_update`, `session_info_update`, `user_message_chunk` | ignored |
| `usage_update` with `cost` in USD | remembered and reported as `cost_usd` on the turn's `result` (cumulative session cost, like the SDK's `total_cost_usd`) |
| `config_option_update` | refreshes `available_models` / `model` |
| `session/request_permission` (agent → client) | see below |
| `session/prompt` returns `{stopReason}` | `result {subtype: stopReason, is_error: stopReason not in (end_turn, max_tokens, cancelled), session_id, duration_ms, cost_usd, num_turns: 1}` |
| JSON-RPC error on `session/prompt`, or the agent process exits mid-turn | `error {message}` then `result {subtype: "error", is_error: true}` |

Other agent → client requests (`fs/read_text_file`, `fs/write_text_file`, `terminal/*`, vendor extensions such as
Cursor's `cursor/ask_question` / `cursor/create_plan`) get a JSON-RPC `-32601` reply so the agent never blocks on us.
We advertise `fs: {readTextFile: false, writeTextFile: false}` and `terminal: false`, so well-behaved agents use their
own tools; this is what the room's approval flow expects.

### Permissions

`session/request_permission` carries the tool call and a list of options (`allow_once`, `allow_always`,
`reject_once`, `reject_always`). The adapter:

1. answers `allow_once` without asking when the tool `kind` is `read`, `search`, `fetch` or `think` (the counterpart
   of the Claude adapter pre-approving Read/Glob/Grep/WebFetch/WebSearch);
2. otherwise calls `PermissionBroker.ask(title or kind, rawInput or {title, kind, locations})`, which the room sees as
   the usual `permission_request` event, and answers `{"outcome": {"outcome": "selected", "optionId": …}}` with the
   `allow_once` (fallback `allow_always`) or `reject_once` (fallback `reject_always`) option;
3. answers `{"outcome": {"outcome": "cancelled"}}` when the turn was interrupted while the question was pending (the
   spec requires this after `session/cancel`), or when the agent offered no matching option;
4. rejects when no broker is attached (only possible before `RoomSession` wires it).

"Always allow" in the UI works as before: the broker returns `True` without asking. `allow_always` is deliberately not
sent to the agent, so the room keeps the decision.

### Interrupt

`interrupt()` sends the `session/cancel` notification; the agent is expected to finish `session/prompt` with
`stopReason: cancelled`, which becomes a `result` with `is_error: false`.

### System prompt

ACP has no system-prompt parameter. `ROOM_SYSTEM_PROMPT` (now in `worker/marvin/adapters/prompt.py`, shared with the
Claude adapter, text unchanged) is prepended to the **first prompt of a fresh session** as

```
# Room instructions
<prompt>
Linked repos (readable and editable too): /work/repos/a, /work/repos/b   ← only when the room links repos

# Message
<what was said in the room>
```

Later prompts, and every prompt of a resumed session, are sent as-is. Agents that keep their own instructions
(CLAUDE.md, AGENTS.md, `.cursor/rules`, …) load them in addition.

### Resume

`start()` sends `initialize` (protocol version 1, client info `marvin`). When a saved session id exists:

- if the agent advertises `sessionCapabilities.resume`, `session/resume` is used (no history replay);
- else if it advertises `loadSession`, `session/load` is used and the replayed `session/update` history is swallowed
  (nothing is emitted between turns);
- otherwise, or if either call fails, a new `session/new` is created and the room continues with a fresh conversation
  (same fallback the Claude adapter has for stale ids).

If the agent process dies during a turn the room gets `error` + `result(is_error)`, the adapter marks itself dead, and
the next `send()` restarts the process, trying to resume the same session id first.

### Authentication

If `session/new` fails with `-32000` (auth required), the adapter calls `authenticate` once with the first
advertised method whose id/name looks like an API-key/env/token/login method (`terminal`-type methods are never passed
to `authenticate`, as the spec says), then retries. A failure surfaces as a clear exception from `start()` listing
the offered method ids; the worker keeps running (the room's start fails, others are unaffected). In practice the
tested agents (codex-acp, opencode, claude-agent-acp) accept `session/new` without credentials and only fail at prompt
time, which then shows up as an `error` event in the room.

### Model selection

The spec moved from `models`/`session/set_model` to `configOptions` with `category: "model"` and
`session/set_config_option`. The adapter handles both: after `session/new|load|resume` it reads `configOptions` (as
OpenCode 1.18 returns) or the legacy `models.availableModels` (as codex-acp 1.11 returns), records the list in
`available_models` and the current value in `model`, and if the room pins a model it sends the matching
`session/set_config_option` / `session/set_model` (matching by id, then by label). Unknown model ids are logged and
ignored rather than failing the room. `config_option_update` notifications keep `model` current.

### Linked repos

Passed as `additionalDirectories` on `session/new|load|resume` only when the agent advertises
`sessionCapabilities.additionalDirectories` (claude-agent-acp and codex-acp do; OpenCode 1.18 does not). Agents that do
not advertise it learn the paths from the first prompt instead.

## Adding a profile

1. Add a `HarnessProfile` to `PROFILES` in `worker/marvin/adapters/registry.py`: `id`, `label`, `kind="acp"`, the
   `command` list, one line of `auth`, optional `models`/`default_model`/`note`/`env`.
2. Check the command against the ACP registry (`distribution` entries) or the vendor's docs and record it in the table
   above with the date.
3. Install the CLI in the image (`Dockerfile`, commented block) and add its credential to `.env.example`.
4. `test_registry.py` checks every profile has a command and auth text and lists the ids; extend the expected list.

## Known limitations

- No per-turn cost unless the agent sends `usage_update` with a USD `cost`; `cost_usd` is then the cumulative session
  cost (same semantics as the SDK adapter). `num_turns` is always 1.
- Reasoning (`agent_thought_chunk`) is hidden; plans, modes and slash commands are ignored.
- Client-side `fs/*` and `terminal/*` are switched off, so agents that need a client-provided filesystem will not edit
  files (none of the registry agents require it).
- Images dropped in the room are passed to the agent as paths in the prompt text, not as ACP image content blocks.
- The Claude adapter's `max_turns` has no equivalent; agents apply their own limits (`max_turn_requests`).
- `interrupt()` relies on the agent honouring `session/cancel`; a hung agent is only recovered by the room's
  `close()`/restart.

## Decisions to review

- **No SDK**: PyPI `agent-client-protocol` 0.12.1 is current but pulls in pydantic and its API is still 0.x; the
  adapter uses ~150 lines of hand-written JSON-RPC instead, tested against a fake agent and three real ones.
- **`session/resume` preferred over `session/load`** when advertised: same outcome, no history replay to swallow.
- **Quiet tool kinds** (`read`, `search`, `fetch`, `think`) are auto-allowed; adjust `QUIET_TOOL_KINDS` if the room
  should approve web fetches.
- **`allow_always` is never sent** to agents; "always allow" stays a Marvin-side switch.
- **Unknown agent → client requests are refused** (`-32601`) rather than emulated; Cursor's `cursor/create_plan` and
  `cursor/ask_question` will therefore be reported by the agent as unsupported. If Cursor rooms need them, add handlers
  in `AcpHarness._handle_request`.
- **Packages**: `@agentclientprotocol/*` instead of the `@zed-industries/*` names given in the task (stale on npm).
- **grok**: `--no-auto-update` dropped (flag does not exist in 1.0.25).
- **Node 22** added to the image via NodeSource (Debian bookworm's nodejs is 18, too old for Gemini CLI and Copilot);
  the ACP CLIs themselves stay commented out in the Dockerfile.
- **Unknown `MARVIN_HARNESS`** falls back to `claude-code`; `--harness` with an unknown id exits at startup with the
  list of known ids.
