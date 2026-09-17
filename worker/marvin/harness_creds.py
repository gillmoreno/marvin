"""Machine credentials for coding-agent harnesses, set from Settings (not .env).

Each provider is an API key and, for Grok, an optional subscription login (`grok login --device-auth`).
Keys and the Grok session file are Fernet-encrypted in <state_dir>/harness.json. API keys still honour an
environment override. The default harness is chosen in Settings; MARVIN_HARNESS only seeds it when Settings
has no value, and MARVIN_HARNESS=claude-code is ignored (that is already the built-in default).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("marvin.harness_creds")

CODE_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4,})\b")
URL_RE = re.compile(r"https://[^\s]+")


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    env_var: str
    harnesses: tuple[str, ...]
    console_url: str
    steps: tuple[str, ...]
    key_prefix: str = ""
    note: str = ""
    subscription: str | None = None  # "grok" = device-code login via the grok CLI


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        id="anthropic", label="Anthropic (Claude)", env_var="ANTHROPIC_API_KEY",
        harnesses=("claude-code", "claude-acp"), key_prefix="sk-ant-",
        console_url="https://console.anthropic.com/settings/keys",
        steps=(
            "Open console.anthropic.com → API keys.",
            "Create Key and copy the sk-ant-… string.",
            "Paste it here.",
        ),
        note="A room other people can reach cannot use a Claude Pro/Max login. Use an API key (or commercial credentials).",
    ),
    Provider(
        id="xai", label="xAI (Grok)", env_var="XAI_API_KEY",
        harnesses=("grok",), key_prefix="xai-",
        console_url="https://console.x.ai/team/default/api-keys",
        steps=(
            "Open console.x.ai → API Keys.",
            "Create an API key and copy the xai-… string.",
            "Paste it here.",
        ),
        note="An API key is billed at xAI API rates. Sign in with Grok uses your grok.com subscription instead.",
        subscription="grok",
    ),
    Provider(
        id="openai", label="OpenAI (Codex)", env_var="OPENAI_API_KEY",
        harnesses=("codex",), key_prefix="sk-",
        console_url="https://platform.openai.com/api-keys",
        steps=(
            "Open platform.openai.com → API keys.",
            "Create a new secret key.",
            "Paste it here.",
        ),
    ),
    Provider(
        id="google", label="Google (Gemini)", env_var="GEMINI_API_KEY",
        harnesses=("gemini",),
        console_url="https://aistudio.google.com/apikey",
        steps=(
            "Open aistudio.google.com/apikey.",
            "Create API key and copy it.",
            "Paste it here.",
        ),
    ),
    Provider(
        id="cursor", label="Cursor", env_var="CURSOR_API_KEY",
        harnesses=("cursor",),
        console_url="https://cursor.com/dashboard",
        steps=(
            "Open cursor.com/dashboard → Integrations (or Settings → API).",
            "Create a user API key.",
            "Paste it here.",
        ),
    ),
    Provider(
        id="copilot", label="GitHub Copilot", env_var="COPILOT_GITHUB_TOKEN",
        harnesses=("copilot",),
        console_url="https://github.com/settings/tokens",
        steps=(
            "Open github.com/settings/tokens and create a token for an account that has Copilot.",
            "Paste it here.",
        ),
        note="The account must have an active Copilot subscription.",
    ),
)
_BY_ID = {p.id: p for p in PROVIDERS}


def _operator_harness_override() -> str | None:
    """MARVIN_HARNESS as a seed, not a lock. Restating the built-in default does nothing."""
    from marvin.adapters import registry
    raw = os.environ.get("MARVIN_HARNESS", "").strip() or None
    if not raw or raw == registry.DEFAULT_HARNESS:
        return None
    return raw


def get_provider(pid: str) -> Provider:
    try:
        return _BY_ID[pid]
    except KeyError:
        raise KeyError(f"unknown provider {pid!r}; known: {', '.join(_BY_ID)}") from None


def _clean_key(raw: str, prefix: str) -> str:
    key = (raw or "").strip()
    if not key or any(c.isspace() for c in key):
        raise ValueError("paste the key itself, not a sentence")
    if len(key) < 12:
        raise ValueError("that is too short to be an API key")
    if prefix == "sk-" and key.startswith("sk-ant-"):
        raise ValueError("that looks like an Anthropic key; paste it under Anthropic")
    if prefix and not key.startswith(prefix):
        raise ValueError(f"this key should start with {prefix}")
    return key


def _hint(secret: str) -> str:
    if len(secret) <= 8:
        return "•" * len(secret)
    return secret[:4] + "•" * min(12, len(secret) - 8) + secret[-4:]


def parse_device_output(text: str) -> tuple[str | None, str | None]:
    """Best-effort user_code and verification URL from `grok login --device-auth` stdout/stderr."""
    url = None
    for m in URL_RE.finditer(text):
        cand = m.group(0).rstrip(").,;\"'")
        if "http" in cand:
            url = cand
            break
    code = None
    labeled = re.search(r"(?:enter\s+)?(?:the\s+)?(?:code|user[_\s-]?code)\s*[:=]\s*([A-Z0-9-]{4,})", text, re.I)
    if labeled:
        code = labeled.group(1)
    elif (m := CODE_RE.search(text)):
        code = m.group(1)
    return code, url


class HarnessCreds:
    """<state_dir>/harness.json. Stored Settings win for the default harness; env seeds when unset."""

    def __init__(self, state_dir: str | None, secret: str, *, runner: Callable[..., asyncio.Task] | None = None) -> None:
        self.path = Path(state_dir) / "harness.json" if state_dir else None
        self.state_dir = Path(state_dir) if state_dir else None
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("marvin-harness:" + secret).encode()).digest()))
        self._data: dict = self._load()
        self._env_default = _operator_harness_override()
        self._we_set_harness = False
        self._runner = runner  # tests inject a fake grok login
        self._flows: dict[str, GrokFlow] = {}
        self.on_grok_session: Callable[[], None] | None = None  # RoomManager reloads grok rooms
        self.activate()
        self._adopt_only_connected(only_if_unset=True)

    def _load(self) -> dict:
        if not self.path or not self.path.exists():
            return {"keys": {}, "sessions": {}, "settings": {}}
        try:
            data = json.loads(self.path.read_text())
            data.setdefault("keys", {})
            data.setdefault("sessions", {})
            data.setdefault("settings", {})
            return data
        except Exception:
            log.exception("could not read %s", self.path)
            return {"keys": {}, "sessions": {}, "settings": {}}

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def _encrypt(self, text: str) -> str:
        return self._fernet.encrypt(text.encode()).decode()

    def _decrypt(self, blob: str) -> str | None:
        try:
            return self._fernet.decrypt(blob.encode()).decode()
        except (InvalidToken, Exception):
            return None

    # -- keys -------------------------------------------------------------------
    def get_key(self, pid: str) -> str | None:
        rec = self._data["keys"].get(pid)
        if not rec:
            return None
        val = self._decrypt(rec.get("enc", ""))
        if val is None:
            log.warning("harness key %s cannot be decrypted (session secret changed?); dropping it", pid)
            self._data["keys"].pop(pid, None)
            self._save()
        return val

    def put_key(self, pid: str, raw: str) -> None:
        p = get_provider(pid)
        key = _clean_key(raw, p.key_prefix)
        self._data["keys"][pid] = {"enc": self._encrypt(key), "set_at": time.time()}
        self._save()
        self.activate()
        self._adopt_only_connected()

    def forget_key(self, pid: str) -> None:
        get_provider(pid)
        if self._data["keys"].pop(pid, None) is not None:
            self._save()
        env = get_provider(pid).env_var
        stored_now = self.get_key(pid)
        if not stored_now and os.environ.get(env) and env in getattr(self, "_we_set_env", set()):
            os.environ.pop(env, None)
            self._we_set_env.discard(env)
        self._release_default_if_unconnected()

    # -- grok session -----------------------------------------------------------
    def grok_auth_json(self) -> str | None:
        rec = self._data["sessions"].get("grok")
        if not rec:
            return None
        val = self._decrypt(rec.get("enc", ""))
        if val is None:
            log.warning("grok session cannot be decrypted; dropping it")
            self._data["sessions"].pop("grok", None)
            self._save()
        return val

    def put_grok_session(self, auth_json: str) -> None:
        json.loads(auth_json)  # must be JSON
        self._data["sessions"]["grok"] = {"enc": self._encrypt(auth_json), "set_at": time.time()}
        self._save()
        self.activate()
        self.install_all_homes()
        self._adopt_only_connected()
        if self.on_grok_session:
            try:
                self.on_grok_session()
            except Exception:
                log.exception("on_grok_session")

    def forget_grok_session(self) -> None:
        if self._data["sessions"].pop("grok", None) is not None:
            self._save()
            self.install_all_homes()
        self._release_default_if_unconnected()

    def set_default_harness(self, hid: str | None) -> None:
        from marvin.adapters import registry
        if hid:
            if hid not in registry.ids():
                raise ValueError(f"unknown harness {hid!r}")
            self._data["settings"]["default_harness"] = hid
        else:
            self._data["settings"].pop("default_harness", None)
        self._save()
        self.activate()

    def _provider_connected(self, p: Provider) -> bool:
        if p.subscription == "grok" and self.grok_auth_json():
            return True
        if self.get_key(p.id):
            return True
        env_val = os.environ.get(p.env_var, "").strip()
        we = getattr(self, "_we_set_env", set())
        return bool(env_val and p.env_var not in we)

    def _connected_providers(self) -> list[Provider]:
        return [p for p in PROVIDERS if self._provider_connected(p)]

    def _adopt_only_connected(self, *, only_if_unset: bool = False) -> None:
        """If exactly one provider is connected, rooms should use it."""
        connected = self._connected_providers()
        if len(connected) != 1:
            return
        hid = connected[0].harnesses[0]
        stored = (self._data.get("settings") or {}).get("default_harness")
        if stored == hid:
            return
        if only_if_unset and stored:
            return
        self.set_default_harness(hid)

    def _release_default_if_unconnected(self) -> None:
        stored = (self._data.get("settings") or {}).get("default_harness")
        if not stored:
            return
        connected = self._connected_providers()
        covered = {h for p in connected for h in p.harnesses}
        if stored in covered:
            return
        if len(connected) == 1:
            self.set_default_harness(connected[0].harnesses[0])
        else:
            self.set_default_harness(None)

    # -- what the rest of Marvin sees ------------------------------------------
    def env(self) -> dict[str, str]:
        """Keys to merge into a harness process. Operator-set environment variables win; keys we pushed into
        os.environ ourselves still count as stored."""
        out: dict[str, str] = {}
        we = getattr(self, "_we_set_env", set())
        for p in PROVIDERS:
            env_val = os.environ.get(p.env_var, "").strip()
            if env_val and p.env_var not in we:
                continue
            if key := self.get_key(p.id):
                out[p.env_var] = key
        return out

    def install_home(self, home: Path) -> None:
        """Write ~/.grok/auth.json into a room HOME so `grok` sees the subscription session."""
        blob = self.grok_auth_json()
        dest = home / ".grok" / "auth.json"
        if not blob:
            if dest.exists():
                dest.unlink()
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(blob)
        dest.chmod(0o600)

    def install_all_homes(self) -> None:
        if not self.state_dir:
            return
        root = self.state_dir / "sandbox"
        if root.is_dir():
            for home in root.glob("*/home"):
                self.install_home(home)

    def activate(self) -> None:
        """Push stored keys into os.environ (gaps only) and honour the stored default harness."""
        self._we_set_env = getattr(self, "_we_set_env", set())
        for k, v in self.env().items():
            if not os.environ.get(k, "").strip():
                os.environ[k] = v
                self._we_set_env.add(k)
        stored = (self._data.get("settings") or {}).get("default_harness")
        if stored:
            os.environ["MARVIN_HARNESS"] = stored
            self._we_set_harness = True
        elif self._env_default:
            os.environ["MARVIN_HARNESS"] = self._env_default
            self._we_set_harness = False
        elif self._we_set_harness:
            os.environ.pop("MARVIN_HARNESS", None)
            self._we_set_harness = False

    def status(self) -> dict:
        providers = []
        for p in PROVIDERS:
            env_val = os.environ.get(p.env_var, "").strip()
            stored = self.get_key(p.id)
            if env_val and p.env_var not in getattr(self, "_we_set_env", set()):
                source, hint = "env", _hint(env_val)
            elif stored:
                source, hint = "settings", _hint(stored)
            else:
                source, hint = None, None
            rec: dict = {
                "id": p.id, "label": p.label, "env": p.env_var, "harnesses": list(p.harnesses),
                "console_url": p.console_url, "steps": list(p.steps), "key_prefix": p.key_prefix,
                "note": p.note, "subscription": p.subscription,
                "key_set": bool(source), "key_source": source, "key_hint": hint,
                "subscription_set": False,
            }
            if p.subscription == "grok":
                rec["subscription_set"] = bool(self.grok_auth_json())
            providers.append(rec)
        from marvin.adapters import registry
        stored = (self._data.get("settings") or {}).get("default_harness")
        if stored:
            default, default_source = stored, "settings"
        elif self._env_default:
            default, default_source = self._env_default, "env"
        else:
            default, default_source = registry.DEFAULT_HARNESS, "builtin"
        return {
            "providers": providers,
            "default_harness": default,
            "default_source": default_source,
            "harnesses": [x.to_wire() for x in registry.profiles()],
        }

    def ready(self) -> dict:
        """Whether the machine can talk to an agent. No secrets. Join waits on this."""
        st = self.status()
        chosen = next((p for p in st["providers"] if p["id"] == "xai" and (p["key_set"] or p["subscription_set"])), None)
        if not chosen:
            chosen = next((p for p in st["providers"] if p["key_set"] or p["subscription_set"]), None)
        return {
            "ready": bool(chosen),
            "label": chosen["label"] if chosen else None,
            "default_harness": st["default_harness"],
        }

    # -- grok device login ------------------------------------------------------
    async def start_grok_login(self) -> GrokFlow:
        for f in list(self._flows.values()):
            await f.cancel()
        self._flows.clear()
        flow = GrokFlow(self)
        self._flows[flow.id] = flow
        flow.task = asyncio.create_task(flow.run())
        try:
            await asyncio.wait_for(flow.ready.wait(), timeout=45)
        except TimeoutError:
            await flow.cancel()
            raise RuntimeError(
                "Grok CLI did not print a login code. Is `grok` on PATH, or was the sandbox image built with grok "
                "(`make sandbox-image SANDBOX_HARNESSES=\"claude-code grok\"`)?"
            ) from None
        if flow.status == "error":
            raise RuntimeError(flow.error or "grok login failed")
        return flow

    def get_flow(self, flow_id: str) -> GrokFlow | None:
        return self._flows.get(flow_id)


@dataclass
class GrokFlow:
    creds: HarnessCreds
    id: str = ""
    user_code: str = ""
    verification_uri: str = "https://accounts.x.ai/device"
    expires_at: float = 0.0
    status: str = "pending"  # pending | connected | error
    error: str | None = None
    ready: asyncio.Event = None  # type: ignore[assignment]
    task: asyncio.Task | None = None
    _proc: asyncio.subprocess.Process | None = None
    _home: Path | None = None

    def __post_init__(self) -> None:
        import uuid
        self.id = uuid.uuid4().hex[:12]
        self.ready = asyncio.Event()
        self.expires_at = time.time() + 15 * 60

    def public(self) -> dict:
        return {
            "flow": self.id,
            "user_code": self.user_code,
            "verification_uri": self.verification_uri,
            "expires_in": max(0, int(self.expires_at - time.time())),
            "status": self.status,
            "error": self.error,
        }

    async def run(self) -> None:
        home = (self.creds.state_dir / "grok-login" / self.id) if self.creds.state_dir else Path(f"/tmp/marvin-grok-{self.id}")
        home.mkdir(parents=True, exist_ok=True)
        self._home = home
        try:
            if self.creds._runner:
                await self.creds._runner(self, home)
                return
            await self._run_cli(home)
        except asyncio.CancelledError:
            self.status = "error"
            self.error = "cancelled"
            self.ready.set()
            raise
        except Exception as e:
            log.exception("grok login")
            self.status = "error"
            self.error = str(e)
            self.ready.set()

    async def _run_cli(self, home: Path) -> None:
        env = {**os.environ, "HOME": str(home), "GROK_HOME": str(home / ".grok")}
        cmd = _grok_login_cmd(home)
        log.info("grok login: %s", " ".join(cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env,
        )
        buf = ""
        assert self._proc.stdout
        while True:
            if time.time() > self.expires_at:
                self.status = "error"
                self.error = "login timed out"
                self.ready.set()
                self._kill()
                return
            chunk = b""
            if self._proc.returncode is None:
                try:
                    chunk = await asyncio.wait_for(self._proc.stdout.read(256), timeout=2.0)
                except TimeoutError:
                    chunk = b""
            if chunk:
                buf += chunk.decode("utf-8", "replace")
                code, url = parse_device_output(buf)
                if code and not self.user_code:
                    self.user_code = code
                    if url:
                        self.verification_uri = url
                    self.ready.set()
            auth = home / ".grok" / "auth.json"
            if auth.exists() and auth.stat().st_size > 2:
                self.creds.put_grok_session(auth.read_text())
                self.status = "connected"
                self.ready.set()
                self._kill()
                return
            if self._proc.returncode is not None:
                if auth.exists() and auth.stat().st_size > 2:
                    self.creds.put_grok_session(auth.read_text())
                    self.status = "connected"
                    self.ready.set()
                    return
                self.status = "error"
                self.error = (buf.strip() or f"grok login exited {self._proc.returncode}")[:400]
                self.ready.set()
                return
            if not chunk:
                await asyncio.sleep(0.4)

    def _kill(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()

    async def cancel(self) -> None:
        self._kill()
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
        self.status = "error"
        self.error = "cancelled"
        self.ready.set()


def _work_volume() -> str:
    """Host volume name that is /work inside the worker (MARVIN_SANDBOX_MOUNTS). The Docker daemon sees
    host paths, so we must mount this volume, not the worker-container path /work/state/..."""
    first = (os.environ.get("MARVIN_SANDBOX_MOUNTS") or "marvin_work:/work").split(",")[0].strip()
    return first.split(":")[0] or "marvin_work"


def _grok_login_cmd(home: Path) -> list[str]:
    if shutil.which("grok"):
        return ["grok", "login", "--device-auth"]
    docker = shutil.which("docker")
    image = os.environ.get("MARVIN_SANDBOX_IMAGE", "marvin-sandbox:local")
    if docker:
        return [
            docker, "run", "--rm", "-i",
            "-v", f"{_work_volume()}:/work",
            "-e", f"HOME={home}",
            "-e", f"GROK_HOME={home / '.grok'}",
            "-w", str(home),
            image, "grok", "login", "--device-auth",
        ]
    raise RuntimeError(
        "Grok CLI is not on this machine. Rebuild the sandbox image including grok: "
        'make sandbox-image SANDBOX_HARNESSES="claude-code grok"'
    )
