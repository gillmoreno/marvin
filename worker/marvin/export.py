"""Ship a closed audit session to the customer's S3 bucket and/or a JSON webhook. No phone-home to us."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from cryptography.fernet import Fernet, InvalidToken

from marvin.audit import Meeting
from marvin.license import allows as license_allows

log = logging.getLogger("marvin.export")


def _fernet(secret: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("marvin-export:" + secret).encode()).digest()))


class Exporter:
    def __init__(self, state_dir: str | None, secret: str, *, environ: dict[str, str] | None = None) -> None:
        env = environ if environ is not None else os.environ
        self.path = Path(state_dir) / "export.json" if state_dir else None
        self._fernet = _fernet(secret or "dev")
        self.env_bucket = (env.get("MARVIN_AUDIT_S3_BUCKET") or "").strip() or None
        self.env_webhook = (env.get("MARVIN_AUDIT_WEBHOOK") or "").strip() or None
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path or not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {}

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def _dec(self, key: str) -> str | None:
        enc = self._data.get(key)
        if not enc:
            return None
        try:
            return self._fernet.decrypt(enc.encode()).decode()
        except (InvalidToken, ValueError):
            return None

    def put(self, body: dict[str, Any]) -> dict[str, Any]:
        for k in ("bucket", "region", "prefix", "webhook", "object_lock"):
            if k in body:
                val = body.get(k)
                if k == "object_lock":
                    self._data[k] = bool(val)
                else:
                    self._data[k] = str(val or "").strip()
        for secret_name in ("access_key", "secret_key"):
            raw = str(body.get(secret_name) or "").strip()
            if raw:
                self._data[secret_name + "_enc"] = self._fernet.encrypt(raw.encode()).decode()
        self._save()
        return self.public()

    def public(self) -> dict[str, Any]:
        return {
            "bucket": self.env_bucket or self._data.get("bucket") or None,
            "region": self._data.get("region") or "eu-central-1",
            "prefix": self._data.get("prefix") or "marvin-audit/",
            "webhook": self.env_webhook or self._data.get("webhook") or None,
            "object_lock": bool(self._data.get("object_lock")),
            "has_keys": bool(self.env_bucket or self._dec("access_key_enc")),
            "source": "env" if self.env_bucket or self.env_webhook else ("settings" if self._data.get("bucket") or self._data.get("webhook") else None),
        }

    def ship(self, meeting: Meeting, path: Path) -> None:
        if not license_allows("audit"):
            return
        body = path.read_bytes()
        key = f"{self.public()['prefix'].rstrip('/')}/{meeting.room}/{meeting.id}.jsonl"
        bucket = self.env_bucket or self._data.get("bucket")
        webhook = self.env_webhook or self._data.get("webhook")
        if bucket:
            self._put_s3(bucket, key, body)
        if webhook:
            self._post_webhook(webhook, meeting, body)

    def _put_s3(self, bucket: str, key: str, body: bytes) -> None:
        region = self._data.get("region") or os.environ.get("AWS_REGION") or "eu-central-1"
        ak = os.environ.get("AWS_ACCESS_KEY_ID") or self._dec("access_key_enc")
        sk = os.environ.get("AWS_SECRET_ACCESS_KEY") or self._dec("secret_key_enc")
        if not ak or not sk:
            log.warning("audit s3: no keys; skipped %s", key)
            return
        # boto3 is optional; fall back to a signed PUT so we do not force a fat dep on every laptop.
        try:
            import boto3
            client = boto3.client("s3", region_name=region, aws_access_key_id=ak, aws_secret_access_key=sk)
            args: dict[str, Any] = {"Bucket": bucket, "Key": key, "Body": body, "ContentType": "application/x-ndjson"}
            if self._data.get("object_lock"):
                args["ObjectLockMode"] = "GOVERNANCE"
            client.put_object(**args)
            log.info("audit s3 s3://%s/%s", bucket, key)
            return
        except ImportError:
            pass
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{quote(key)}"
        # Minimal AWS SigV4 via httpx is a lot of code; require boto3 for S3. Webhook still works without it.
        log.warning("audit s3: install boto3 on the worker to upload (pip/uv add boto3). skipped %s", url)

    def _post_webhook(self, url: str, meeting: Meeting, body: bytes) -> None:
        try:
            r = httpx.post(
                url,
                content=body,
                headers={
                    "content-type": "application/x-ndjson",
                    "x-marvin-session": meeting.id,
                    "x-marvin-room": meeting.room,
                },
                timeout=20.0,
            )
            if r.status_code >= 300:
                log.warning("audit webhook %s -> %s", url, r.status_code)
        except Exception:
            log.exception("audit webhook %s", url)
