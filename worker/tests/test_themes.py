"""Custom UI themes: validation of theme.json / theme.css, the machine default, docs and skill install, admin routes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from marvin.admin import make_admin_app
from marvin.sandbox import Sandbox, SandboxConfig
from marvin.themes import ThemeStore, validate_css, validate_json
from marvin.config import RoomConfig

GOOD = {
    "name": "Night Shift", "description": "navy + amber", "scheme": "dark",
    "fonts": {"ui": "Manrope", "mono": "DM Mono", "google": "family=Manrope:wght@400;700&family=DM+Mono"},
    "presence": {"agent": "orb", "speaker": "bars"},
    "tokens": {"--bg": "#0d1220", "--accent": "#f0b35c", "--radius": "10px"},
}


def write_theme(root: Path, theme_id: str, meta: dict | str, css: str | None = None) -> Path:
    d = root / "themes" / theme_id
    d.mkdir(parents=True)
    (d / "theme.json").write_text(meta if isinstance(meta, str) else json.dumps(meta))
    if css is not None:
        (d / "theme.css").write_text(css)
    return d


def test_validate_json_accepts_the_contract():
    t = validate_json("night-shift", GOOD)
    assert t.valid and t.name == "Night Shift" and t.scheme == "dark"
    assert t.fonts["google"] == "family=Manrope:wght@400;700&family=DM+Mono"
    assert t.presence == {"agent": "orb", "speaker": "bars"}
    assert t.tokens == {"--bg": "#0d1220", "--accent": "#f0b35c", "--radius": "10px"}


def test_validate_json_collects_every_problem():
    bad = {**GOOD, "scheme": "sepia", "presence": {"agent": "hologram"}, "tokens": {"--bg": "url(x)", "--nope": "1", "color": "red"},
           "fonts": {"google": "javascript:alert(1)"}}
    t = validate_json("Bad_Id", bad)
    msgs = "\n".join(t.errors)
    assert "not a valid id" in msgs
    assert "scheme" in msgs and "presence.agent" in msgs and "token --bg" in msgs and "must start with --" in msgs and "fonts.google" in msgs
    assert any("--nope" in w for w in t.warnings)  # unknown tokens are dropped, not fatal
    assert "--nope" not in t.tokens


def test_builtin_ids_are_reserved():
    assert any("built-in" in e for e in validate_json("signal", GOOD).errors)


def test_validate_css_blocks_imports_and_foreign_urls():
    assert validate_css(".left { color: red } @keyframes x { 50% { opacity: .5 } }") == []
    assert validate_css("@font-face { src: url(https://fonts.gstatic.com/s/x.woff2) } .a { background: url(data:image/png;base64,AAA) }") == []
    errs = validate_css("@import url(https://evil.example/x.css); .a { background: url(https://evil.example/t.png) } .b::after { content: '<' }")
    assert any("@import" in e for e in errs) and any("evil.example" in e for e in errs) and any("'<'" in e for e in errs)
    assert any("KB" in e for e in validate_css("a{}" * 120_000))


def test_store_lists_valid_and_invalid_themes(tmp_path: Path):
    write_theme(tmp_path, "night-shift", GOOD, ".rail { display: none }")
    write_theme(tmp_path, "broken", "{ not json")
    write_theme(tmp_path, "sneaky", GOOD, "@import url(https://evil.example/x.css);")
    (tmp_path / "themes" / ".hidden").mkdir()
    store = ThemeStore(str(tmp_path))
    themes = {t.id: t for t in store.list()}
    assert set(themes) == {"night-shift", "broken", "sneaky"}
    assert themes["night-shift"].valid and themes["night-shift"].has_css
    assert not themes["broken"].valid and "not valid JSON" in themes["broken"].errors[0]
    assert not themes["sneaky"].valid
    assert store.css("night-shift") == ".rail { display: none }"
    assert store.css("sneaky") is None  # rejected CSS is never served
    assert store.css("nope") is None
    wire = themes["night-shift"].to_wire()
    assert wire["css"] == "/api/themes/night-shift/theme.css" and wire["builtin"] is False


def test_default_env_then_settings_then_builtin(tmp_path: Path):
    store = ThemeStore(str(tmp_path), env={})
    assert store.default() == ("control-room", "builtin")
    with pytest.raises(ValueError):
        store.set_default("missing-theme")
    write_theme(tmp_path, "night-shift", GOOD)
    store.set_default("night-shift")
    assert store.default() == ("night-shift", "settings")
    store.set_default("editorial")  # built-ins are always acceptable
    assert store.default() == ("editorial", "settings")
    assert ThemeStore(str(tmp_path), env={"MARVIN_THEME": "signal"}).default() == ("signal", "env")
    store.set_default(None)
    assert store.default() == ("control-room", "builtin")


def test_delete_clears_the_default(tmp_path: Path):
    store = ThemeStore(str(tmp_path), env={})
    write_theme(tmp_path, "night-shift", GOOD)
    store.set_default("night-shift")
    store.delete("night-shift")
    assert store.list() == [] and store.default() == ("control-room", "builtin")
    with pytest.raises(KeyError):
        store.delete("night-shift")
    with pytest.raises(KeyError):
        store.delete("../etc")


def test_docs_and_skill_are_installed(tmp_path: Path):
    store = ThemeStore(str(tmp_path))
    store.install_docs()
    readme = tmp_path / "themes" / "README.md"
    assert readme.exists() and "theme.json" in readme.read_text() and "--accent" in readme.read_text()
    text = readme.read_text()
    assert "full-page" in text and "four icon buttons" in text
    skill = ThemeStore.install_skill(tmp_path / "home")
    assert skill == tmp_path / "home" / ".claude" / "skills" / "marvin-theme" / "SKILL.md"
    skill_text = skill.read_text()
    assert "MARVIN_THEMES_DIR" in skill_text
    assert "rearrange the chrome" in skill_text
    assert store.agent_env() == {"MARVIN_THEMES_DIR": str(tmp_path / "themes")}
    assert ThemeStore(None).agent_env() == {} and not ThemeStore(None).enabled


def test_sandbox_mounts_the_themes_dir(tmp_path: Path):
    sb = Sandbox(SandboxConfig(mode="docker"), state_dir=str(tmp_path), notes_path=tmp_path / "none")
    cfg = RoomConfig(name="dev", repo=str(tmp_path / "repo"))
    themes = str(tmp_path / "themes")
    assert any(m.src == themes and m.dst == themes and not m.ro for m in sb.mounts_for(cfg))
    assert "MARVIN_THEMES_DIR" in SandboxConfig().forward_env


class _Mgr:
    def describe(self):
        return []


async def test_admin_routes(tmp_path: Path):
    write_theme(tmp_path, "night-shift", GOOD, ".rail { display: none }")
    store = ThemeStore(str(tmp_path), env={})
    app = make_admin_app(_Mgr(), None, store)  # type: ignore[arg-type]
    async with TestClient(TestServer(app)) as c:
        r = await c.get("/themes")
        j = await r.json()
        assert r.status == 200 and [t["id"] for t in j["themes"]] == ["night-shift"] and j["default"] == "control-room"
        r = await c.get("/themes/night-shift/theme.css")
        assert r.status == 200 and r.content_type == "text/css" and await r.text() == ".rail { display: none }"
        assert (await c.get("/themes/nope/theme.css")).status == 404
        # writes need the admin role (the token server enforces it too; checked again here)
        r = await c.put("/themes/default", json={"id": "night-shift"}, headers={"X-Marvin-User": "gil", "X-Marvin-Roles": "participant"})
        assert r.status == 403
        r = await c.put("/themes/default", json={"id": "night-shift"}, headers={"X-Marvin-User": "gil", "X-Marvin-Roles": "admin,participant"})
        assert r.status == 200 and (await r.json())["default"] == "night-shift"
        r = await c.put("/themes/default", json={"id": "missing"}, headers={"X-Marvin-Roles": "admin"})
        assert r.status == 400
        r = await c.delete("/themes/night-shift", headers={"X-Marvin-Roles": "admin"})
        assert r.status == 200 and (await r.json())["themes"] == [] and (await r.json())["default"] == "control-room"
