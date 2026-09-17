"""Who may join this machine, the transcription notice, and the OIDC values oauth2-proxy needs.

Env wins over the file (``<state_dir>/access.json``). Settings writes the file. The token server reads
it on each login so a save does not need a restart. Docs: authentication.md, ee-company-pilot.md.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("marvin.access")

DEFAULT_NOTICE = "This room is transcribed. What you say is sent to the coding agent configured on this machine."


def _csv(value: str | None) -> list[str]:
    return [v.strip().lower() for v in (value or "").split(",") if v.strip()]


def _fernet(secret: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("marvin-access:" + secret).encode()).digest()))


class Access:
    """Allowed domains / allow-list / admin map / notice / SSO client. Env overrides the stored file."""

    def __init__(self, state_dir: str | None, secret: str, *, environ: dict[str, str] | None = None) -> None:
        env = environ if environ is not None else os.environ
        self.path = Path(state_dir) / "access.json" if state_dir else None
        self.install_dir = Path(env.get("MARVIN_INSTALL_DIR") or "") if env.get("MARVIN_INSTALL_DIR") else None
        self._fernet = _fernet(secret or "dev")
        self.env_domains = _csv(env.get("MARVIN_ALLOWED_EMAIL_DOMAINS"))
        self.env_allow = _csv(env.get("MARVIN_ALLOW_LIST"))
        self.env_admin_groups = _csv(env.get("MARVIN_ADMIN_GROUPS"))
        self.env_admin_users = _csv(env.get("MARVIN_ADMIN_USERS"))
        self.env_issuer = (env.get("OAUTH2_PROXY_OIDC_ISSUER_URL") or "").strip() or None
        self.env_client_id = (env.get("OAUTH2_PROXY_CLIENT_ID") or "").strip() or None
        self._data: dict[str, Any] = self._load()
        self._mtime = self.path.stat().st_mtime if self.path and self.path.exists() else 0.0

    def _load(self) -> dict[str, Any]:
        if not self.path or not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except Exception:
            log.exception("could not read %s", self.path)
            return {}

    def refresh(self) -> None:
        if not self.path or not self.path.exists():
            self._data = {}
            return
        m = self.path.stat().st_mtime
        if m != self._mtime:
            self._data = self._load()
            self._mtime = m

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2))
        tmp.chmod(0o600)
        tmp.replace(self.path)
        self._mtime = self.path.stat().st_mtime
        self.write_proxy_env()

    def allowed_domains(self) -> list[str]:
        self.refresh()
        return self.env_domains or _csv(self._data.get("allowed_domains"))

    def allow_list(self) -> list[str]:
        self.refresh()
        return self.env_allow or _csv(self._data.get("allow_list"))

    def admin_groups(self) -> list[str]:
        self.refresh()
        return self.env_admin_groups or _csv(self._data.get("admin_groups"))

    def admin_users(self) -> list[str]:
        self.refresh()
        return self.env_admin_users or _csv(self._data.get("admin_users"))

    def notice(self) -> str:
        self.refresh()
        text = (self._data.get("notice") or "").strip()
        return text or DEFAULT_NOTICE

    def email_allowed(self, email: str | None) -> bool:
        domains, allow = self.allowed_domains(), self.allow_list()
        if not domains and not allow:
            return True
        if not email or "@" not in email:
            return False
        e = email.strip().lower()
        if e in allow:
            return True
        return e.rsplit("@", 1)[-1] in domains

    def refusal(self) -> str:
        domains = self.allowed_domains()
        if domains:
            return f"This machine only accepts emails at {', '.join(domains)}."
        if self.allow_list():
            return "This machine only accepts addresses an admin has allowed."
        return "This email is not allowed."

    def _secret(self, key: str) -> str | None:
        enc = (self._data.get("sso") or {}).get(key)
        if not enc:
            return None
        try:
            return self._fernet.decrypt(enc.encode()).decode()
        except (InvalidToken, ValueError):
            return None

    def put(self, body: dict[str, Any]) -> dict[str, Any]:
        if "allowed_domains" in body:
            self._data["allowed_domains"] = ",".join(_csv(str(body.get("allowed_domains") or "")))
        if "allow_list" in body:
            self._data["allow_list"] = ",".join(_csv(str(body.get("allow_list") or "")))
        if "admin_groups" in body:
            self._data["admin_groups"] = ",".join(_csv(str(body.get("admin_groups") or "")))
        if "admin_users" in body:
            self._data["admin_users"] = ",".join(_csv(str(body.get("admin_users") or "")))
        if "notice" in body:
            self._data["notice"] = str(body.get("notice") or "").strip()
        sso = self._data.setdefault("sso", {})
        if "issuer" in body:
            sso["issuer"] = str(body.get("issuer") or "").strip()
        if "client_id" in body:
            sso["client_id"] = str(body.get("client_id") or "").strip()
        if "email_domains" in body:
            sso["email_domains"] = str(body.get("email_domains") or "").strip()
        if "groups_claim" in body:
            sso["groups_claim"] = str(body.get("groups_claim") or "groups").strip() or "groups"
        if "provider" in body:
            sso["provider"] = str(body.get("provider") or "oidc").strip() or "oidc"
        secret = str(body.get("client_secret") or "").strip()
        if secret:
            sso["client_secret_enc"] = self._fernet.encrypt(secret.encode()).decode()
        cookie = str(body.get("cookie_secret") or "").strip()
        if cookie:
            sso["cookie_secret_enc"] = self._fernet.encrypt(cookie.encode()).decode()
        self._data["updated_at"] = time.time()
        self._save()
        return self.public(admin=True)

    def public(self, *, admin: bool = False) -> dict[str, Any]:
        self.refresh()
        sso = self._data.get("sso") or {}
        out = {
            "notice": self.notice(),
            "allowed_domains": self.allowed_domains(),
            "allow_list": self.allow_list() if admin else [],
            "restricted": bool(self.allowed_domains() or self.allow_list()),
            "allowed_domains_source": "env" if self.env_domains else ("settings" if _csv(self._data.get("allowed_domains")) else None),
            "sso": {
                "issuer": self.env_issuer or sso.get("issuer") or None,
                "client_id": self.env_client_id or sso.get("client_id") or None,
                "email_domains": sso.get("email_domains") or None,
                "groups_claim": sso.get("groups_claim") or "groups",
                "provider": sso.get("provider") or "oidc",
                "configured": bool(self.env_issuer or self.env_client_id or sso.get("issuer") or sso.get("client_id")),
                "source": "env" if (self.env_issuer or self.env_client_id) else ("settings" if (sso.get("issuer") or sso.get("client_id")) else None),
                "has_secret": bool(self.env_client_id or self._secret("client_secret_enc")),
            },
        }
        if admin:
            out["admin_groups"] = self.admin_groups()
            out["admin_users"] = self.admin_users()
            out["admin_groups_source"] = "env" if self.env_admin_groups else ("settings" if _csv(self._data.get("admin_groups")) else None)
        return out

    def write_proxy_env(self) -> Path | None:
        """File compose can env_file. Secrets stay on disk mode 0600, not in the repo."""
        dest_dir = self.install_dir
        if dest_dir is None:
            return None
        self.refresh()
        sso = self._data.setdefault("sso", {})
        issuer = self.env_issuer or sso.get("issuer") or ""
        cid = self.env_client_id or sso.get("client_id") or ""
        provider = sso.get("provider") or "oidc"
        if not cid:
            return None
        if provider != "github" and not issuer:
            return None
        secret = os.environ.get("OAUTH2_PROXY_CLIENT_SECRET") or self._secret("client_secret_enc") or ""
        cookie = os.environ.get("OAUTH2_PROXY_COOKIE_SECRET") or self._secret("cookie_secret_enc") or ""
        if not cookie:
            cookie = secrets.token_urlsafe(32)
            sso["cookie_secret_enc"] = self._fernet.encrypt(cookie.encode()).decode()
            if self.path:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._data, indent=2))
                tmp.chmod(0o600)
                tmp.replace(self.path)
        dest = dest_dir / ".oauth2-proxy.env"
        dest.write_text(
            "\n".join([
                f"OAUTH2_PROXY_PROVIDER={provider}",
                f"OAUTH2_PROXY_OIDC_ISSUER_URL={issuer}",
                f"OAUTH2_PROXY_CLIENT_ID={cid}",
                f"OAUTH2_PROXY_CLIENT_SECRET={secret}",
                f"OAUTH2_PROXY_COOKIE_SECRET={cookie}",
                f"OAUTH2_PROXY_EMAIL_DOMAINS={sso.get('email_domains') or '*'}",
                f"OAUTH2_PROXY_OIDC_GROUPS_CLAIM={sso.get('groups_claim') or 'groups'}",
                "",
            ])
        )
        dest.chmod(0o600)
        return dest
