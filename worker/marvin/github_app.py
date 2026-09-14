"""GitHub App as the machine identity (manifest flow). Installation tokens replace a shared PAT."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt

log = logging.getLogger("marvin.github_app")


class GitHubApp:
    def __init__(self, store: Any, http: httpx.AsyncClient) -> None:
        self.store = store
        self.http = http
        self._token: tuple[float, str] | None = None

    def rec(self) -> dict[str, Any]:
        return dict(self.store._data.get("settings", {}).get("app") or {})

    def _put(self, **kw: Any) -> None:
        settings = self.store._data.setdefault("settings", {})
        cur = dict(settings.get("app") or {})
        cur.update(kw)
        settings["app"] = cur
        self.store._save()

    def public(self) -> dict[str, Any]:
        r = self.rec()
        return {
            "id": r.get("id"),
            "slug": r.get("slug"),
            "owner": r.get("owner"),
            "installation_id": r.get("installation_id"),
            "configured": bool(r.get("id") and r.get("pem_enc")),
            "installed": bool(r.get("installation_id")),
        }

    def manifest(self, origin: str) -> dict[str, Any]:
        origin = origin.rstrip("/")
        return {
            "name": "Marvin",
            "url": origin,
            "hook_attributes": {"url": f"{origin}/api/github/app/hook", "active": False},
            "redirect_url": f"{origin}/api/github/app/callback",
            "callback_urls": [f"{origin}/api/github/app/callback"],
            "setup_url": f"{origin}/api/github/app/install",
            "public": False,
            "default_permissions": {"contents": "write", "pull_requests": "write", "metadata": "read"},
        }

    async def convert(self, code: str) -> dict[str, Any]:
        r = await self.http.post(f"https://api.github.com/app-manifests/{code}/conversions", headers={"Accept": "application/vnd.github+json"})
        if r.status_code >= 300:
            raise RuntimeError(r.text[:400] or f"GitHub {r.status_code}")
        data = r.json()
        pem = data.get("pem") or ""
        self._put(
            id=str(data.get("id") or ""),
            slug=data.get("slug"),
            client_id=data.get("client_id"),
            owner=(data.get("owner") or {}).get("login"),
            pem_enc=self.store._fernet.encrypt(pem.encode()).decode() if pem else None,
            webhook_secret_enc=self.store._fernet.encrypt((data.get("webhook_secret") or "").encode()).decode() if data.get("webhook_secret") else None,
        )
        log.info("github app: created %s", data.get("slug"))
        return self.public()

    def pem(self) -> str | None:
        enc = self.rec().get("pem_enc")
        if not enc:
            return None
        try:
            return self.store._fernet.decrypt(enc.encode()).decode()
        except Exception:
            return None

    def jwt(self) -> str:
        rec = self.rec()
        pem = self.pem()
        if not rec.get("id") or not pem:
            raise RuntimeError("no GitHub App on this machine")
        now = int(time.time())
        return jwt.encode({"iat": now - 30, "exp": now + 8 * 60, "iss": rec["id"]}, pem, algorithm="RS256")

    def set_installation(self, installation_id: str) -> dict[str, Any]:
        self._put(installation_id=str(installation_id))
        self._token = None
        return self.public()

    def token(self) -> str | None:
        rec = self.rec()
        if not rec.get("installation_id") or not self.pem():
            return None
        if self._token and self._token[0] > time.time() + 60:
            return self._token[1]
        # sync httpx for the token path used by git at turn start
        try:
            r = httpx.post(
                f"https://api.github.com/app/installations/{rec['installation_id']}/access_tokens",
                headers={"Authorization": f"Bearer {self.jwt()}", "Accept": "application/vnd.github+json"},
                timeout=15.0,
            )
            if r.status_code >= 300:
                log.warning("github app token: %s", r.status_code)
                return None
            tok = r.json().get("token")
            exp = time.time() + 50 * 60
            if tok:
                self._token = (exp, tok)
            return tok
        except Exception:
            log.exception("github app token")
            return None

    async def repos(self, query: str = "") -> list[dict[str, Any]]:
        rec = self.rec()
        if not rec.get("installation_id"):
            return []
        tok = self.token()
        if not tok:
            return []
        r = await self.http.get(
            "https://api.github.com/installation/repositories",
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
            params={"per_page": 100},
        )
        if r.status_code >= 300:
            return []
        repos = []
        for repo in r.json().get("repositories") or []:
            repos.append({
                "full_name": repo.get("full_name"),
                "description": repo.get("description") or "",
                "clone_url": repo.get("clone_url"),
                "private": bool(repo.get("private")),
                "default_branch": repo.get("default_branch") or "main",
            })
        if query:
            q = query.lower()
            repos = [x for x in repos if q in (x["full_name"] or "").lower() or q in x["description"].lower()]
        return repos
