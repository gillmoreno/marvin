from datetime import datetime, timezone

from aiohttp.test_utils import TestClient, TestServer

from marvin.admin import make_admin_app
from marvin.config import Config
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import ee  # noqa: E402
from marvin.license import FEATURES, LicenseStore, bind, generate_keypair, issue, verify
from marvin.room.manager import RoomManager

ADM = {"X-Marvin-User": "root", "X-Marvin-Roles": "admin,participant"}
WHO = {"X-Marvin-User": "pat", "X-Marvin-Roles": "participant"}


def _pair_token(company="example.com", expires="2027-11-01", seats=50, features="*", now=None):
    priv, pub = generate_keypair()
    token = issue(company, expires, seats, features, private_pem=priv, now=now)
    return token, pub, priv


def test_issue_and_verify():
    token, pub, _ = _pair_token()
    st = verify(token, public_pem=pub, now=int(datetime(2026, 9, 14, tzinfo=timezone.utc).timestamp()))
    assert st.valid and st.company == "example.com" and st.seats == 50
    assert st.allows("sso") and st.allows("audit")
    assert "*" in st.features


def test_tampered_and_wrong_key_fail():
    token, pub, _ = _pair_token()
    parts = token.split(".")
    bad = parts[0] + "." + parts[1][:-2] + "xx." + parts[2]
    assert verify(bad, public_pem=pub).reason == "malformed" or verify(bad, public_pem=pub).reason == "bad_signature"
    other = generate_keypair()[1]
    assert verify(token, public_pem=other).reason == "bad_signature"
    assert verify(token).reason == "bad_signature"  # bundled public key, this token was not ours
    assert verify("not-a-jwt").reason == "malformed"
    assert verify(None).reason == "missing"
    assert not verify(None).allows("sso")


def test_expired_and_unknown_feature():
    token, pub, priv = _pair_token(expires="2020-01-01", now=1)
    st = verify(token, public_pem=pub, now=int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()))
    assert st.valid is False and st.reason == "expired" and st.company == "example.com"
    token, pub, _ = _pair_token(features="sso,audit")
    st = verify(token, public_pem=pub, now=1_800_000_000)
    assert st.allows("sso") and not st.allows("isolation")
    try:
        issue("x", "2027-01-01", 1, "nope", private_pem=priv)
        raise AssertionError("unknown feature should fail")
    except ValueError as e:
        assert "unknown" in str(e)
    assert "sso" in FEATURES


def test_store_env_wins_and_rejects_bad(tmp_path):
    priv, pub = generate_keypair()
    good = issue("acme.com", "2027-11-01", 10, "*", private_pem=priv)
    env = LicenseStore(str(tmp_path), "secret", environ={"MARVIN_LICENSE_KEY": good}, public_pem=pub)
    assert env.status().valid and env.status().source == "env"
    try:
        env.put("x.y.z")
        raise AssertionError("env should block Settings")
    except RuntimeError:
        pass
    store = LicenseStore(str(tmp_path), "secret", environ={}, public_pem=pub)
    assert store.status().reason == "missing"
    try:
        store.put("eyJ.not.real")
        raise AssertionError("bad key should not store")
    except ValueError:
        pass
    assert store.status().reason == "missing"
    assert store.put(good).valid and store.status().source == "settings"
    assert store.path and store.path.is_file()
    text = store.path.read_text()
    assert good not in text and "key_enc" in text
    assert store.clear().reason == "missing"


async def test_admin_license_routes(tmp_path):
    priv, pub = generate_keypair()
    good = issue("acme.com", "2027-11-01", 25, "sso,audit", private_pem=priv)
    store = LicenseStore(str(tmp_path), "secret", environ={}, public_pem=pub)
    mgr = RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path), session_kwargs={})
    async with TestClient(TestServer(make_admin_app(mgr, licenses=store))) as c:
        guest = await (await c.get("/license", headers=WHO)).json()
        assert guest["valid"] is False and guest["ee"] is False
        j = await (await c.get("/license", headers=ADM)).json()
        assert j["valid"] is False and j["ee"] is False
        bad = await c.put("/license", json={"key": "nope"}, headers=ADM)
        assert bad.status == 400
        ok = await c.put("/license", json={"key": good}, headers=ADM)
        body = await ok.json()
        assert ok.status == 200 and body["valid"] and body["company"] == "acme.com" and body["seats"] == 25
        assert body["source"] == "settings"
        gone = await (await c.delete("/license", headers=ADM)).json()
        assert gone["valid"] is False


def test_ee_package_follows_license(tmp_path):
    priv, pub = generate_keypair()
    store = LicenseStore(str(tmp_path), "s", environ={}, public_pem=pub)
    bind(store)
    try:
        assert ee.enabled("sso") is False
        store.put(issue("acme.com", "2027-11-01", 1, "*", private_pem=priv))
        assert ee.enabled("sso") is True
    finally:
        bind(None)
