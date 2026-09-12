"""Generic harness adapter speaking the Agent Client Protocol (https://agentclientprotocol.com) over stdio.

One subprocess per room (`command`), JSON-RPC 2.0 with newline-delimited JSON. We are the *client*: we send
`initialize`, `session/new|load|resume`, `session/prompt`, `session/cancel`; the agent streams `session/update`
notifications and may call us back with `session/request_permission`, which we route to the room's PermissionBroker.
No SDK dependency: the protocol surface we use is small and the wire format is plain JSON, so a hand-written client
keeps the footprint (and the number of moving parts) down. See docs_and_changelog/harnesses.md for the event mapping.
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import re
import time
from typing import Any, AsyncIterator

from .base import HarnessEvent
from .permissions import PermissionBroker
from .prompt import ROOM_SYSTEM_PROMPT, _truncate

log = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
CLIENT_INFO = {"name": "marvin", "version": "0.1.0"}
# We advertise no client-side fs/terminal: agents use their own tools, and the room only sees permission requests.
CLIENT_CAPABILITIES = {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}
OK_STOP_REASONS = ("end_turn", "max_tokens", "cancelled")
# Tool kinds that never bother the room (same spirit as the Claude adapter's pre-approved Read/Glob/Grep/WebFetch/WebSearch).
QUIET_TOOL_KINDS = frozenset({"read", "search", "fetch", "think"})
AUTH_METHOD_HINT = re.compile(r"api[-_ ]?key|env|token|cached|login|oauth|account", re.I)
START_TIMEOUT_S = 90.0
_DONE = object()


class AcpError(Exception):
    """A JSON-RPC error returned by the agent, or a transport failure (agent exited)."""

    def __init__(self, message: str, code: int | None = None, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data

    def __str__(self) -> str:
        return f"{super().__str__()}" + (f" (code {self.code})" if self.code is not None else "")


AUTH_REQUIRED = -32000
METHOD_NOT_FOUND = -32601


class AcpHarness:
    """Implements marvin.adapters.base.Harness over an ACP agent subprocess."""

    def __init__(
        self,
        cwd: str,
        permissions: PermissionBroker | None,
        *,
        agent_name: str = "Marvin",
        room: str = "room",
        command: list[str],
        env: dict[str, str] | None = None,
        model: str | None = None,
        resume: str | None = None,
        add_dirs: list[str] | None = None,
        name: str = "acp",
        system_prompt: str = ROOM_SYSTEM_PROMPT,
        project: str = "",
    ) -> None:
        if not command:
            raise ValueError("AcpHarness needs a command to run")
        self.name = name
        self.cwd = cwd
        self.permissions = permissions
        self.agent_name = agent_name
        self.room = room
        self.command = list(command)
        self.env = dict(env or {})
        self.model: str | None = model  # effective model, updated from the agent's config options
        self.requested_model: str | None = model
        self.session_id: str | None = resume
        self.add_dirs = list(add_dirs or [])
        self.system_prompt = system_prompt.format(agent_name=agent_name, room=room) + (f"\n{project}" if project else "")
        self.available_models: list[dict[str, str]] = []
        self.agent_info: dict[str, Any] = {}
        self.agent_capabilities: dict[str, Any] = {}
        self.stderr_tail: collections.deque[str] = collections.deque(maxlen=60)
        self._resume = resume
        self._resumed = False  # True when the running session was loaded/resumed (no system prompt needed)
        self._needs_system_prompt = True
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._stderr_reader: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._ids = 0
        self._write_lock = asyncio.Lock()
        self._dead = True
        self._turn: _Turn | None = None
        self._model_config_id: str | None = None

    # -- lifecycle ---------------------------------------------------------------
    async def start(self) -> None:
        await self._spawn()
        try:
            await asyncio.wait_for(self._handshake(), timeout=START_TIMEOUT_S)
        except BaseException:
            await self.close()
            raise
        log.info("%s: acp session %s in %s (agent %s)", self.name, (self.session_id or "?")[:8], self.cwd, self.agent_info.get("name") or self.command[0])

    async def close(self) -> None:
        proc, self._proc = self._proc, None
        self._dead = True
        for t in (self._reader, self._stderr_reader):
            if t and t is not asyncio.current_task():
                t.cancel()
        self._reader = self._stderr_reader = None
        self._fail_pending(AcpError("agent closed"))
        if proc is None:
            return
        try:
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()
        except Exception:
            pass
        if proc.returncode is None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()

    async def interrupt(self) -> None:
        turn = self._turn
        if turn is None or self._dead or not self.session_id:
            return
        turn.cancelled.set()
        await self._notify("session/cancel", {"sessionId": self.session_id})

    # -- one turn ----------------------------------------------------------------
    async def send(self, prompt: str) -> AsyncIterator[HarnessEvent]:
        if self._dead:
            # The agent died (or was never started): bring it back, resuming the same session when the agent can.
            self._resume = self.session_id
            await self.start()
        yield HarnessEvent("turn_start", {"harness": self.name})
        text = prompt
        if self._needs_system_prompt:  # first prompt of a fresh session: ACP has no system-prompt parameter
            text = f"# Room instructions\n{self.system_prompt}\n\n# Message\n{prompt}"
        self._needs_system_prompt = False
        turn = self._turn = _Turn()
        t0 = time.monotonic()
        task = asyncio.create_task(self._request("session/prompt", {"sessionId": self.session_id, "prompt": [{"type": "text", "text": text}]}))
        task.add_done_callback(lambda _t: turn.queue.put_nowait(_DONE))
        try:
            while True:
                item = await turn.queue.get()
                if item is _DONE:
                    break
                yield item
            for ev in turn.flush_text():
                yield ev
            duration_ms = int((time.monotonic() - t0) * 1000)
            try:
                res = task.result()
            except AcpError as e:
                yield HarnessEvent("error", {"message": f"{self.name}: {e}"})
                yield self._result("error", True, duration_ms, turn)
                return
            stop = str((res or {}).get("stopReason") or "end_turn")
            yield self._result(stop, stop not in OK_STOP_REASONS, duration_ms, turn)
        finally:
            self._turn = None

    def _result(self, subtype: str, is_error: bool, duration_ms: int, turn: _Turn) -> HarnessEvent:
        return HarnessEvent(
            "result",
            {"subtype": subtype, "is_error": is_error, "cost_usd": turn.cost_usd, "duration_ms": duration_ms, "num_turns": 1, "session_id": self.session_id},
        )

    # -- process -----------------------------------------------------------------
    async def _spawn(self) -> None:
        env = {**os.environ, **self.env}
        log.info("%s: starting %s", self.name, " ".join(self.command))
        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=self.cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=32 * 1024 * 1024,  # tool results may embed big blobs; the default 64 KiB line limit would kill the stream
        )
        self._dead = False
        self._reader = asyncio.create_task(self._read_stdout(self._proc), name=f"acp-stdout-{self.name}")
        self._stderr_reader = asyncio.create_task(self._read_stderr(self._proc), name=f"acp-stderr-{self.name}")

    async def _read_stdout(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    log.debug("%s: non-JSON on stdout: %s", self.name, line[:200])
                    continue
                if isinstance(msg, dict):
                    self._dispatch(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s: stdout reader", self.name)
        finally:
            if self._proc is proc:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1)  # so the return code is known in the log line
                except (asyncio.TimeoutError, Exception):
                    pass
                self._on_exit(proc)

    async def _read_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            s = line.decode(errors="replace").rstrip()
            self.stderr_tail.append(s)
            log.debug("%s stderr: %s", self.name, s)

    def _on_exit(self, proc: asyncio.subprocess.Process) -> None:
        self._dead = True
        rc = proc.returncode
        tail = " | ".join(list(self.stderr_tail)[-5:])
        msg = f"agent exited (rc={rc}){': ' + tail if tail else ''}"
        log.warning("%s: %s", self.name, msg)
        self._fail_pending(AcpError(msg))

    def _fail_pending(self, err: Exception) -> None:
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(err)
        self._pending.clear()

    # -- JSON-RPC ----------------------------------------------------------------
    async def _write(self, msg: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or self._dead:
            raise AcpError("agent is not running")
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode()
        async with self._write_lock:
            try:
                proc.stdin.write(data)
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, RuntimeError) as e:
                raise AcpError(f"agent pipe closed: {e}") from e

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._ids += 1
        rid = self._ids
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        try:
            await self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
            return await fut
        finally:
            self._pending.pop(rid, None)

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def _respond(self, rid: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": rid}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result if result is not None else {}
        try:
            await self._write(msg)
        except AcpError:
            pass  # the agent is gone; nothing to answer

    def _dispatch(self, msg: dict[str, Any]) -> None:
        if "method" in msg:
            if "id" in msg:
                asyncio.create_task(self._handle_request(msg))
            else:
                self._handle_notification(msg.get("method", ""), msg.get("params") or {})
            return
        fut = self._pending.get(msg.get("id"))  # type: ignore[arg-type]
        if fut is None or fut.done():
            return
        if "error" in msg and msg["error"] is not None:
            err = msg["error"] or {}
            fut.set_exception(AcpError(str(err.get("message", "error")), code=err.get("code"), data=err.get("data")))
        else:
            fut.set_result(msg.get("result"))

    async def _handle_request(self, msg: dict[str, Any]) -> None:
        method, rid, params = msg.get("method", ""), msg.get("id"), msg.get("params") or {}
        try:
            if method == "session/request_permission":
                await self._respond(rid, await self._on_permission(params))
            else:
                # fs/*, terminal/*, vendor extensions (cursor/ask_question, ...): we advertised none of these.
                log.debug("%s: unsupported request %s", self.name, method)
                await self._respond(rid, error={"code": METHOD_NOT_FOUND, "message": f"{method} is not supported by this client"})
        except Exception as e:
            log.exception("%s: handling %s", self.name, method)
            await self._respond(rid, error={"code": -32603, "message": f"{type(e).__name__}: {e}"})

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method != "session/update":
            log.debug("%s: notification %s ignored", self.name, method)
            return
        turn = self._turn
        if turn is None:
            return  # history replayed by session/load, or chatter between turns: not a room event
        for ev in self._translate(params.get("update") or {}, turn):
            turn.queue.put_nowait(ev)

    # -- translation -------------------------------------------------------------
    def _translate(self, upd: dict[str, Any], turn: _Turn) -> list[HarnessEvent]:
        kind = upd.get("sessionUpdate")
        out: list[HarnessEvent] = []
        if kind == "agent_message_chunk":
            content = upd.get("content") or {}
            if content.get("type") == "text":
                mid = upd.get("messageId")
                if mid is not None and turn.message_id is not None and mid != turn.message_id:
                    out.extend(turn.flush_text())
                turn.message_id = mid if mid is not None else turn.message_id
                turn.text.append(content.get("text", ""))
                out.append(HarnessEvent("text_delta", {"text": content.get("text", "")}))
        elif kind == "tool_call":
            out.extend(turn.flush_text())
            title, tkind = upd.get("title") or "", upd.get("kind") or "other"
            inp = upd.get("rawInput")
            if not isinstance(inp, dict):
                inp = {"title": title, "kind": tkind, "locations": upd.get("locations") or []}
            tid = str(upd.get("toolCallId", ""))
            turn.tools[tid] = title or tkind
            out.append(HarnessEvent("tool_use", {"id": tid, "tool": title or tkind, "input": inp}))
            if upd.get("status") in ("completed", "failed"):
                out.append(self._tool_result(upd, tid))
        elif kind == "tool_call_update":
            if upd.get("status") in ("completed", "failed"):
                out.append(self._tool_result(upd, str(upd.get("toolCallId", ""))))
        elif kind == "usage_update":
            cost = upd.get("cost") or {}
            if isinstance(cost.get("amount"), (int, float)) and str(cost.get("currency", "USD")).upper() == "USD":
                turn.cost_usd = float(cost["amount"])
        elif kind == "config_option_update":
            self._read_config_options(upd.get("configOptions") or [])
        # agent_thought_chunk (reasoning stays off the shared screen), user_message_chunk, plan,
        # available_commands_update, current_mode_update, session_info_update: not room events.
        return out

    def _tool_result(self, upd: dict[str, Any], tid: str) -> HarnessEvent:
        text = _tool_output_text(upd)
        return HarnessEvent("tool_result", {"id": tid, "output": _truncate(text), "is_error": upd.get("status") == "failed"})

    # -- permissions -------------------------------------------------------------
    async def _on_permission(self, params: dict[str, Any]) -> dict[str, Any]:
        call = params.get("toolCall") or {}
        options = params.get("options") or []
        tool = call.get("title") or call.get("kind") or "tool"
        raw = call.get("rawInput")
        tool_input = raw if isinstance(raw, dict) else {"title": call.get("title"), "kind": call.get("kind"), "locations": call.get("locations") or []}
        turn = self._turn
        if turn is not None and turn.cancelled.is_set():
            return {"outcome": {"outcome": "cancelled"}}
        if call.get("kind") in QUIET_TOOL_KINDS:
            allowed = True
        elif self.permissions is None:
            allowed = False
        else:
            ask = asyncio.ensure_future(self.permissions.ask(tool, tool_input))
            waiters = [ask] + ([asyncio.ensure_future(turn.cancelled.wait())] if turn is not None else [])
            done, pending = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            if ask not in done:
                return {"outcome": {"outcome": "cancelled"}}
            allowed = bool(ask.result())
        option = _pick_option(options, ("allow_once", "allow_always") if allowed else ("reject_once", "reject_always"))
        if option is None:
            return {"outcome": {"outcome": "cancelled"}}
        return {"outcome": {"outcome": "selected", "optionId": option}}

    # -- handshake ---------------------------------------------------------------
    async def _handshake(self) -> None:
        init = await self._request("initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": CLIENT_CAPABILITIES, "clientInfo": CLIENT_INFO}) or {}
        self.agent_info = init.get("agentInfo") or {}
        self.agent_capabilities = init.get("agentCapabilities") or {}
        auth_methods = [m for m in (init.get("authMethods") or []) if isinstance(m, dict)]
        self._resumed = False
        resp = None
        if self._resume:
            try:
                resp = await self._open_session(self._resume)
            except AcpError as e:
                if e.code == AUTH_REQUIRED:
                    await self._authenticate(auth_methods)
                    try:
                        resp = await self._open_session(self._resume)
                    except AcpError as e2:
                        log.warning("%s: cannot resume session %s (%s); starting a new one", self.name, self._resume[:8], e2)
                else:
                    log.warning("%s: cannot resume session %s (%s); starting a new one", self.name, self._resume[:8], e)
        if resp is None:
            try:
                resp = await self._new_session()
            except AcpError as e:
                if e.code != AUTH_REQUIRED:
                    raise
                await self._authenticate(auth_methods)
                resp = await self._new_session()
        self._needs_system_prompt = not self._resumed
        await self._apply_model(resp or {})

    async def _open_session(self, session_id: str) -> dict[str, Any] | None:
        """session/resume (no replay) when advertised, else session/load (history is replayed and swallowed)."""
        caps = self.agent_capabilities
        params: dict[str, Any] = {"sessionId": session_id, "cwd": self.cwd, "mcpServers": [], **self._dirs_param()}
        if (caps.get("sessionCapabilities") or {}).get("resume") is not None:
            resp = await self._request("session/resume", params)
        elif caps.get("loadSession"):
            resp = await self._request("session/load", params)
        else:
            log.info("%s: agent cannot load sessions; starting a new one", self.name)
            return None
        self.session_id = session_id
        self._resumed = True
        return resp or {}

    def _dirs_param(self) -> dict[str, Any]:
        """Linked repos go in `additionalDirectories` only for agents that advertise it (strict agents reject unknown
        fields); the others learn about them from the first prompt instead."""
        if self.add_dirs and (self.agent_capabilities.get("sessionCapabilities") or {}).get("additionalDirectories") is not None:
            return {"additionalDirectories": self.add_dirs}
        return {}

    async def _new_session(self) -> dict[str, Any]:
        params: dict[str, Any] = {"cwd": self.cwd, "mcpServers": [], **self._dirs_param()}
        resp = await self._request("session/new", params) or {}
        self.session_id = str(resp.get("sessionId") or "") or None
        if not self.session_id:
            raise AcpError("session/new returned no sessionId")
        self._resumed = False
        return resp

    async def _authenticate(self, methods: list[dict[str, Any]]) -> None:
        usable = [m for m in methods if m.get("type", "agent") != "terminal"]
        ids = [str(m.get("id")) for m in usable]
        if not usable:
            raise AcpError(f"{self.name} needs authentication and offers no non-interactive method (advertised: {[m.get('id') for m in methods]}); authenticate the CLI on this machine first")
        chosen = next((m for m in usable if AUTH_METHOD_HINT.search(f"{m.get('id', '')} {m.get('name', '')}")), usable[0])
        log.info("%s: authenticating with %r (offered: %s)", self.name, chosen.get("id"), ids)
        try:
            await self._request("authenticate", {"methodId": chosen.get("id")})
        except AcpError as e:
            raise AcpError(f"authentication with {chosen.get('id')!r} failed: {e}; methods offered: {ids}") from e

    async def _apply_model(self, resp: dict[str, Any]) -> None:
        """Pick the requested model through the agent's config options (current ACP) or the legacy `models` field."""
        self._read_config_options(resp.get("configOptions") or [])
        if self._model_config_id:  # current spec (OpenCode 1.18 does this)
            if self.requested_model:
                value = _match_model(self.available_models, self.requested_model)
                if value is None:
                    log.warning("%s: model %r is not offered by the agent (has %s)", self.name, self.requested_model, [m["id"] for m in self.available_models])
                else:
                    try:
                        r = await self._request("session/set_config_option", {"sessionId": self.session_id, "configId": self._model_config_id, "value": value}) or {}
                        if r.get("configOptions"):
                            self._read_config_options(r["configOptions"])
                        else:
                            self.model = value
                    except AcpError as e:
                        log.warning("%s: session/set_config_option failed: %s", self.name, e)
            return
        models = resp.get("models") or {}
        if isinstance(models, dict) and models.get("availableModels"):  # pre-configOptions shape (codex-acp 1.11 does this)
            self.available_models = [{"id": str(m.get("modelId")), "label": str(m.get("name") or m.get("modelId")), "note": str(m.get("description") or "")} for m in models["availableModels"]]
            self.model = models.get("currentModelId") or self.model
            if self.requested_model:
                value = _match_model(self.available_models, self.requested_model)
                if value is None:
                    log.warning("%s: model %r is not offered by the agent (has %s)", self.name, self.requested_model, [m["id"] for m in self.available_models])
                else:
                    try:
                        await self._request("session/set_model", {"sessionId": self.session_id, "modelId": value})
                        self.model = value
                    except AcpError as e:
                        log.warning("%s: session/set_model failed: %s", self.name, e)
        elif self.requested_model:
            log.info("%s: agent exposes no model selector; %r stays a request only", self.name, self.requested_model)

    def _read_config_options(self, opts: list[dict[str, Any]]) -> None:
        for o in opts:
            if not isinstance(o, dict) or o.get("type", "select") != "select":
                continue
            if o.get("category") == "model" or (o.get("category") is None and str(o.get("id", "")).lower() == "model"):
                self._model_config_id = str(o.get("id"))
                flat: list[dict[str, Any]] = []
                for item in o.get("options") or []:
                    if isinstance(item, dict) and "options" in item and "group" in item:
                        flat.extend(x for x in item["options"] if isinstance(x, dict))
                    elif isinstance(item, dict):
                        flat.append(item)
                self.available_models = [{"id": str(x.get("value")), "label": str(x.get("name") or x.get("value")), "note": str(x.get("description") or "")} for x in flat]
                cur = o.get("currentValue")
                if cur is not None:
                    self.model = str(cur)
                return


