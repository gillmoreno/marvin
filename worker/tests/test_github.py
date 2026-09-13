"""GitHub device flow, encrypted token store and per-turn git identity files (marvin.github)."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from aiohttp.test_utils import TestClient, TestServer

from marvin.github import Connection, GitHubConnect, GitIdentity, TokenStore


class FakeGitHub:
    """httpx mock transport for github.com: device code, token polling (pending -> token), /user."""

    def __init__(self, *, deny: bool = False, device_flow_disabled: bool = False) -> None:
        self.polls = 0
        self.deny = deny
        self.device_flow_disabled = device_flow_disabled

    def handler(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.endswith("/login/device/code"):
            assert b"client_id=Iv1.test" in req.content and b"scope=repo" in req.content
            if self.device_flow_disabled:
                return httpx.Response(400, json={"error": "device_flow_disabled", "error_description": "Device Flow must be explicitly enabled for this App"})
            return httpx.Response(200, json={"device_code": "dc", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device", "expires_in": 900, "interval": 0.01})
        if url.endswith("/login/oauth/access_token"):
            self.polls += 1
            if self.deny:
                return httpx.Response(200, json={"error": "access_denied"})
            if self.polls == 1:
                return httpx.Response(200, json={"error": "authorization_pending"})
            if self.polls == 2:
                return httpx.Response(200, json={"error": "slow_down", "interval": 0.01})
            return httpx.Response(200, json={"access_token": "gho_secret", "token_type": "bearer", "scope": "repo,read:org"})
        if url.endswith("/user"):
            assert req.headers["Authorization"] == "Bearer gho_secret"
            return httpx.Response(200, json={"login": "gil", "id": 42, "name": "Gil Moreno", "email": None})
        if url.endswith("/user/emails"):
            return httpx.Response(200, json=[{"email": "gil@example.com", "primary": True, "verified": True}])
        if "/user/repos" in url:
            self.polls += 100  # count listing calls separately from token polls
            if req.headers["Authorization"] == "Bearer revoked":
                return httpx.Response(401, json={"message": "Bad credentials"})
            page = int(req.url.params.get("page", "1"))
            if page > 1:
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[
                {"full_name": "acme/web", "html_url": "https://github.com/acme/web", "clone_url": "https://github.com/acme/web.git", "default_branch": "main", "private": True, "pushed_at": "2026-09-12T00:00:00Z", "description": "the storefront", "language": "TypeScript"},
                {"full_name": "acme/api", "html_url": "https://github.com/acme/api", "clone_url": "https://github.com/acme/api.git", "default_branch": "develop", "private": False, "pushed_at": None, "description": None, "language": None},
            ])
        raise AssertionError(url)


def connect_for(tmp_path, fake: FakeGitHub, client_id="Iv1.test") -> GitHubConnect:
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), headers={"Accept": "application/json"})
    return GitHubConnect(TokenStore(str(tmp_path), secret="s3"), client_id=client_id, http=http)


async def wait_for(flow, status="connected", timeout=2.0):
    for _ in range(int(timeout / 0.01)):
        if flow.status != "pending":
            break
        await asyncio.sleep(0.01)
    assert flow.status == status, (flow.status, flow.error)


def test_token_store_encrypts_at_rest(tmp_path):
    store = TokenStore(str(tmp_path), secret="s3")
    store.put("gil", Connection(login="gil", name="Gil", email="g@x", token="gho_secret"))
    raw = (tmp_path / "github.json").read_text()
    assert "gho_secret" not in raw
    assert (tmp_path / "github.json").stat().st_mode & 0o777 == 0o600
    assert TokenStore(str(tmp_path), secret="s3").get("gil").token == "gho_secret"
    # a different secret cannot read it, and the unreadable record is dropped rather than served
    other = TokenStore(str(tmp_path), secret="other")
    assert other.get("gil") is None
    assert json.loads((tmp_path / "github.json").read_text())["users"] == {}


async def test_device_flow_end_to_end(tmp_path):
    fake = FakeGitHub()
    gh = connect_for(tmp_path, fake)
    assert gh.status("gil") == {"configured": True, "connected": None, "machine_identity": gh.machine_token is not None}
    flow = await gh.start("gil")
    assert flow.user_code == "ABCD-1234" and flow.verification_uri.endswith("/login/device")
    assert gh.get_flow(flow.id, "gil") is flow and gh.get_flow(flow.id, "someone-else") is None
    await wait_for(flow)
    assert fake.polls == 3  # pending, slow_down, token
    conn = gh.store.get("gil")
    assert conn.login == "gil" and conn.name == "Gil Moreno" and conn.email == "gil@example.com" and conn.token == "gho_secret"
    assert gh.status("gil")["connected"]["login"] == "gil"
    gh.disconnect("gil")
    assert gh.status("gil")["connected"] is None
    await gh.aclose()


async def test_device_flow_denied_and_restart_cancels_previous(tmp_path):
    fake = FakeGitHub(deny=True)
    gh = connect_for(tmp_path, fake)
    first = await gh.start("gil")
    second = await gh.start("gil")  # a second click cancels the first flow
    assert first.id not in gh.flows and second.id in gh.flows
    await wait_for(second, "error")
    assert "declined" in second.error
    await gh.aclose()


async def test_list_repos_uses_the_persons_token_and_caches(tmp_path):
    fake = FakeGitHub()
    gh = connect_for(tmp_path, fake)
    gh.machine_token = None
    with pytest.raises(LookupError, match="connect GitHub first"):
        await gh.list_repos("gil")
    gh.store.put("gil", Connection(login="gil", name="Gil", email="g@x", token="gho_secret"))
    repos = await gh.list_repos("gil")
    assert [r["full_name"] for r in repos] == ["acme/web", "acme/api"]
    assert repos[1] == {"full_name": "acme/api", "html_url": "https://github.com/acme/api", "clone_url": "https://github.com/acme/api.git", "default_branch": "develop", "private": False, "pushed_at": None, "description": "", "language": ""}
    calls = fake.polls
    assert [r["full_name"] for r in await gh.list_repos("gil", query="store")] == ["acme/web"]  # matches the description
    assert fake.polls == calls  # served from the one-minute cache
    assert gh.token_for("gil") == "gho_secret" and gh.token_for("nobody") is None
    # a revoked token is forgotten and reported
    gh.store.put("bob", Connection(login="bob", name="Bob", email="b@x", token="revoked"))
    with pytest.raises(LookupError, match="connect again"):
        await gh.list_repos("bob")
    assert gh.store.get("bob") is None
    await gh.aclose()


async def test_device_flow_disabled_on_the_app_is_explained(tmp_path):
    gh = connect_for(tmp_path, FakeGitHub(device_flow_disabled=True))
    with pytest.raises(RuntimeError, match="Enable Device Flow"):
        await gh.start("gil")
    await gh.aclose()


async def test_start_without_client_id_explains(tmp_path, monkeypatch):
    monkeypatch.delenv("MARVIN_GITHUB_CLIENT_ID", raising=False)
    gh = connect_for(tmp_path, FakeGitHub(), client_id=None)
    assert not gh.configured and gh.client_id_source is None
    with pytest.raises(RuntimeError, match="Settings"):
        await gh.start("gil")
    # an admin sets it from Settings: persisted next to the tokens, survives a restart, env still wins when present
    with pytest.raises(ValueError):
        gh.set_client_id("nope")
    gh.set_client_id(" Iv1.test ")
    assert gh.configured and gh.client_id == "Iv1.test" and gh.client_id_source == "settings"
    assert TokenStore(str(tmp_path), secret="s3").get_setting("client_id") == "Iv1.test"
    assert gh.status("gil")["configured"] and "client_id" not in gh.status("gil")
    assert gh.status("gil", admin=True)["client_id"] == "Iv1.test"
    gh.set_client_id("")
    assert not gh.configured
    gh.env_client_id = "Iv1.env"
    gh.set_client_id("Iv1.settings")
    assert gh.client_id == "Iv1.env" and gh.client_id_source == "env"
    await gh.aclose()


def test_git_identity_files(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    gh = connect_for(tmp_path, FakeGitHub())
    gh.machine_token = None
    gh.store.put("gil", Connection(login="gil", name="Gil Moreno", email="gil@example.com", token="gho_secret"))
    ident = GitIdentity(str(tmp_path), gh)
    env = ident.env("demo")
    d = tmp_path / "sandbox" / "demo" / "home" / ".marvin"  # the sandbox's room HOME: same path inside the container
    assert env == {"GIT_CONFIG_GLOBAL": str(d / "gitconfig"), "GH_CONFIG_DIR": str(d / "gh")}

    # nobody asked yet, no machine token: no identity and no credentials of ours; the included ~/.gitconfig applies
    assert ident.apply("demo", None).startswith("no GitHub credentials")
    cfg = (d / "gitconfig").read_text()
    assert "path = ~/.gitconfig" in cfg and "[user]" not in cfg and "credential" not in cfg and not (d / "token").exists()

    # Gil's turn: their name, e-mail and token; gh sees the same token
    assert ident.apply("demo", "gil") == "@gil (gil)"
    cfg = (d / "gitconfig").read_text()
    assert "name = Gil Moreno" in cfg and "email = gil@example.com" in cfg and f"cat {d / 'token'}" in cfg and "insteadOf = git@github.com:" in cfg
    assert (d / "token").read_text() == "gho_secret\n" and (d / "token").stat().st_mode & 0o777 == 0o600
    assert "oauth_token: gho_secret" in (d / "gh" / "hosts.yml").read_text() and "user: gil" in (d / "gh" / "hosts.yml").read_text()

    # someone who has not connected, with a machine token configured: shared identity
    gh.machine_token = "ghp_machine"
    assert ident.apply("demo", "guest") == "machine identity"
    assert (d / "token").read_text() == "ghp_machine\n" and "name = Marvin" in (d / "gitconfig").read_text()

    # and without either, the credentials are removed again
    gh.machine_token = None
    ident.apply("demo", "guest")
    assert not (d / "token").exists() and not (d / "gh" / "hosts.yml").exists()


def test_git_identity_without_state_dir_is_a_noop():
    ident = GitIdentity(None, None)
    assert ident.env("demo") == {} and ident.apply("demo", "gil") == "no state dir"


async def test_admin_routes_are_per_user(tmp_path):
    from marvin.admin import make_admin_app
    from marvin.room.manager import RoomManager
    from marvin.config import Config

    fake = FakeGitHub()
    gh = connect_for(tmp_path, fake, client_id=None)
    gh.env_client_id = None
    gh.set_client_id("Iv1.test")  # configured from Settings, not the environment
    mgr = RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path), session_kwargs={})
    async with TestClient(TestServer(make_admin_app(mgr, gh))) as c:
        assert (await c.get("/github/me")).status == 400  # no X-Marvin-User: the token server always sets one
        h = {"X-Marvin-User": "gil", "X-Marvin-Roles": "participant"}
        me = await (await c.get("/github/me", headers=h)).json()
        assert me["configured"] and me["connected"] is None
        r = await c.post("/github/connect", headers=h)
        assert r.status == 201
        f = await r.json()
        assert f["user_code"] == "ABCD-1234" and f["verification_uri"].startswith("https://github.com/")
        # another user cannot peek at this flow
        assert (await c.get(f"/github/connect/{f['flow']}", headers={"X-Marvin-User": "bob"})).status == 404
        await wait_for(gh.flows[f["flow"]])
        s = await (await c.get(f"/github/connect/{f['flow']}", headers=h)).json()
        assert s["status"] == "connected" and s["connected"]["login"] == "gil"
        assert (await (await c.get("/github/me", headers=h)).json())["connected"]["login"] == "gil"
        assert (await (await c.get("/github/me", headers={"X-Marvin-User": "bob"})).json())["connected"] is None
        assert (await (await c.delete("/github/me", headers=h)).json())["connected"] is None
        # the client id: participants cannot set it or see it, admins can
        assert (await c.put("/github/config", json={"client_id": "Iv1.other"}, headers=h)).status == 403
        assert "client_id" not in await (await c.get("/github/me", headers=h)).json()
        adm = {"X-Marvin-User": "root", "X-Marvin-Roles": "participant,admin"}
        assert (await c.put("/github/config", json={"client_id": "x"}, headers=adm)).status == 400
        r = await c.put("/github/config", json={"client_id": "Iv1.other"}, headers=adm)
        assert r.status == 200 and (await r.json())["client_id"] == "Iv1.other"
    await gh.aclose()
