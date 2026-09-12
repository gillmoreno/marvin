"""AcpHarness against tests/fake_acp_agent.py (a real subprocess speaking ACP over stdio)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from marvin.adapters.acp import AcpError, AcpHarness
from marvin.adapters.permissions import PermissionBroker

FAKE = str(Path(__file__).with_name("fake_acp_agent.py"))


def make(tmp_path, *, env: dict[str, str] | None = None, resume: str | None = None, model: str | None = None, permissions=None) -> tuple[AcpHarness, Path]:
    logf = tmp_path / "agent.log"
    e = {"FAKE_ACP_LOG": str(logf), **(env or {})}
    h = AcpHarness(str(tmp_path), permissions, agent_name="Marvin", room="r", command=[sys.executable, FAKE], env=e, model=model, resume=resume, name="fake")
    return h, logf


def calls(logf: Path) -> list[dict]:
    return [json.loads(l) for l in logf.read_text().splitlines()] if logf.exists() else []


async def collect(h: AcpHarness, prompt: str):
    return [ev async for ev in h.send(prompt)]


async def test_stream_basic(tmp_path):
    h, logf = make(tmp_path)
    await h.start()
    try:
        assert h.session_id == "fake-1" and h.agent_info["name"] == "fake-acp"
        evs = await collect(h, "hello")
        kinds = [e.kind for e in evs]
        assert kinds == ["turn_start", "text_delta", "text_delta", "text", "tool_use", "tool_result", "text_delta", "text", "result"]
        assert evs[3].data["text"] == "Hello there "
        assert evs[4].data == {"id": "call-1", "tool": "Run tests", "input": {"command": "pytest -q"}}
        assert evs[5].data == {"id": "call-1", "output": "3 passed", "is_error": False}
        assert evs[7].data["text"] == "done."
        res = evs[-1].data
        assert res["subtype"] == "end_turn" and res["is_error"] is False and res["session_id"] == "fake-1"
        assert res["cost_usd"] == pytest.approx(0.0042) and res["num_turns"] == 1 and res["duration_ms"] >= 0
        # the reasoning chunks were dropped
        assert not any("thinking" in json.dumps(e.data) for e in evs)
        init = next(c for c in calls(logf) if c["method"] == "initialize")
        assert init["params"]["protocolVersion"] == 1 and init["params"]["clientCapabilities"]["fs"] == {"readTextFile": False, "writeTextFile": False}
    finally:
        await h.close()


async def test_permission_allow_and_deny(tmp_path):
    decisions: list[bool] = [True, False]
    seen: list[tuple[str, dict]] = []

    async def notify(req):
        seen.append((req.tool, req.input))
        broker.resolve(req.id, decisions.pop(0))

    broker = PermissionBroker(notify)
    h, _ = make(tmp_path, env={"FAKE_ACP_PERMISSION": "1"})
    h.permissions = broker  # assigned after construction, like RoomSession does
    await h.start()
    try:
        evs = await collect(h, "run the tests")
        tr = next(e for e in evs if e.kind == "tool_result")
        assert tr.data["is_error"] is False and tr.data["output"] == "3 passed"
        evs = await collect(h, "again")
        tr = next(e for e in evs if e.kind == "tool_result")
        assert tr.data["is_error"] is True and "denied" in tr.data["output"]
        assert seen == [("Run tests", {"command": "pytest -q"})] * 2
        assert evs[-1].data["subtype"] == "end_turn"
    finally:
        await h.close()


async def test_permission_without_broker_is_rejected(tmp_path):
    h, _ = make(tmp_path, env={"FAKE_ACP_PERMISSION": "1"})
    await h.start()
    try:
        evs = await collect(h, "run")
        assert next(e for e in evs if e.kind == "tool_result").data["is_error"] is True
    finally:
        await h.close()


async def test_interrupt_yields_cancelled(tmp_path):
    h, logf = make(tmp_path, env={"FAKE_ACP_SLOW": "1"})
    await h.start()
    try:
        evs = []
        async for ev in h.send("long task"):
            evs.append(ev)
            if len([e for e in evs if e.kind == "text_delta"]) == 2:
                await h.interrupt()
        assert evs[-1].kind == "result" and evs[-1].data["subtype"] == "cancelled" and evs[-1].data["is_error"] is False
        assert len([e for e in evs if e.kind == "text_delta"]) < 40
        assert any(c["method"] == "session/cancel" for c in calls(logf))
        # the harness is still usable afterwards
        evs = await collect(h, "short")
        assert evs[-1].data["subtype"] == "end_turn"
    finally:
        await h.close()


async def test_interrupt_while_waiting_for_permission(tmp_path):
    async def never(req):
        pass

    broker = PermissionBroker(never)
    h, _ = make(tmp_path, env={"FAKE_ACP_PERMISSION": "1"}, permissions=broker)
    await h.start()
    try:
        evs = []
        async for ev in h.send("run"):
            evs.append(ev)
            if ev.kind == "tool_use":
                await asyncio.sleep(0.05)
                assert broker.pending, "the room should have been asked"
                await h.interrupt()
        assert evs[-1].data["subtype"] == "cancelled" and broker.pending == []
    finally:
        await h.close()


async def test_resume_uses_session_load_when_advertised(tmp_path):
    h, logf = make(tmp_path, env={"FAKE_ACP_LOAD": "1"}, resume="old-session")
    await h.start()
    try:
        assert h.session_id == "old-session"
        methods = [c["method"] for c in calls(logf)]
        assert "session/load" in methods and "session/new" not in methods
        load = next(c for c in calls(logf) if c["method"] == "session/load")
        assert load["params"]["sessionId"] == "old-session" and load["params"]["cwd"] == str(tmp_path) and load["params"]["mcpServers"] == []
        evs = await collect(h, "next")
        # replayed history did not leak into the turn, and a resumed session gets no system prompt
        assert [e.kind for e in evs][:3] == ["turn_start", "text_delta", "text_delta"]
        assert "earlier answer" not in json.dumps([e.data for e in evs])
        prompt = next(c for c in calls(logf) if c["method"] == "session/prompt")
        assert prompt["params"]["prompt"][0]["text"] == "next"
    finally:
        await h.close()


async def test_resume_prefers_session_resume_capability(tmp_path):
    h, logf = make(tmp_path, env={"FAKE_ACP_LOAD": "1", "FAKE_ACP_RESUME_CAP": "1"}, resume="old-session")
    await h.start()
    try:
        methods = [c["method"] for c in calls(logf)]
        assert "session/resume" in methods and "session/load" not in methods and h.session_id == "old-session"
    finally:
        await h.close()


async def test_resume_falls_back_to_new_session(tmp_path):
    h, logf = make(tmp_path, resume="old-session")
    await h.start()
    try:
        methods = [c["method"] for c in calls(logf)]
        assert "session/load" not in methods and "session/new" in methods
        assert h.session_id == "fake-1"
    finally:
        await h.close()


async def test_system_prompt_only_on_first_prompt(tmp_path):
    h, logf = make(tmp_path)
    await h.start()
    try:
        await collect(h, "first question")
        await collect(h, "second question")
        prompts = [c["params"]["prompt"][0]["text"] for c in calls(logf) if c["method"] == "session/prompt"]
        assert len(prompts) == 2
        assert prompts[0].startswith("# Room instructions\nYou are Marvin,") and "marvin/r/<short-topic>" in prompts[0] and prompts[0].endswith("# Message\nfirst question")
        assert prompts[1] == "second question"
    finally:
        await h.close()


async def test_agent_crash_mid_turn_then_recovers(tmp_path):
    h, logf = make(tmp_path, env={"FAKE_ACP_CRASH_AT": "1"})
    await h.start()
    try:
        evs = await collect(h, "crash please")
        kinds = [e.kind for e in evs]
        assert kinds[:2] == ["turn_start", "text_delta"] and kinds[-2:] == ["error", "result"]
        assert evs[-1].data["is_error"] is True and "exited" in evs[-2].data["message"]
        # next send restarts the agent (fresh process, new handshake) and works
        evs = await collect(h, "and again")
        assert evs[-1].kind == "result" and evs[-1].data["subtype"] == "end_turn"
        assert [c["method"] for c in calls(logf)].count("initialize") == 2
    finally:
        await h.close()


async def test_close_terminates_process(tmp_path):
    h, _ = make(tmp_path)
    await h.start()
    proc = h._proc
    assert proc is not None and proc.returncode is None
    await h.close()
    assert proc.returncode is not None and h._proc is None


async def test_authenticate_when_required(tmp_path):
    h, logf = make(tmp_path, env={"FAKE_ACP_AUTH": "api-key"})
    await h.start()
    try:
        methods = [c["method"] for c in calls(logf)]
        assert methods == ["initialize", "session/new", "authenticate", "session/new"]
        auth = next(c for c in calls(logf) if c["method"] == "authenticate")
        assert auth["params"]["methodId"] == "api-key" and h.session_id == "fake-1"
    finally:
        await h.close()


async def test_model_selection_through_config_options(tmp_path):
    h, logf = make(tmp_path, env={"FAKE_ACP_MODELS": "1"}, model="fast")
    await h.start()
    try:
        assert h.model == "fast" and [m["id"] for m in h.available_models] == ["fast", "smart"]
        setopt = next(c for c in calls(logf) if c["method"] == "session/set_config_option")
        assert setopt["params"] == {"sessionId": "fake-1", "configId": "model", "value": "fast"}
    finally:
        await h.close()
    # no model requested: the agent's current one is reported
    (tmp_path / "b").mkdir()
    h, logf = make(tmp_path / "b", env={"FAKE_ACP_MODELS": "1"})
    await h.start()
    try:
        assert h.model == "smart" and not any(c["method"] == "session/set_config_option" for c in calls(logf))
    finally:
        await h.close()


async def test_interactive_auth_fails_fast(tmp_path):
    h, logf = make(tmp_path, env={"FAKE_ACP_AUTH": "grok.com"})
    h.name = "grok"
    with pytest.raises(AcpError, match="Sign in with Grok"):
        await h.start()
    assert "authenticate" not in [c.get("method") for c in calls(logf)]


async def test_bad_command_raises_on_start(tmp_path):
    h = AcpHarness(str(tmp_path), None, command=["/nonexistent/acp-agent"], name="broken")
    with pytest.raises(Exception):
        await h.start()
    assert h._proc is None