class _Turn:
    """Per-prompt state: the event queue send() drains, the text being assembled, cost, cancellation."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.text: list[str] = []
        self.message_id: str | None = None
        self.tools: dict[str, str] = {}
        self.cost_usd: float | None = None
        self.cancelled = asyncio.Event()

    def flush_text(self) -> list[HarnessEvent]:
        if not self.text:
            return []
        full, self.text = "".join(self.text), []
        return [HarnessEvent("text", {"text": full})] if full else []


def _pick_option(options: list[dict[str, Any]], kinds: tuple[str, ...]) -> str | None:
    for k in kinds:
        for o in options:
            if isinstance(o, dict) and o.get("kind") == k and o.get("optionId") is not None:
                return str(o["optionId"])
    return None


def _match_model(models: list[dict[str, str]], wanted: str) -> str | None:
    w = wanted.strip().lower()
    for m in models:
        if m["id"].lower() == w:
            return m["id"]
    for m in models:
        if m["label"].lower() == w:
            return m["id"]
    return None


def _tool_output_text(upd: dict[str, Any]) -> str:
    parts: list[str] = []
    for c in upd.get("content") or []:
        if not isinstance(c, dict):
            continue
        if c.get("type") == "content":
            block = c.get("content") or {}
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif block.get("type"):
                parts.append(f"[{block['type']}]")
        elif c.get("type") == "diff":
            parts.append(f"diff {c.get('path', '')}: {len(str(c.get('newText', '')))} chars")
        elif c.get("type") == "terminal":
            parts.append(f"[terminal {c.get('terminalId', '')}]")
    if parts:
        return "\n".join(parts)
    raw = upd.get("rawOutput")
    if raw is None:
        return ""
    return raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
