from aiohttp.test_utils import TestClient, TestServer

from marvin.access import DEFAULT_NOTICE, Access
from marvin.admin import make_admin_app
from marvin.config import Config
from marvin.room.manager import RoomManager

ADM = {"X-Marvin-User": "root", "X-Marvin-Roles": "admin,participant"}


def test_open_until_restricted(tmp_path):
    a = Access(str(tmp_path), "s")
    assert a.email_allowed(None) and a.email_allowed("anyone@x.test")
    a.put({"allowed_domains": "Company.COM", "allow_list": "Friend@Other.dev", "notice": "We record this room."})
    assert a.allowed_domains() == ["company.com"]
    assert a.email_allowed("maria@company.com") and a.email_allowed("friend@other.dev")
    assert not a.email_allowed("alex@gmail.com") and not a.email_allowed(None)
    assert a.notice() == "We record this room."
    assert "company.com" in a.refusal()
    pub = a.public(admin=True)
    assert pub["restricted"] and pub["allowed_domains_source"] == "settings"


def test_env_wins_over_file(tmp_path, monkeypatch):
    a = Access(str(tmp_path), "s", environ={"MARVIN_ALLOWED_EMAIL_DOMAINS": "acme.test"})
    a.put({"allowed_domains": "other.test"})
    assert a.allowed_domains() == ["acme.test"]
    assert a.public()["allowed_domains_source"] == "env"


def test_proxy_env_only_when_issuer_and_install_dir(tmp_path):
    a = Access(str(tmp_path / "state"), "s", environ={"MARVIN_INSTALL_DIR": str(tmp_path)})
    a.put({"allowed_domains": "x.test"})
    assert not (tmp_path / ".oauth2-proxy.env").exists()
    a.put({"issuer": "https://login.example/v2.0", "client_id": "abc", "client_secret": "shh"})
    dest = tmp_path / ".oauth2-proxy.env"
    text = dest.read_text()
    assert dest.stat().st_mode & 0o777 == 0o600
    assert "OAUTH2_PROXY_OIDC_ISSUER_URL=https://login.example/v2.0" in text
    assert "OAUTH2_PROXY_CLIENT_SECRET=shh" in text
    assert "OAUTH2_PROXY_COOKIE_SECRET=" in text
    assert a.notice() == DEFAULT_NOTICE


async def test_sso_put_needs_license(tmp_path):
    access = Access(str(tmp_path), "s")
    mgr = RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path), session_kwargs={})
    async with TestClient(TestServer(make_admin_app(mgr, access=access))) as c:
        ok = await c.put("/access", json={"allowed_domains": "company.com", "notice": "hi"}, headers=ADM)
        assert ok.status == 200
        no = await c.put("/access", json={"issuer": "https://login.example/v2.0", "client_id": "x"}, headers=ADM)
        assert no.status == 403 and (await no.json())["feature"] == "sso"
