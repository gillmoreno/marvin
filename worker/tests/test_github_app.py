from aiohttp.test_utils import TestClient, TestServer

from marvin.admin import make_admin_app
from marvin.config import Config
from marvin.github import GitHubConnect, TokenStore
from marvin.github_app import GitHubApp
from marvin.license import LicenseStore, generate_keypair, issue
from marvin.room.manager import RoomManager

ADM = {"X-Marvin-User": "root", "X-Marvin-Roles": "admin,participant"}


def test_manifest_urls():
    app = GitHubApp(TokenStore(None, "s"), None)  # type: ignore[arg-type]
    m = app.manifest("https://marvin.example")
    assert m["redirect_url"] == "https://marvin.example/api/github/app/callback"
    assert m["setup_url"] == "https://marvin.example/api/github/app/install"
    assert m["default_permissions"]["contents"] == "write"


async def test_github_app_get_needs_license(tmp_path):
    gh = GitHubConnect(TokenStore(str(tmp_path), "s"))
    mgr = RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path), session_kwargs={})
    try:
        async with TestClient(TestServer(make_admin_app(mgr, gh))) as c:
            r = await c.get("/github/app", headers=ADM, params={"origin": "https://marvin.test"})
            assert r.status == 403
        priv, pub = generate_keypair()
        store = LicenseStore(str(tmp_path), "s", environ={}, public_pem=pub)
        store.put(issue("acme.com", "2027-11-01", 1, "*", private_pem=priv))
        async with TestClient(TestServer(make_admin_app(mgr, gh, licenses=store))) as c:
            r = await c.get("/github/app", headers=ADM, params={"origin": "https://marvin.test"})
            j = await r.json()
            assert r.status == 200 and j["manifest"]["url"] == "https://marvin.test"
    finally:
        await gh.aclose()
