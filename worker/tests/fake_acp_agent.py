"""A tiny ACP agent over stdio for tests: JSON-RPC 2.0, newline-delimited. Scenarios are picked with env vars.

FAKE_ACP_LOG=<file>        append one JSON line per incoming request/notification ({"method", "params"})
FAKE_ACP_LOAD=1            advertise loadSession and answer session/load (replays two updates first)
FAKE_ACP_RESUME_CAP=1      advertise sessionCapabilities.resume and answer session/resume
FAKE_ACP_AUTH=<id>         advertise one auth method; session/new fails with -32000 until `authenticate` is called
FAKE_ACP_PERMISSION=1      ask session/request_permission before the tool call and honour the answer
FAKE_ACP_MODELS=1          expose a model selector in configOptions (fast|smart, current smart)
FAKE_ACP_CHUNKS=<n>        number of agent_message_chunk before the tool call (default 2)
FAKE_ACP_SLOW=1            sleep between chunks and stream many, so session/cancel can land mid-turn
FAKE_ACP_CRASH_AT=<n>      exit(3) after the first chunk of the n-th prompt (1-based), once (marker file next to the log)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

ENV = os.environ
LOG = ENV.get("FAKE_ACP_LOG")


def log_msg(method: str, params: Any) -> None:
    if LOG:
        with open(LOG, "a") as f:
            f.write(json.dumps({"method": method, "params": params}) + "\n")


class Agent:
    def __init__(self) -> None:
        self.out = sys.stdout
        self.authenticated = not ENV.get("FAKE_ACP_AUTH")
        self.sessions: dict[str, dict] = {}
        self.cancelled: set[str] = set()
        self.prompts = 0
        self.model = "smart"
        self._ids = 1000
        self._pending: dict[int, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def write(self, msg: dict) -> None:
        async with self._lock:
            self.out.write(json.dumps(msg) + "\n")
            self.out.flush()

    async def notify(self, method: str, params: dict) -> None:
        await self.write({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: dict) -> Any:
        self._ids += 1
        rid = self._ids
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self.write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return await fut

    async def update(self, sid: str, upd: dict) -> None:
        await self.notify("session/update", {"sessionId": sid, "update": upd})

    def config_options(self) -> list[dict] | None:
        if not ENV.get("FAKE_ACP_MODELS"):
            return None
        return [{
            "id": "model", "name": "Model", "category": "model", "type": "select", "currentValue": self.model,
            "options": [{"value": "fast", "name": "Fast"}, {"value": "smart", "name": "Smart"}],
        }]

    # -- request handlers -----------------------------------------------------
    async def handle(self, msg: dict) -> None:
        method, params, rid = msg.get("method"), msg.get("params") or {}, msg.get("id")
        if method is None:  # response to one of our requests
            fut = self._pending.pop(msg.get("id"), None)
            if fut and not fut.done():
                fut.set_result(msg.get("result") if "error" not in msg else {"error": msg["error"]})
            return
        log_msg(method, params)
        try:
            if method == "initialize":
                caps: dict[str, Any] = {"loadSession": bool(ENV.get("FAKE_ACP_LOAD")), "promptCapabilities": {"image": False, "audio": False, "embeddedContext": False}}
                if ENV.get("FAKE_ACP_RESUME_CAP"):
                    caps["sessionCapabilities"] = {"resume": {}}
                auth = [{"id": ENV["FAKE_ACP_AUTH"], "name": "API key from the environment"}] if ENV.get("FAKE_ACP_AUTH") else []
                await self.reply(rid, {"protocolVersion": 1, "agentCapabilities": caps, "agentInfo": {"name": "fake-acp", "version": "0.0.1"}, "authMethods": auth})
            elif method == "authenticate":
                if params.get("methodId") != ENV.get("FAKE_ACP_AUTH"):
                    await self.error(rid, -32602, "unknown auth method")
                else:
                    self.authenticated = True
                    await self.reply(rid, {})
            elif method == "session/new":
                if not self.authenticated:
                    await self.error(rid, -32000, "Authentication required")
                    return
                sid = f"fake-{len(self.sessions) + 1}"
                self.sessions[sid] = {"cwd": params.get("cwd")}
                resp: dict[str, Any] = {"sessionId": sid}
                if (opts := self.config_options()) is not None:
                    resp["configOptions"] = opts
                await self.reply(rid, resp)
            elif method in ("session/load", "session/resume"):
                if (method == "session/load" and not ENV.get("FAKE_ACP_LOAD")) or (method == "session/resume" and not ENV.get("FAKE_ACP_RESUME_CAP")):
                    await self.error(rid, -32601, "Method not found")
                    return
                sid = params["sessionId"]
                self.sessions[sid] = {"cwd": params.get("cwd")}
                if method == "session/load":  # replay history: the client must not turn these into room events
                    await self.update(sid, {"sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": "earlier question"}})
                    await self.update(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "earlier answer"}})
                resp = {}
                if (opts := self.config_options()) is not None:
                    resp["configOptions"] = opts
                await self.reply(rid, resp)
            elif method == "session/set_config_option":
                if params.get("configId") == "model" and params.get("value") in ("fast", "smart"):
                    self.model = params["value"]
                    await self.reply(rid, {"configOptions": self.config_options()})
                else:
                    await self.error(rid, -32602, "bad config option")
            elif method == "session/prompt":
                asyncio.create_task(self.prompt(rid, params))
            elif method == "session/cancel":
                self.cancelled.add(params.get("sessionId"))
            else:
                await self.error(rid, -32601, f"Method not found: {method}")
        except Exception as e:  # pragma: no cover
            if rid is not None:
                await self.error(rid, -32603, f"{type(e).__name__}: {e}")

    async def reply(self, rid: Any, result: Any) -> None:
        await self.write({"jsonrpc": "2.0", "id": rid, "result": result})

    async def error(self, rid: Any, code: int, message: str) -> None:
        await self.write({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})

    # -- one turn ---------------------------------------------------------------
    async def prompt(self, rid: Any, params: dict) -> None:
        sid = params["sessionId"]
        self.prompts += 1
        self.cancelled.discard(sid)
        slow = bool(ENV.get("FAKE_ACP_SLOW"))
        chunks = 40 if slow else int(ENV.get("FAKE_ACP_CHUNKS", "2"))
        crash_at = int(ENV.get("FAKE_ACP_CRASH_AT", "0"))
        words = ["Hello ", "there ", "from ", "the ", "fake ", "agent "]
        for i in range(chunks):
            if sid in self.cancelled:
                await self.reply(rid, {"stopReason": "cancelled"})
                return
            await self.update(sid, {"sessionUpdate": "agent_message_chunk", "messageId": "m1", "content": {"type": "text", "text": words[i % len(words)]}})
            await self.update(sid, {"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "(thinking)"}})
            if crash_at and self.prompts == crash_at and not os.path.exists(f"{LOG}.crashed"):
                open(f"{LOG}.crashed", "w").close()  # crash once: the restarted process must behave
                self.out.flush()
                os._exit(3)
            if slow:
                await asyncio.sleep(0.05)
        if sid in self.cancelled:
            await self.reply(rid, {"stopReason": "cancelled"})
            return
        tool = {"toolCallId": "call-1", "title": "Run tests", "kind": "execute", "status": "pending", "rawInput": {"command": "pytest -q"}}
        await self.update(sid, {"sessionUpdate": "tool_call", **tool})
        allowed = True
        if ENV.get("FAKE_ACP_PERMISSION"):
            answer = await self.request(
                "session/request_permission",
                {
                    "sessionId": sid,
                    "toolCall": {"toolCallId": "call-1", "title": "Run tests", "kind": "execute", "rawInput": {"command": "pytest -q"}},
                    "options": [
                        {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                        {"optionId": "allow-always", "name": "Always allow", "kind": "allow_always"},
                        {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
                    ],
                },
            )
            outcome = (answer or {}).get("outcome") or {}
            if outcome.get("outcome") == "cancelled":
                await self.reply(rid, {"stopReason": "cancelled"})
                return
            allowed = outcome.get("optionId") in ("allow", "allow-always")
        if allowed:
            await self.update(sid, {"sessionUpdate": "tool_call_update", "toolCallId": "call-1", "status": "completed", "content": [{"type": "content", "content": {"type": "text", "text": "3 passed"}}]})
        else:
            await self.update(sid, {"sessionUpdate": "tool_call_update", "toolCallId": "call-1", "status": "failed", "rawOutput": {"error": "denied by the room"}})
        await self.update(sid, {"sessionUpdate": "agent_message_chunk", "messageId": "m2", "content": {"type": "text", "text": "done."}})
        await self.update(sid, {"sessionUpdate": "usage_update", "used": 1200, "size": 200000, "cost": {"amount": 0.0042, "currency": "USD"}})
        await self.reply(rid, {"stopReason": "end_turn"})


async def main() -> None:
    agent = Agent()
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=32 * 1024 * 1024)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    while True:
        line = await reader.readline()
        if not line:
            return
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            print(f"fake-acp: bad json {line[:80]!r}", file=sys.stderr, flush=True)
            continue
        await agent.handle(msg)


if __name__ == "__main__":
    print("fake-acp: starting", file=sys.stderr, flush=True)
    asyncio.run(main())
