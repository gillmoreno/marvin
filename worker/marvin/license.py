"""Offline Enterprise license: a JWT we sign, the worker checks with a public key in this package.

No phone-home. ``MARVIN_LICENSE_KEY`` wins over the key stored from Settings (encrypted in
``<state_dir>/license.json``). Issue tokens with ``tools/issue-license.py`` and the private key
that is not in this repo. Docs: ``docs_and_changelog/licensing.md``.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)

log = logging.getLogger("marvin.license")

ISS = "marvin"
AUD = "marvin-ee"
KID = "marvin-1"
ALG = "EdDSA"
PUBLIC_PATH = Path(__file__).with_name("license.pub")
# What a subscription can turn on. Code that lands in ee/ should call allows("sso") etc.
FEATURES = (
    "sso",
    "roles",
    "audit",
    "retention",
    "isolation",
    "helm",
    "gpu-stt",
    "supply-chain",
    "support",
)
_SKEW = 60
_store: "LicenseStore | None" = None


def public_pem() -> bytes:
    return PUBLIC_PATH.read_bytes()


def load_public(pem: bytes | None = None) -> Ed25519PublicKey:
    key = load_pem_public_key(pem or public_pem())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("license public key must be Ed25519")
    return key


def load_private(pem: bytes) -> Ed25519PrivateKey:
    key = load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("license private key must be Ed25519")
    return key


def generate_keypair() -> tuple[bytes, bytes]:
    priv = Ed25519PrivateKey.generate()
    return (
        priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()),
        priv.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo),
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64url(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _dump(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()


def expires_unix(expires: str | int) -> int:
    if isinstance(expires, int):
        if expires <= 0:
            raise ValueError("expiry must be a future unix time or YYYY-MM-DD")
        return expires
    day = datetime.strptime(expires.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(day.replace(hour=23, minute=59, second=59).timestamp())


def _features(raw: Iterable[str] | str | None) -> tuple[str, ...]:
    if raw is None or raw == "" or raw == "*":
        return ("*",)
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in raw if str(p).strip()]
    if not parts or parts == ["*"]:
        return ("*",)
    unknown = [p for p in parts if p != "*" and p not in FEATURES]
    if unknown:
        raise ValueError(f"unknown feature(s): {', '.join(unknown)}; known: {', '.join(FEATURES)} or *")
    return tuple(parts)


def issue(
    company: str,
    expires: str | int,
    seats: int = 10,
    features: Iterable[str] | str | None = "*",
    *,
    private_pem: bytes,
    now: int | None = None,
) -> str:
    """Mint a customer JWT. Run this on our machine; they never run it."""
    company = (company or "").strip()
    if not company or len(company) > 200 or "\n" in company:
        raise ValueError("company must be a short name or domain (e.g. example.com)")
    seats = int(seats)
    if seats < 1 or seats > 1_000_000:
        raise ValueError("seats must be a positive integer")
    exp = expires_unix(expires)
    iat = int(now if now is not None else time.time())
    if exp <= iat:
        raise ValueError("expiry is not in the future")
    header = {"alg": ALG, "typ": "JWT", "kid": KID}
    payload = {
        "iss": ISS,
        "aud": AUD,
        "sub": company,
        "iat": iat,
        "exp": exp,
        "seats": seats,
        "features": list(_features(features)),
    }
    signing = f"{_b64url(_dump(header))}.{_b64url(_dump(payload))}".encode()
    sig = load_private(private_pem).sign(signing)
    return f"{signing.decode()}.{_b64url(sig)}"


@dataclass(frozen=True)
class Status:
    valid: bool
    reason: str | None
    company: str | None = None
    seats: int | None = None
    expires_at: int | None = None
    features: tuple[str, ...] = ()
    source: str | None = None
    has_key: bool = False
    key_hint: str | None = None

    def allows(self, feature: str) -> bool:
        if not self.valid:
            return False
        if not self.features or "*" in self.features:
            return True
        return feature in self.features

    def message(self) -> str:
        if self.valid:
            when = datetime.fromtimestamp(self.expires_at or 0, tz=timezone.utc).strftime("%Y-%m-%d")
            who = self.company or "unknown"
            n = f"{self.seats} seats" if self.seats else "licensed"
            return f"{who} · {n} · until {when}"
        return {
            None: "No license key. This machine is the free core.",
            "missing": "No license key. This machine is the free core.",
            "malformed": "That does not look like a Marvin license key.",
            "bad_signature": "This key was not issued by us, or it was changed.",
            "expired": "This license has ended.",
            "wrong_issuer": "This key is not a Marvin license.",
        }.get(self.reason, "This license is not valid.")

    def public(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "message": self.message(),
            "company": self.company,
            "seats": self.seats,
            "expires_at": self.expires_at,
            "features": list(self.features),
            "source": self.source,
            "has_key": self.has_key,
            "ee": self.valid,
            "key_hint": self.key_hint,
        }


def verify(token: str | None, *, public_pem: bytes | None = None, now: int | None = None, source: str | None = None) -> Status:
    if not (token or "").strip():
        return Status(False, "missing", source=source, has_key=False)
    raw = token.strip()
    parts = raw.split(".")
    if len(parts) != 3:
        return Status(False, "malformed", source=source, has_key=True)
    try:
        header = json.loads(_unb64url(parts[0]))
        payload = json.loads(_unb64url(parts[1]))
        sig = _unb64url(parts[2])
    except (ValueError, json.JSONDecodeError):
        return Status(False, "malformed", source=source, has_key=True)
    if header.get("alg") != ALG or not isinstance(payload, dict):
        return Status(False, "malformed", source=source, has_key=True)
    try:
        load_public(public_pem).verify(sig, f"{parts[0]}.{parts[1]}".encode())
    except (InvalidSignature, ValueError):
        return Status(False, "bad_signature", source=source, has_key=True)
    if payload.get("iss") != ISS or payload.get("aud") != AUD:
        return Status(False, "wrong_issuer", source=source, has_key=True)
    exp = payload.get("exp")
    if not isinstance(exp, int):
        return Status(False, "malformed", source=source, has_key=True)
    clock = int(now if now is not None else time.time())
    if exp + _SKEW < clock:
        return Status(False, "expired", company=str(payload.get("sub") or "") or None, seats=_seats(payload), expires_at=exp, features=_read_features(payload), source=source, has_key=True)
    seats = _seats(payload)
    company = str(payload.get("sub") or "").strip() or None
    if not company or seats is None:
        return Status(False, "malformed", source=source, has_key=True)
    return Status(True, None, company=company, seats=seats, expires_at=exp, features=_read_features(payload), source=source, has_key=True)


def _seats(payload: dict[str, Any]) -> int | None:
    n = payload.get("seats")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        return None
    return n


def _read_features(payload: dict[str, Any]) -> tuple[str, ...]:
    raw = payload.get("features")
    if raw == "*" or raw is None:
        return ("*",)
    if isinstance(raw, str):
        return tuple(p.strip() for p in raw.split(",") if p.strip()) or ("*",)
    if isinstance(raw, list):
        return tuple(str(p).strip() for p in raw if str(p).strip()) or ("*",)
    return ("*",)


def _hint(secret: str) -> str:
    if len(secret) <= 8:
        return "•" * len(secret)
    return secret[:4] + "•" * min(12, len(secret) - 8) + secret[-4:]


class LicenseStore:
    """Env override, then the encrypted key in ``<state_dir>/license.json``."""

    def __init__(
        self,
        state_dir: str | None,
        secret: str,
        *,
        environ: dict[str, str] | None = None,
        public_pem: bytes | None = None,
    ) -> None:
        env = environ if environ is not None else os.environ
        self.env_key = (env.get("MARVIN_LICENSE_KEY") or "").strip() or None
        self.path = Path(state_dir) / "license.json" if state_dir else None
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("marvin-license:" + secret).encode()).digest()))
        self._public_pem = public_pem
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path or not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except Exception:
            log.exception("could not read %s", self.path)
            return {}

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def _stored_key(self) -> str | None:
        enc = self._data.get("key_enc")
        if not enc:
            return None
        try:
            return self._fernet.decrypt(enc.encode()).decode()
        except (InvalidToken, ValueError):
            log.warning("license key cannot be decrypted (session secret changed?); dropping it")
            self.clear()
            return None

    def raw_key(self) -> str | None:
        return self.env_key or self._stored_key()

    def source(self) -> str | None:
        if self.env_key:
            return "env"
        if self._stored_key():
            return "settings"
        return None

    def status(self) -> Status:
        raw = self.raw_key()
        st = verify(raw, public_pem=self._public_pem, source=self.source())
        return replace(st, key_hint=_hint(raw)) if raw else st

    def put(self, key: str) -> Status:
        if self.env_key:
            raise RuntimeError("MARVIN_LICENSE_KEY is set in the environment; it wins over Settings")
        st = verify((key or "").strip(), public_pem=self._public_pem, source="settings")
        if not st.valid:
            raise ValueError(st.message())
        self._data["key_enc"] = self._fernet.encrypt(key.strip().encode()).decode()
        self._save()
        return self.status()

    def clear(self) -> Status:
        if self.env_key:
            raise RuntimeError("MARVIN_LICENSE_KEY is set in the environment; it wins over Settings")
        if self._data.pop("key_enc", None) is not None:
            self._save()
        return self.status()


def bind(store: LicenseStore | None) -> None:
    global _store
    _store = store


def current() -> Status:
    if _store is not None:
        return _store.status()
    return verify(os.environ.get("MARVIN_LICENSE_KEY"), source="env" if os.environ.get("MARVIN_LICENSE_KEY") else None)


def allows(feature: str) -> bool:
    return current().allows(feature)
