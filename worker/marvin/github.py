"""Connect GitHub from the browser: per-user tokens through GitHub's device flow, handed to git and gh per turn.

Flow (Settings -> Account -> Connect GitHub): the worker asks GitHub for a device code, the UI shows the 8-character
user code and a link to github.com/login/device, the worker polls until the person approves, then stores the user
token encrypted under their Marvin identity. No client secret is involved (device flow), so the only configuration
is the public client id of an OAuth App with "Device flow" enabled: MARVIN_GITHUB_CLIENT_ID.

Per turn, the conductor asks `GitIdentity.apply(room, requester)` and the room's git and gh see that person's
identity: `GIT_CONFIG_GLOBAL` points at a per-room gitconfig (user.name/email, a credential helper that reads a
token file), `GH_CONFIG_DIR` at a per-room gh config (hosts.yml with the token). Both files live in the room's
directory under the state dir, which in sandbox mode is mounted into the container at the same path. When the
requester has not connected, the machine identity (GITHUB_TOKEN, MARVIN_GIT_NAME/EMAIL) is used; when neither
exists, the files carry no credentials and git falls back to the system's helpers (the operator's keychain in dev).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("marvin.github")

DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
API = "https://api.github.com"
SCOPES = "repo read:org workflow"  # what `gh auth login` asks for, minus gist


@dataclass(frozen=True)
class Connection:
    login: str
    name: str
    email: str
    token: str
    scopes: str = ""
    connected_at: float = 0.0

    def public(self) -> dict[str, Any]:
        return {"login": self.login, "name": self.name, "email": self.email, "scopes": self.scopes, "connected_at": self.connected_at}


class TokenStore:
    """<state_dir>/github.json: {"users": {marvin_user_id: {login, name, email, token_enc, ...}}}. Tokens are Fernet-
    encrypted with a key derived from the session secret, so a copied state directory is not a copied credential."""

    def __init__(self, state_dir: str | None, secret: str) -> None:
        self.path = Path(state_dir) / "github.json" if state_dir else None
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("marvin-github:" + secret).encode()).digest()))
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path or not self.path.exists():
            return {"users": {}}
        try:
            data = json.loads(self.path.read_text())
            data.setdefault("users", {})
            return data
        except Exception:
            log.exception("could not read %s", self.path)
            return {"users": {}}

    # Machine-wide settings that live next to the tokens (plain: the client id is a public identifier).
    def get_setting(self, key: str) -> str | None:
        return self._data.get("settings", {}).get(key) or None

    def set_setting(self, key: str, value: str | None) -> None:
        settings = self._data.setdefault("settings", {})
        if value:
            settings[key] = value
        else:
            settings.pop(key, None)
        self._save()

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def get(self, user_id: str) -> Connection | None:
        rec = self._data["users"].get(user_id)
        if not rec:
            return None
        try:
            token = self._fernet.decrypt(rec["token_enc"].encode()).decode()
        except (InvalidToken, KeyError):
            log.warning("github token for %s cannot be decrypted (session secret changed?); dropping it", user_id)
            self.forget(user_id)
            return None
        return Connection(login=rec["login"], name=rec["name"], email=rec["email"], token=token, scopes=rec.get("scopes", ""), connected_at=rec.get("connected_at", 0.0))

    def put(self, user_id: str, conn: Connection) -> None:
        self._data["users"][user_id] = {**conn.public(), "token_enc": self._fernet.encrypt(conn.token.encode()).decode()}
        self._save()

    def forget(self, user_id: str) -> None:
        if self._data["users"].pop(user_id, None) is not None:
            self._save()


@dataclass
class Flow:
    id: str
    user_id: str
    device_code: str
    user_code: str
    verification_uri: str
    expires_at: float
    interval: float
    status: str = "pending"  # pending | connected | error
    error: str | None = None
    connection: Connection | None = None
    task: asyncio.Task | None = None


class GitHubConnect:
    """Device-flow sessions plus the token store. One instance per worker."""

    def __init__(self, store: TokenStore, *, client_id: str | None = None, http: httpx.AsyncClient | None = None) -> None:
        self.store = store
        # The OAuth App's client id: set by an admin in Settings (stored with the tokens) or, as an override, in the
        # environment. It is a public identifier, not a secret.
        self.env_client_id = client_id or os.environ.get("MARVIN_GITHUB_CLIENT_ID", "").strip() or None
        self.http = http or httpx.AsyncClient(timeout=20, headers={"Accept": "application/json", "User-Agent": "marvin"})
        self.flows: dict[str, Flow] = {}
        self.machine_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or None
        self._repo_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    @property
    def client_id(self) -> str | None:
        return self.env_client_id or self.store.get_setting("client_id")

    @property
    def client_id_source(self) -> str | None:
        return "env" if self.env_client_id else ("settings" if self.store.get_setting("client_id") else None)

    def set_client_id(self, value: str | None) -> None:
        value = (value or "").strip()
        if value and not re.fullmatch(r"[A-Za-z0-9._-]{8,80}", value):
            raise ValueError("that does not look like a GitHub client id (e.g. Ov23li… or Iv1.…)")
        self.store.set_setting("client_id", value or None)

    @property
    def configured(self) -> bool:
        return bool(self.client_id)

    def status(self, user_id: str, *, admin: bool = False) -> dict[str, Any]:
        conn = self.store.get(user_id)
        out: dict[str, Any] = {"configured": self.configured, "connected": conn.public() if conn else None, "machine_identity": bool(self.machine_token)}
        if admin:
            cid = self.client_id
            out["client_id"] = cid  # admins may see it; it is public anyway (the UI masks it by default)
            out["client_id_source"] = self.client_id_source
        return out

    async def start(self, user_id: str) -> Flow:
        if not self.client_id:
            raise RuntimeError("GitHub connection is not configured on this machine: set MARVIN_GITHUB_CLIENT_ID (see docs_and_changelog/github.md)")
        r = await self.http.post(DEVICE_CODE_URL, data={"client_id": self.client_id, "scope": SCOPES})
        try:
            d = r.json() if r.content else {}
        except ValueError:
            d = {}
        if "device_code" not in d:
            err = d.get("error", "")
            if err == "device_flow_disabled":
                raise RuntimeError("Device Flow is not enabled on that OAuth App. On GitHub: Settings → Developer settings → OAuth Apps → your app → tick “Enable Device Flow” → Update application. Then try again; the client id stays as it is.")
            if r.status_code == 404 or err in ("Not Found", "unauthorized_client"):
                raise RuntimeError("GitHub does not know this client id. Check it against the OAuth App page (Settings → Developer settings → OAuth Apps) and save it again.")
            raise RuntimeError(f"GitHub device code request failed: {d.get('error_description') or err or f'HTTP {r.status_code}'}")
        flow = Flow(
            id=secrets.token_urlsafe(12), user_id=user_id, device_code=d["device_code"], user_code=d["user_code"],
            verification_uri=d.get("verification_uri", "https://github.com/login/device"),
            expires_at=time.time() + float(d.get("expires_in", 900)), interval=float(d.get("interval", 5)),
        )
        # One live flow per user: starting again cancels the previous one.
        for old in [f for f in self.flows.values() if f.user_id == user_id and f.status == "pending"]:
            if old.task:
                old.task.cancel()
            self.flows.pop(old.id, None)
        self.flows[flow.id] = flow
        flow.task = asyncio.create_task(self._poll(flow), name=f"github-device-{flow.id}")
        log.info("github: device flow started for %s (code %s)", user_id, flow.user_code)
        return flow

    def get_flow(self, flow_id: str, user_id: str) -> Flow | None:
        f = self.flows.get(flow_id)
        return f if f and f.user_id == user_id else None

    async def _poll(self, flow: Flow) -> None:
        interval = flow.interval
        try:
            while time.time() < flow.expires_at:
                await asyncio.sleep(interval)
                r = await self.http.post(TOKEN_URL, data={"client_id": self.client_id, "device_code": flow.device_code, "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
                d = r.json() if r.content else {}
                if token := d.get("access_token"):
                    conn = await self._whoami(token, scopes=d.get("scope", ""))
                    self.store.put(flow.user_id, conn)
                    flow.connection, flow.status = conn, "connected"
                    log.info("github: %s connected as @%s", flow.user_id, conn.login)
                    return
                err = d.get("error")
                if err == "authorization_pending":
                    continue
                if err == "slow_down":
                    interval = float(d.get("interval", interval + 5))
                    continue
                flow.status, flow.error = "error", {"expired_token": "the code expired; start again", "access_denied": "you declined the request on GitHub"}.get(err, d.get("error_description") or err or f"HTTP {r.status_code}")
                return
            flow.status, flow.error = "error", "the code expired; start again"
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("github device flow")
            flow.status, flow.error = "error", f"{type(e).__name__}: {e}"

    async def _whoami(self, token: str, *, scopes: str = "") -> Connection:
        h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        r = await self.http.get(f"{API}/user", headers=h)
        r.raise_for_status()
        u = r.json()
        email = u.get("email") or ""
        if not email:
            # Private e-mail: ask for the primary, fall back to GitHub's noreply address (what GitHub itself uses).
            try:
                r2 = await self.http.get(f"{API}/user/emails", headers=h)
                if r2.status_code == 200:
                    email = next((e["email"] for e in r2.json() if e.get("primary") and e.get("verified")), "")
            except Exception:
                pass
        if not email:
            email = f"{u['id']}+{u['login']}@users.noreply.github.com"
        return Connection(login=u["login"], name=u.get("name") or u["login"], email=email, token=token, scopes=scopes, connected_at=time.time())

    async def verify(self, user_id: str) -> Connection | None:
        """Re-check a stored token against GitHub; forget it if it was revoked."""
        conn = self.store.get(user_id)
        if not conn:
            return None
        r = await self.http.get(f"{API}/user", headers={"Authorization": f"Bearer {conn.token}"})
        if r.status_code == 401:
            log.info("github: token for %s was revoked; forgetting it", user_id)
            self.store.forget(user_id)
            return None
        return conn

    def disconnect(self, user_id: str) -> None:
        self.store.forget(user_id)

    def token_for(self, user_id: str | None) -> str | None:
        """The token to act with for this person: their connected account, else the machine's."""
        conn = self.store.get(user_id) if user_id else None
        return conn.token if conn else self.machine_token

    async def list_repos(self, user_id: str | None, *, query: str = "", limit: int = 300) -> list[dict[str, Any]]:
        """Repositories the person's account can see (owner, collaborator, org member), most recently pushed first.
        Cached for a minute per token. `query` filters on full name / description, case-insensitively."""
        token = self.token_for(user_id)
        if not token:
            raise LookupError("connect GitHub first (Settings -> GitHub), or set GITHUB_TOKEN on the machine")
        key = hashlib.sha256(token.encode()).hexdigest()[:16]
        cached = self._repo_cache.get(key)
        if cached and time.time() - cached[0] < 60:
            repos = cached[1]
        else:
            repos = []
            h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
            page = 1
            while len(repos) < limit:
                r = await self.http.get(f"{API}/user/repos", headers=h, params={"per_page": 100, "page": page, "sort": "pushed", "affiliation": "owner,collaborator,organization_member"})
                if r.status_code == 401:
                    if user_id and self.store.get(user_id):
                        self.store.forget(user_id)
                    raise LookupError("GitHub rejected the token; connect again")
                r.raise_for_status()
                batch = r.json()
                repos += [
                    {"full_name": x["full_name"], "html_url": x["html_url"], "clone_url": x["clone_url"], "default_branch": x.get("default_branch") or "main",
                     "private": bool(x.get("private")), "pushed_at": x.get("pushed_at"), "description": x.get("description") or "", "language": x.get("language") or ""}
                    for x in batch
                ]
                if len(batch) < 100:
                    break
                page += 1
            self._repo_cache[key] = (time.time(), repos)
        if query:
            q = query.lower()
            repos = [x for x in repos if q in x["full_name"].lower() or q in x["description"].lower()]
        return repos

    async def aclose(self) -> None:
        for f in self.flows.values():
            if f.task:
                f.task.cancel()
        await self.http.aclose()


