"""Who is calling the token server and what they may do. Three modes, picked by MARVIN_AUTH:

- header:   an identity-aware proxy (oauth2-proxy behind Caddy, an OIDC ingress) already authenticated the user and
            sets X-Forwarded-User/-Email/-Preferred-Username/-Groups. Trusted only from MARVIN_TRUSTED_PROXIES.
- password: Marvin's own login (POST /api/login) against MARVIN_ROOM_PASSWORD / MARVIN_ADMIN_PASSWORD, kept in a
            signed HttpOnly cookie.
- none:     dev only: the name typed on the join screen, everyone is admin. Refuses to bind anything but loopback.

Design and threat model: docs_and_changelog/authentication.md.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import time
from collections import deque
from dataclasses import dataclass

from aiohttp import web

from marvin.room.protocol import AGENT_IDENTITY

log = logging.getLogger("marvin.auth")

PARTICIPANT = "participant"
ADMIN = "admin"
MODES = ("header", "password", "none")
COOKIE = "marvin_session"
DEFAULT_TRUSTED_PROXIES = "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
FAILS_PER_MINUTE = 10  # password mode: failed logins per client IP before 429

HDR_USER, HDR_EMAIL, HDR_NAME, HDR_GROUPS = "X-Forwarded-User", "X-Forwarded-Email", "X-Forwarded-Preferred-Username", "X-Forwarded-Groups"


@dataclass(frozen=True)
class Identity:
    id: str  # stable, slug-safe, unique per user: becomes the LiveKit participant identity
    name: str  # display name
    email: str | None = None
    roles: frozenset[str] = frozenset({PARTICIPANT})

    @property
    def is_admin(self) -> bool:
        return ADMIN in self.roles

    def to_wire(self) -> dict:
        return {"id": self.id, "name": self.name, "email": self.email, "roles": sorted(self.roles)}


def slug(name: str) -> str:
    """LiveKit identity from a free-form name; never the agent's own identity."""
    s = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-") or "guest"
    return "human-" + s if s == AGENT_IDENTITY else s


def _csv(value: str | None, *, lower: bool = True) -> frozenset[str]:
    items = (v.strip() for v in (value or "").split(","))
    return frozenset((v.lower() if lower else v) for v in items if v)


