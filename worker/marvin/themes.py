"""Custom UI themes: folders under <state_dir>/themes, each with theme.json and an optional theme.css.

The web app ships three themes of its own (control-room, editorial, signal); this module handles the ones people, or
the agent in a room, add on this machine. A theme is data and CSS, never code: the worker validates the JSON against
the contract in theme_docs/README.md and rejects CSS that could pull in anything (`@import`, `url(` other than data:
or Google Fonts). Invalid themes are still listed, with their errors, so Settings can say what is wrong.

The directory is mounted into every room sandbox at the same path and named by MARVIN_THEMES_DIR in the agent's
environment; the README in it is the agent's instructions and the Claude Code skill (theme_docs/SKILL.md) is
installed into each room HOME, so "Marvin, make me a theme" works from any room.

Machine default: MARVIN_THEME in the environment overrides; else <themes>/default.json written from Settings; else the
web app's own default.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("marvin.themes")

DOCS = Path(__file__).parent / "theme_docs"
BUILTIN_IDS = ("control-room", "editorial", "signal")
FALLBACK_DEFAULT = "control-room"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
GOOGLE_RE = re.compile(r"^[A-Za-z0-9+:;@,&=.\- ]{1,600}$")
FONT_RE = re.compile(r"^[A-Za-z0-9 ,'\"\-]{1,120}$")
TOKEN_VALUE_BAD = re.compile(r"url\(|[;{}<]", re.I)
CSS_MAX_BYTES = 200_000
CSS_FORBIDDEN = (("@import", "@import is not allowed"), ("expression(", "expression() is not allowed"), ("javascript:", "javascript: is not allowed"),
                 ("behavior:", "behavior: is not allowed"), ("-moz-binding", "-moz-binding is not allowed"), ("<", "'<' is not allowed in CSS"))
CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]*)", re.I)
URL_OK = ("data:", "https://fonts.googleapis.com/", "https://fonts.gstatic.com/")
AGENT_VARIANTS = ("dot", "scope", "ink", "orb", "bars")
SPEAKER_VARIANTS = ("dot", "bars", "ink", "ring")
TOKENS = (
    "--bg", "--panel", "--panel-2", "--line", "--fg", "--fg-2", "--dim", "--accent", "--accent-fg", "--sel", "--ok", "--warn", "--warn-bg", "--bad",
    "--exec", "--read", "--write", "--ins-bg", "--del-bg", "--glow", "--font-ui", "--font-display", "--font-mono", "--text", "--radius", "--radius-lg",
    "--shadow", "--left-w", "--right-w",
)


@dataclass
class Theme:
    id: str
    name: str = ""
    description: str = ""
    author: str = ""
    scheme: str = "dark"
    fonts: dict[str, str] = field(default_factory=dict)
    presence: dict[str, str] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    has_css: bool = False
    mtime: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_wire(self) -> dict:
        return {
            "id": self.id, "name": self.name or self.id, "description": self.description, "author": self.author, "scheme": self.scheme,
            "fonts": self.fonts, "presence": self.presence, "tokens": self.tokens, "css": f"/api/themes/{self.id}/theme.css" if self.has_css else None,
            "mtime": self.mtime, "valid": self.valid, "errors": self.errors, "warnings": self.warnings, "builtin": False,
        }


def validate_json(theme_id: str, raw: object) -> Theme:
    """The contract from theme_docs/README.md, as code. Collects every problem instead of stopping at the first."""
    t = Theme(id=theme_id)
    if not ID_RE.match(theme_id):
        t.errors.append(f"folder name {theme_id!r} is not a valid id (lowercase letters, digits, dashes, 2-40 chars)")
    if theme_id in BUILTIN_IDS:
        t.errors.append(f"{theme_id!r} is a built-in theme; pick another id")
    if not isinstance(raw, dict):
        t.errors.append("theme.json must be a JSON object")
        return t
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 60:
        t.errors.append("name is required (1-60 characters)")
    else:
        t.name = name.strip()
    for key, limit in (("description", 300), ("author", 60)):
        v = raw.get(key, "")
        if v is None:
            v = ""
        if not isinstance(v, str) or len(v) > limit:
            t.errors.append(f"{key} must be a string of at most {limit} characters")
        else:
            setattr(t, key, v.strip())
    scheme = raw.get("scheme")
    if scheme not in ("dark", "light"):
        t.errors.append('scheme must be "dark" or "light"')
    else:
        t.scheme = scheme
    fonts = raw.get("fonts", {}) or {}
    if not isinstance(fonts, dict):
        t.errors.append("fonts must be an object")
    else:
        for key in ("ui", "display", "mono"):
            v = fonts.get(key)
            if v is None:
                continue
            if not isinstance(v, str) or not FONT_RE.match(v):
                t.errors.append(f"fonts.{key} must be a font-family name")
            else:
                t.fonts[key] = v.strip()
        g = fonts.get("google")
        if g is not None:
            if not isinstance(g, str) or not GOOGLE_RE.match(g) or "family=" not in g:
                t.errors.append("fonts.google must look like family=Name:wght@400;700&family=Other")
            else:
                t.fonts["google"] = g.strip().lstrip("?&")
        for k in fonts:
            if k not in ("ui", "display", "mono", "google"):
                t.warnings.append(f"fonts.{k} is not used")
    presence = raw.get("presence", {}) or {}
    if not isinstance(presence, dict):
        t.errors.append("presence must be an object")
    else:
        for key, allowed in (("agent", AGENT_VARIANTS), ("speaker", SPEAKER_VARIANTS)):
            v = presence.get(key)
            if v is None:
                continue
            if v not in allowed:
                t.errors.append(f"presence.{key} must be one of {', '.join(allowed)}")
            else:
                t.presence[key] = v
    tokens = raw.get("tokens", {}) or {}
    if not isinstance(tokens, dict):
        t.errors.append("tokens must be an object of --token: value")
    else:
        for k, v in tokens.items():
            if not isinstance(k, str) or not k.startswith("--"):
                t.errors.append(f"token {k!r} must start with --")
                continue
            if k not in TOKENS:
                t.warnings.append(f"token {k} is not one the app uses (ignored)")
                continue
            if not isinstance(v, (str, int, float)) or len(str(v)) > 200 or TOKEN_VALUE_BAD.search(str(v)):
                t.errors.append(f"token {k}: value must be a short CSS value without url(), ';', braces or '<'")
                continue
            t.tokens[k] = str(v).strip()
    return t


def validate_css(text: str) -> list[str]:
    errors: list[str] = []
    if len(text.encode()) > CSS_MAX_BYTES:
        errors.append(f"theme.css is larger than {CSS_MAX_BYTES // 1000} KB")
    low = text.lower()
    for needle, msg in CSS_FORBIDDEN:
        if needle in low:
            errors.append(msg)
    for m in CSS_URL_RE.finditer(text):
        u = m.group(1).strip()
        if not u.startswith(URL_OK):
            errors.append(f"url({u[:60]!r}) is not allowed: only data: and Google Fonts")
    return errors


class ThemeStore:
    def __init__(self, state_dir: str | None, env=os.environ) -> None:
        self.dir = Path(state_dir) / "themes" if state_dir else None
        self.env_default = (env.get("MARVIN_THEME") or "").strip() or None

    @property
    def enabled(self) -> bool:
        return self.dir is not None

    # -- setup ---------------------------------------------------------------------
    def install_docs(self) -> None:
        """The contract lives next to the themes so an agent in any room finds it; refreshed at every start."""
        if not self.dir:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        src = DOCS / "README.md"
        dst = self.dir / "README.md"
        if src.exists() and (not dst.exists() or dst.read_text() != src.read_text()):
            shutil.copyfile(src, dst)

    @staticmethod
    def install_skill(home: Path) -> Path | None:
        """Claude Code user-level skill in `home`/.claude/skills/marvin-theme; other harnesses read the README (the
        room prompt tells them). Idempotent."""
        src = DOCS / "SKILL.md"
        if not src.exists():
            return None
        dst = home / ".claude" / "skills" / "marvin-theme" / "SKILL.md"
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or dst.read_text() != src.read_text():
                shutil.copyfile(src, dst)
        except OSError as e:
            log.warning("themes: cannot install the skill into %s: %s", home, e)
            return None
        return dst

    def agent_env(self) -> dict[str, str]:
        return {"MARVIN_THEMES_DIR": str(self.dir)} if self.dir else {}

    # -- reading -------------------------------------------------------------------
    def load(self, theme_id: str) -> Theme | None:
        if not self.dir:
            return None
        d = self.dir / theme_id
        if not d.is_dir() or theme_id.startswith("."):
            return None
        meta = d / "theme.json"
        css = d / "theme.css"
        if not meta.exists():
            t = Theme(id=theme_id, errors=["theme.json is missing"])
        else:
            try:
                raw = json.loads(meta.read_text())
            except (OSError, ValueError) as e:
                raw = None
                t = Theme(id=theme_id, errors=[f"theme.json is not valid JSON: {e}"])
            if raw is not None:
                t = validate_json(theme_id, raw)
        mt = [meta.stat().st_mtime] if meta.exists() else []
        if css.exists():
            t.has_css = True
            try:
                t.errors.extend(validate_css(css.read_text(errors="replace")))
            except OSError as e:
                t.errors.append(f"theme.css cannot be read: {e}")
            mt.append(css.stat().st_mtime)
        t.mtime = max(mt) if mt else d.stat().st_mtime
        return t

    def list(self) -> list[Theme]:
        if not self.dir or not self.dir.exists():
            return []
        out = [t for t in (self.load(p.name) for p in sorted(self.dir.iterdir()) if p.is_dir()) if t]
        return out

    def css(self, theme_id: str) -> str | None:
        """The stylesheet of a valid theme; None when the theme is missing or invalid (never serve rejected CSS)."""
        t = self.load(theme_id)
        if not t or not t.valid or not t.has_css:
            return None
        return (self.dir / theme_id / "theme.css").read_text(errors="replace")  # type: ignore[union-attr]

    def delete(self, theme_id: str) -> None:
        if not self.dir or not ID_RE.match(theme_id):
            raise KeyError(theme_id)
        d = self.dir / theme_id
        if not d.is_dir():
            raise KeyError(theme_id)
        shutil.rmtree(d)
        if self.stored_default() == theme_id:
            self.set_default(None)

    # -- the machine default -------------------------------------------------------
    def stored_default(self) -> str | None:
        if not self.dir:
            return None
        f = self.dir / "default.json"
        try:
            v = json.loads(f.read_text()).get("id") if f.exists() else None
            return v if isinstance(v, str) and v else None
        except (OSError, ValueError):
            return None

    def default(self) -> tuple[str, str]:
        """(theme id, where it comes from: env | settings | builtin)."""
        if self.env_default:
            return self.env_default, "env"
        s = self.stored_default()
        if s:
            return s, "settings"
        return FALLBACK_DEFAULT, "builtin"

    def set_default(self, theme_id: str | None) -> None:
        if not self.dir:
            raise ValueError("no state directory: the default theme cannot be stored")
        if theme_id is not None:
            if not ID_RE.match(theme_id):
                raise ValueError(f"{theme_id!r} is not a theme id")
            if theme_id not in BUILTIN_IDS:
                t = self.load(theme_id)
                if not t:
                    raise ValueError(f"no theme {theme_id!r} on this machine")
                if not t.valid:
                    raise ValueError(f"theme {theme_id!r} is invalid: {t.errors[0]}")
        self.dir.mkdir(parents=True, exist_ok=True)
        f = self.dir / "default.json"
        if theme_id is None:
            if f.exists():
                f.unlink()
            return
        f.write_text(json.dumps({"id": theme_id, "set_at": time.time()}))

    def describe(self) -> dict:
        d, source = self.default()
        return {"themes": [t.to_wire() for t in self.list()], "default": d, "default_source": source, "dir": str(self.dir) if self.dir else None}