class GitIdentity:
    """Per-room git/gh identity files. `env(room)` goes into the harness environment once; `apply(room, requester)`
    rewrites the files at every turn start."""

    def __init__(self, state_dir: str | None, connect: GitHubConnect | None) -> None:
        self.state_dir = Path(state_dir) if state_dir else None
        self.connect = connect

    def room_dir(self, room: str) -> Path | None:
        # Same directory the sandbox mounts as the room's HOME, so the paths are identical inside the container.
        return self.state_dir / "sandbox" / room / "home" / ".marvin" if self.state_dir else None

    def env(self, room: str) -> dict[str, str]:
        d = self.room_dir(room)
        if d is None:
            return {}
        d.mkdir(parents=True, exist_ok=True)
        return {"GIT_CONFIG_GLOBAL": str(d / "gitconfig"), "GH_CONFIG_DIR": str(d / "gh")}

    def resolve(self, user_id: str | None) -> Connection | None:
        return self.connect.store.get(user_id) if (self.connect and user_id) else None

    def apply(self, room: str, user_id: str | None) -> str:
        """Write the room's identity for this turn. Returns a short description for the log."""
        d = self.room_dir(room)
        if d is None:
            return "no state dir"
        d.mkdir(parents=True, exist_ok=True)
        conn = self.resolve(user_id)
        if conn:
            name, email, token, who = conn.name, conn.email, conn.token, f"@{conn.login} ({user_id})"
        else:
            token = self.connect.machine_token if self.connect else None
            name, email = os.environ.get("MARVIN_GIT_NAME", "Marvin"), os.environ.get("MARVIN_GIT_EMAIL", "marvin@example.com")
            who = "machine identity" if token else "no GitHub credentials (system git helpers apply)"
        token_file = d / "token"
        gitconfig = [
            "# written by Marvin at every turn: the identity of the person who asked (or the machine's)",
            "[include]", "\tpath = ~/.gitconfig",  # keep the operator's/room HOME's own settings underneath ours
            "[init]", "\tdefaultBranch = main",
            "[safe]", "\tdirectory = *",
        ]
        if token:
            # Only when Marvin supplies the credentials does it also set the author; otherwise the included config's
            # identity applies (the operator's own on a dev machine, the sandbox init's in a container).
            _write_private(token_file, token + "\n")
            gitconfig += [
                "[user]", f"\tname = {name}", f"\temail = {email}",
                "[credential]",
                "\thelper =",  # empty value resets the helper list: the included config's keychain must not answer first
                f"\thelper = \"!f() {{ echo username=x-access-token; echo password=$(cat {token_file}); }}; f\"",
                '[url "https://github.com/"]', "\tinsteadOf = git@github.com:",
            ]
            gh = d / "gh"
            gh.mkdir(exist_ok=True)
            _write_private(gh / "hosts.yml", f"github.com:\n    oauth_token: {token}\n    user: {conn.login if conn else 'marvin'}\n    git_protocol: https\n")
        else:
            token_file.unlink(missing_ok=True)
            (d / "gh" / "hosts.yml").unlink(missing_ok=True)
        _write_private(d / "gitconfig", "\n".join(gitconfig) + "\n")
        return who


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.chmod(0o600)
    tmp.replace(path)