def _networks(value: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return tuple(ipaddress.ip_network(cidr.strip(), strict=False) for cidr in value.split(",") if cidr.strip())


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Auth:
    """Mode + settings, built once from the environment (`Auth.from_env()`); stored on the aiohttp app as app["auth"]."""

    fail_delay = 0.5  # seconds a wrong password costs; tests set 0

    def __init__(
        self,
        mode: str,
        *,
        trusted_proxies: str = DEFAULT_TRUSTED_PROXIES,
        admin_groups: str = "",
        admin_users: str = "",
        room_password: str = "",
        admin_password: str = "",
        session_secret: str = "",
        session_hours: float = 12,
        insecure_ok: bool = False,
    ) -> None:
        if mode not in MODES:
            raise SystemExit(f"MARVIN_AUTH={mode!r}: expected one of {', '.join(MODES)}")
        self.mode = mode
        self.trusted = _networks(trusted_proxies)
        self.admin_groups = _csv(admin_groups)
        self.admin_users = _csv(admin_users)
        self.room_password = room_password
        self.admin_password = admin_password
        self.secret = session_secret.encode()
        self.session_seconds = int(session_hours * 3600)
        self.insecure_ok = insecure_ok
        self._fails: dict[str, deque[float]] = {}
        self._warned_untrusted = False
        if mode == "password" and not room_password:
            raise SystemExit("MARVIN_AUTH=password needs MARVIN_ROOM_PASSWORD")
        if mode == "password" and not self.secret:
            raise SystemExit("MARVIN_AUTH=password needs MARVIN_SESSION_SECRET (or LIVEKIT_API_SECRET) to sign the session cookie")

    @classmethod
    def from_env(cls, env=os.environ) -> "Auth":
        mode = env.get("MARVIN_AUTH", "").strip().lower()
        if not mode:
            if env.get("MARVIN_ROOM_PASSWORD"):
                mode = "password"
            else:
                raise SystemExit(
                    "MARVIN_AUTH is not set. Options: MARVIN_AUTH=password (set MARVIN_ROOM_PASSWORD, optionally "
                    "MARVIN_ADMIN_PASSWORD), MARVIN_AUTH=header (behind Caddy + oauth2-proxy or an OIDC ingress, "
                    "see deploy/caddy), or MARVIN_AUTH=none (localhost dev only). See docs_and_changelog/authentication.md."
                )
        return cls(
            mode,
            trusted_proxies=env.get("MARVIN_TRUSTED_PROXIES", DEFAULT_TRUSTED_PROXIES),
            admin_groups=env.get("MARVIN_ADMIN_GROUPS", ""),
            admin_users=env.get("MARVIN_ADMIN_USERS", ""),
            room_password=env.get("MARVIN_ROOM_PASSWORD", ""),
            admin_password=env.get("MARVIN_ADMIN_PASSWORD", ""),
            session_secret=env.get("MARVIN_SESSION_SECRET") or env.get("LIVEKIT_API_SECRET", ""),
            session_hours=float(env.get("MARVIN_SESSION_HOURS", "12")),
            insecure_ok=env.get("MARVIN_AUTH_INSECURE_OK", "").lower() in ("1", "true", "yes"),
        )

    def check_startup(self, host: str) -> None:
        """Called by main() with the bind address. `none` mode must not be reachable from other machines."""
        if self.mode == "password" and self.secret == b"secret":
            log.warning("session cookies are signed with the LiveKit dev secret; set MARVIN_SESSION_SECRET")
        if self.mode != "none":
            return
        loopback = host in ("127.0.0.1", "::1", "localhost")
        if not loopback and not self.insecure_ok:
            raise SystemExit(
                f"MARVIN_AUTH=none with MARVIN_TOKEN_HOST={host}: anyone who can reach this port can be anyone and is admin. "
                "Bind to 127.0.0.1, or set MARVIN_AUTH_INSECURE_OK=1 if you really mean it (e.g. a dev VM behind a VPN)."
            )
        log.warning("MARVIN_AUTH=none: identities are self-asserted and everyone is admin. Local development only.")

    # -- per request -----------------------------------------------------------------
    def identity_from_request(self, req: web.Request) -> Identity | None:
        if self.mode == "header":
            return self._from_headers(req)
        if self.mode == "password":
            return self.read_session(req.cookies.get(COOKIE, ""))
        # none: whatever the client says, admin included
        name = req.query.get("name", "").strip() or "dev"
        return Identity(id=slug(name), name=name, roles=frozenset({PARTICIPANT, ADMIN}))

    def _from_headers(self, req: web.Request) -> Identity | None:
        if not self._trusted_peer(req.remote):
            if not self._warned_untrusted:
                self._warned_untrusted = True
                log.warning("ignoring identity headers from %s: not in MARVIN_TRUSTED_PROXIES", req.remote)
            return None
        user = req.headers.get(HDR_USER, "").strip()
        if not user:
            return None
        email = req.headers.get(HDR_EMAIL, "").strip() or None
        name = req.headers.get(HDR_NAME, "").strip() or (email.split("@", 1)[0] if email else "") or user
        groups = _csv(req.headers.get(HDR_GROUPS))
        roles = {PARTICIPANT}
        if groups & self.admin_groups or user.lower() in self.admin_users or (email and email.lower() in self.admin_users):
            roles.add(ADMIN)
        return Identity(id=slug(user), name=name, email=email, roles=frozenset(roles))

    def _trusted_peer(self, remote: str | None) -> bool:
        try:
            ip = ipaddress.ip_address(remote or "")
        except ValueError:
            return False
        return any(ip in net for net in self.trusted)

    # -- password mode -----------------------------------------------------------------
    def login(self, name: str, password: str) -> Identity | None:
        """Identity for a correct room or admin password, None otherwise. Constant-time compares on both."""
        name = name.strip()
        if not name or not password:
            return None
        is_admin = bool(self.admin_password) and hmac.compare_digest(password.encode(), self.admin_password.encode())
        is_room = hmac.compare_digest(password.encode(), self.room_password.encode())
        if not (is_admin or is_room):
            return None
        roles = {PARTICIPANT, ADMIN} if is_admin else {PARTICIPANT}
        email = name if "@" in name else None
        return Identity(id=slug(name), name=name, email=email, roles=frozenset(roles))

    def make_session(self, ident: Identity, now: float | None = None) -> str:
        payload = {"id": ident.id, "name": ident.name, "email": ident.email, "roles": sorted(ident.roles), "exp": int((now or time.time()) + self.session_seconds)}
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        return f"{body}.{_b64(self._sign(body))}"

    def read_session(self, token: str, now: float | None = None) -> Identity | None:
        if not token or "." not in token:
            return None
        body, sig = token.rsplit(".", 1)
        try:
            if not hmac.compare_digest(_unb64(sig), self._sign(body)):
                return None
            data = json.loads(_unb64(body))
            if float(data["exp"]) < (now or time.time()):
                return None
            email = data.get("email")
            return Identity(id=str(data["id"]), name=str(data["name"]), email=str(email) if email else None, roles=frozenset(str(r) for r in data["roles"]) | {PARTICIPANT})
        except Exception:
            return None

    def _sign(self, body: str) -> bytes:
        return hmac.new(self.secret, body.encode(), hashlib.sha256).digest()

    def too_many_failures(self, ip: str | None, now: float | None = None) -> bool:
        q = self._fails.get(ip or "?")
        if not q:
            return False
        now = now or time.time()
        while q and q[0] < now - 60:
            q.popleft()
        return len(q) >= FAILS_PER_MINUTE

    def record_failure(self, ip: str | None, now: float | None = None) -> None:
        self._fails.setdefault(ip or "?", deque()).append(now or time.time())


def cookie_kwargs(req: web.Request, max_age: int) -> dict:
    """Session cookie flags: HttpOnly, SameSite=Lax, Secure whenever the browser is on https (directly or via the proxy)."""
    https = req.secure or req.headers.get("X-Forwarded-Proto", "").lower() == "https"
    return {"path": "/", "httponly": True, "samesite": "Lax", "secure": https, "max_age": max_age}
