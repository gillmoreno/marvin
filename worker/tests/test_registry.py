import pytest

from marvin.adapters import registry
from marvin.adapters.acp import AcpHarness
from marvin.adapters.claude_code import ClaudeCodeHarness


def test_every_profile_is_launchable_and_documented():
    ids = [p.id for p in registry.profiles()]
    assert ids == ["claude-code", "claude-acp", "codex", "cursor", "gemini", "opencode", "grok", "copilot"]
    for p in registry.profiles():
        assert p.command and all(isinstance(c, str) and c for c in p.command), p.id
        assert p.auth.strip(), p.id
        assert p.kind in ("claude-sdk", "acp"), p.id
        wire = p.to_wire()
        assert wire["id"] == p.id and "env" not in wire and wire["command"] == p.command
    assert registry.get("claude-code").models and registry.get("claude-code").default_model == "claude-fable-5-1"
    assert registry.get("grok").command == ["grok", "agent", "stdio"]
    assert registry.get("cursor").command == ["agent", "acp"] and registry.get("copilot").command == ["copilot", "--acp"]


def test_command_override_from_env(monkeypatch):
    monkeypatch.setenv("MARVIN_HARNESS_CMD_CLAUDE_ACP", "/opt/wrappers/claude-acp --flag 'with space'")
    p = registry.get("claude-acp")
    assert registry.command_env_var("claude-acp") == "MARVIN_HARNESS_CMD_CLAUDE_ACP"
    assert registry.effective_command(p) == ["/opt/wrappers/claude-acp", "--flag", "with space"]
    assert p.to_wire()["command"] == ["/opt/wrappers/claude-acp", "--flag", "with space"]
    assert p.command == ["claude-agent-acp"]  # the profile itself is untouched
    monkeypatch.delenv("MARVIN_HARNESS_CMD_CLAUDE_ACP")
    assert registry.effective_command(p) == ["claude-agent-acp"]


def test_default_id_from_env(monkeypatch):
    monkeypatch.delenv("MARVIN_HARNESS", raising=False)
    assert registry.default_id() == "claude-code"
    monkeypatch.setenv("MARVIN_HARNESS", "opencode")
    assert registry.default_id() == "opencode"
    assert registry.get(None).id == "opencode"
    monkeypatch.setenv("MARVIN_HARNESS", "nope")
    assert registry.default_id() == "claude-code"  # unknown ids fall back rather than breaking every room
    with pytest.raises(KeyError):
        registry.get("nope")


def test_create_harness_returns_the_right_class(tmp_path, monkeypatch):
    monkeypatch.setenv("MARVIN_HARNESS_CMD_OPENCODE", "/usr/bin/true acp")
    h = registry.create_harness("opencode", str(tmp_path), agent_name="Marvin", room="r", model="gpt-x", resume="s1", add_dirs=["/x"])
    assert isinstance(h, AcpHarness) and h.name == "opencode" and h.command == ["/usr/bin/true", "acp"]
    assert h.session_id == "s1" and h.requested_model == "gpt-x" and h.add_dirs == ["/x"] and h.permissions is None
    assert "marvin/r/<short-topic>" in h.system_prompt
    c = registry.create_harness(registry.get("claude-code"), str(tmp_path), room="r", model="claude-sonnet-5")
    assert isinstance(c, ClaudeCodeHarness) and c.name == "claude-code" and c.model == "claude-sonnet-5"
    with pytest.raises(KeyError):
        registry.create_harness("nope", str(tmp_path))
