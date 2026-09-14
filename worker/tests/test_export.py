from pathlib import Path

import httpx

from marvin.audit import Meeting
from marvin.export import Exporter


def test_export_settings_encrypt_keys(tmp_path):
    e = Exporter(str(tmp_path), "s")
    e.put({"bucket": "logs", "region": "eu-central-1", "access_key": "AKIAFAKEKEY", "secret_key": "s3cr3t-value-xyz", "webhook": "https://siem.test/h"})
    raw = (tmp_path / "export.json").read_text()
    assert "AKIAFAKEKEY" not in raw and "s3cr3t-value-xyz" not in raw
    pub = e.public()
    assert pub["bucket"] == "logs" and pub["has_keys"] and pub["webhook"] == "https://siem.test/h"


def test_webhook_ships_when_license_allows(tmp_path, monkeypatch):
    seen = []

    def fake_post(url, **kw):
        seen.append((url, kw["headers"]["x-marvin-session"], kw["content"]))
        return httpx.Response(204)

    monkeypatch.setattr("marvin.export.license_allows", lambda f: True)
    monkeypatch.setattr(httpx, "post", fake_post)
    e = Exporter(str(tmp_path), "s")
    e.put({"webhook": "https://siem.test/h"})
    meeting = Meeting(id="abc", room="demo", started_at=1)
    path = tmp_path / "s.jsonl"
    path.write_text('{"verb":"turn"}\n')
    e.ship(meeting, path)
    assert seen == [("https://siem.test/h", "abc", path.read_bytes())]


def test_ship_is_noop_without_license(tmp_path, monkeypatch):
    monkeypatch.setattr("marvin.export.license_allows", lambda f: False)
    e = Exporter(str(tmp_path), "s")
    e.put({"webhook": "https://siem.test/h"})
    called = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: called.append(1))
    e.ship(Meeting(id="x", room="r", started_at=1), Path(__file__))
    assert called == []
