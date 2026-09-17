"""Settings-stored harness credentials: encrypted keys, env override, Grok device login."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from marvin.admin import make_admin_app
from marvin.harness_creds import HarnessCreds, _grok_login_cmd, parse_device_output


def creds(tmp_path, monkeypatch, **env) -> HarnessCreds:
    for k in ("ANTHROPIC_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY", "MARVIN_HARNESS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return HarnessCreds(str(tmp_path), secret="s3")


def test_key_encrypts_and_env_wins(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch)
    c.put_key("xai", "xai-supersecret-key")
    raw = (tmp_path / "harness.json").read_text()
    assert "xai-supersecret-key" not in raw
    assert (tmp_path / "harness.json").stat().st_mode & 0o777 == 0o600
    assert c.get_key("xai") == "xai-supersecret-key"
    assert c.env()["XAI_API_KEY"] == "xai-supersecret-key"
    st = c.status()
    xai = next(p for p in st["providers"] if p["id"] == "xai")
    assert xai["key_set"] and xai["key_source"] == "settings" and "supersecret" not in (xai["key_hint"] or "")
    # environment overrides the stored key
    monkeypatch.setenv("XAI_API_KEY", "xai-from-the-env-xx")
    c2 = HarnessCreds(str(tmp_path), secret="s3")
    assert "XAI_API_KEY" not in c2.env()
    xai = next(p for p in c2.status()["providers"] if p["id"] == "xai")
    assert xai["key_source"] == "env" and xai["key_hint"].startswith("xai-")


def test_ready_is_true_when_any_provider_is_set(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch)
    assert c.ready()["ready"] is False
    c.put_key("xai", "xai-supersecret-key")
    assert c.ready()["ready"] is True and c.ready()["label"] == "xAI (Grok)"


def test_key_shape(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="sk-ant-"):
        c.put_key("anthropic", "not-an-anthropic-key")
    with pytest.raises(ValueError, match="too short"):
        c.put_key("xai", "xai-short")
    with pytest.raises(ValueError, match="Anthropic"):
        c.put_key("openai", "sk-ant-not-for-openai-here")
    c.put_key("anthropic", "sk-ant-abcdefghijklmnopqrstuvwxyz")
    assert c.get_key("anthropic").startswith("sk-ant-")


def test_wrong_secret_drops_key(tmp_path, monkeypatch):
    creds(tmp_path, monkeypatch).put_key("xai", "xai-supersecret-key")
    other = HarnessCreds(str(tmp_path), secret="other")
    assert other.get_key("xai") is None
    assert json.loads((tmp_path / "harness.json").read_text())["keys"] == {}


def test_default_harness_settings_win_over_env(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch)
    assert c.status()["default_source"] == "builtin"
    c.set_default_harness("grok")
    assert os.environ["MARVIN_HARNESS"] == "grok"
    assert c.status()["default_source"] == "settings"
    monkeypatch.setenv("MARVIN_HARNESS", "codex")
    c2 = HarnessCreds(str(tmp_path), secret="s3")
    assert c2.status()["default_harness"] == "grok" and c2.status()["default_source"] == "settings"


def test_stock_claude_env_is_not_an_override(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch, MARVIN_HARNESS="claude-code")
    assert c.status()["default_harness"] == "claude-code" and c.status()["default_source"] == "builtin"


def test_env_seeds_when_settings_empty(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch, MARVIN_HARNESS="codex")
    assert c.status()["default_harness"] == "codex" and c.status()["default_source"] == "env"
    c.set_default_harness("grok")
    assert c.status()["default_harness"] == "grok" and c.status()["default_source"] == "settings"


def test_only_grok_becomes_default(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch, MARVIN_HARNESS="claude-code")
    c.put_grok_session(json.dumps({"ok": True}))
    st = c.status()
    assert st["default_harness"] == "grok" and st["default_source"] == "settings"


def test_grok_does_not_steal_default_when_other_key_exists(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch)
    c.put_key("anthropic", "sk-ant-abcdefghijklmnopqrstuvwxyz")
    assert c.status()["default_harness"] == "claude-code"
    c.put_grok_session(json.dumps({"ok": True}))
    assert c.status()["default_harness"] == "claude-code"


def test_forget_only_grok_clears_default(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch)
    c.put_grok_session(json.dumps({"ok": True}))
    assert c.status()["default_harness"] == "grok"
    c.forget_grok_session()
    assert c.status()["default_source"] == "builtin"


def test_existing_only_grok_is_adopted_on_load(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch)
    c.put_grok_session(json.dumps({"ok": True}))
    c.set_default_harness(None)
    loaded = HarnessCreds(str(tmp_path), secret="s3")
    assert loaded.status()["default_harness"] == "grok" and loaded.status()["default_source"] == "settings"


def test_install_home_writes_grok_session(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch)
    blob = json.dumps({"https://accounts.x.ai/sign-in": {"key": "sess"}})
    c.put_grok_session(blob)
    home = tmp_path / "room-home"
    c.install_home(home)
    dest = home / ".grok" / "auth.json"
    assert dest.read_text() == blob
    assert dest.stat().st_mode & 0o777 == 0o600
    c.forget_grok_session()
    c.install_home(home)
    assert not dest.exists()


def test_grok_login_cmd_mounts_named_volume(monkeypatch):
    monkeypatch.setattr("marvin.harness_creds.shutil.which", lambda n: "/usr/bin/docker" if n == "docker" else None)
    monkeypatch.setenv("MARVIN_SANDBOX_MOUNTS", "marvin_work:/work")
    cmd = _grok_login_cmd(Path("/work/state/grok-login/abc"))
    assert "marvin_work:/work" in cmd
    assert any(x.endswith("HOME=/work/state/grok-login/abc") for x in cmd)
    assert not any(":/home/marvin" in x for x in cmd)


def test_parse_device_output():
    code, url = parse_device_output("Open https://accounts.x.ai/device and enter code: ABCD-1234\n")
    assert code == "ABCD-1234" and "accounts.x.ai" in (url or "")
    code, url = parse_device_output("visit https://auth.x.ai/activate\nABCD-99ZZ\n")
    assert code == "ABCD-99ZZ" and url


async def test_grok_login_fake_runner(tmp_path, monkeypatch):
    async def runner(flow, home):
        flow.user_code = "WXYZ-7788"
        flow.verification_uri = "https://accounts.x.ai/device"
        flow.ready.set()
        (home / ".grok").mkdir(parents=True, exist_ok=True)
        (home / ".grok" / "auth.json").write_text('{"ok": true}')
        flow.creds.put_grok_session('{"ok": true}')
        flow.status = "connected"

    for k in ("ANTHROPIC_API_KEY", "XAI_API_KEY", "MARVIN_HARNESS"):
        monkeypatch.delenv(k, raising=False)
    c = HarnessCreds(str(tmp_path), secret="s3", runner=runner)
    flow = await c.start_grok_login()
    assert flow.user_code == "WXYZ-7788" and flow.status == "connected"
    assert json.loads(c.grok_auth_json()) == {"ok": True}
    assert c.status()["providers"][1]["subscription_set"] is True  # xai is second
    assert c.status()["default_harness"] == "grok" and c.status()["default_source"] == "settings"


class _Mgr:
    def describe(self):
        return []


async def test_admin_harness_creds_require_admin(tmp_path, monkeypatch):
    c = creds(tmp_path, monkeypatch)
    app = make_admin_app(_Mgr(), harness_creds=c)  # type: ignore[arg-type]
    async with TestClient(TestServer(app)) as client:
        assert (await client.get("/harness-creds")).status == 403
        r = await client.get("/harness-creds", headers={"X-Marvin-Roles": "admin"})
        assert r.status == 200
        body = await r.json()
        assert {p["id"] for p in body["providers"]} >= {"anthropic", "xai", "openai"}
        bad = await client.put("/harness-creds/xai", json={"key": "nope"}, headers={"X-Marvin-Roles": "admin"})
        assert bad.status == 400
        ok = await client.put("/harness-creds/xai", json={"key": "xai-supersecret-key"}, headers={"X-Marvin-Roles": "admin"})
        assert ok.status == 200 and (await ok.json())["providers"][1]["key_set"]
        gone = await client.delete("/harness-creds/xai", headers={"X-Marvin-Roles": "admin"})
        assert gone.status == 200 and not (await gone.json())["providers"][1]["key_set"]
