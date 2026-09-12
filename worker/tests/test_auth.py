"""Token server authentication: header, password and none modes, roles in the LiveKit token, role checks on the admin proxy."""
import json

import jwt
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from marvin import token_server
from marvin.auth import Auth, Identity, slug

HDRS = {"X-Forwarded-User": "alice@example.com", "X-Forwarded-Email": "alice@example.com", "X-Forwarded-Preferred-Username": "Alice", "X-Forwarded-Groups": "eng,marvin-admins"}


def jwt_payload(token: str) -> dict:
    """Verify the LiveKit JWT with the API secret (what livekit-server does) and return its claims."""
    return jwt.decode(token, token_server.SECRET, algorithms=["HS256"], issuer=token_server.KEY)


def fake_upstream() -> tuple[web.Application, list]:
    """Stands in for the worker admin API: records method, path and the identity headers the proxy added."""
    seen: list = []
    app = web.Application()

    async def any_(req: web.Request) -> web.Response:
        seen.append((req.method, req.path, req.headers.get("X-Marvin-User"), req.headers.get("X-Marvin-Roles")))
        if req.path == "/rooms" and req.method == "GET":
            return web.json_response({"rooms": [{"name": "dev"}]})
        return web.json_response({"ok": True})

    app.router.add_route("*", "/{tail:.*}", any_)
    return app, seen


@pytest.fixture
async def upstream(monkeypatch):
    app, seen = fake_upstream()
    async with TestClient(TestServer(app)) as c:
        monkeypatch.setattr(token_server, "ADMIN_URL", str(c.make_url("")).rstrip("/"))
        monkeypatch.setattr(token_server, "CONFIG", None)
        yield seen


async def client(auth: Auth):
    return TestClient(TestServer(token_server.make_app(auth)))


# -- header mode ---------------------------------------------------------------------------
async def test_header_mode_requires_headers(upstream):
    async with await client(Auth("header")) as c:
        assert (await c.get("/api/token?room=dev")).status == 401
        assert (await c.get("/api/rooms")).status == 401
        j = await (await c.get("/api/me")).json()
        assert j == {"auth": "header", "identity": None}


async def test_header_mode_identity_and_admin_via_group(upstream):
    async with await client(Auth("header", admin_groups="Marvin-Admins")) as c:
        j = await (await c.get("/api/me", headers=HDRS)).json()
        assert j["identity"] == {"id": "alice-example-com", "name": "Alice", "email": "alice@example.com", "roles": ["admin", "participant"]}
        r = await c.get("/api/token?room=dev", headers=HDRS)
        assert r.status == 200
        p = jwt_payload((await r.json())["token"])
        assert p["sub"] == "alice-example-com" and p["name"] == "Alice"
        assert json.loads(p["metadata"]) == {"roles": ["admin", "participant"]}
        assert p["video"]["room"] == "dev"


async def test_header_mode_admin_via_user_list_and_name_fallbacks(upstream):
    async with await client(Auth("header", admin_users="ALICE@example.com")) as c:
        hdrs = {"X-Forwarded-User": "alice@example.com"}  # no preferred username, no email: name falls back to the user
        j = await (await c.get("/api/me", headers=hdrs)).json()
        assert j["identity"]["roles"] == ["admin", "participant"] and j["identity"]["name"] == "alice@example.com"
        hdrs = {"X-Forwarded-User": "u123", "X-Forwarded-Email": "bob@example.com"}  # name falls back to the email local part
        j = await (await c.get("/api/me", headers=hdrs)).json()
        assert j["identity"] == {"id": "u123", "name": "bob", "email": "bob@example.com", "roles": ["participant"]}


async def test_header_mode_ignores_untrusted_proxy(upstream):
    async with await client(Auth("header", trusted_proxies="10.9.9.0/24", admin_groups="marvin-admins")) as c:
        assert (await c.get("/api/token?room=dev", headers=HDRS)).status == 401  # the test client is 127.0.0.1
        assert (await (await c.get("/api/me", headers=HDRS)).json())["identity"] is None


# -- password mode ---------------------------------------------------------------------------
def pw_auth(**kw) -> Auth:
    a = Auth("password", room_password="open-sesame", admin_password="root-pw", session_secret="s3", **kw)
    a.fail_delay = 0
    return a


async def test_password_login_sets_cookie_and_identity(upstream):
    async with await client(pw_auth()) as c:
        assert (await (await c.get("/api/me")).json()) == {"auth": "password", "identity": None}
        assert (await c.get("/api/token?room=dev")).status == 401
        r = await c.post("/api/login", json={"name": "Gil Moreno", "password": "open-sesame"})
        assert r.status == 200
        ck = r.cookies["marvin_session"]
        assert ck["httponly"] and ck["samesite"] == "Lax" and ck["path"] == "/" and not ck["secure"]  # plain http test client
        assert (await r.json())["identity"] == {"id": "gil-moreno", "name": "Gil Moreno", "email": None, "roles": ["participant"]}
        j = await (await c.get("/api/me")).json()
        assert j["identity"]["id"] == "gil-moreno" and j["identity"]["roles"] == ["participant"]
        r = await c.get("/api/token?room=dev&name=Somebody+Else")  # the name query is ignored: the session decides
        assert r.status == 200
        p = jwt_payload((await r.json())["token"])
        assert p["sub"] == "gil-moreno" and p["name"] == "Gil Moreno" and json.loads(p["metadata"]) == {"roles": ["participant"]}
        assert (await c.post("/api/logout")).status == 200
        assert (await (await c.get("/api/me")).json())["identity"] is None


async def test_password_secure_cookie_behind_https_proxy(upstream):
    async with await client(pw_auth()) as c:
        r = await c.post("/api/login", json={"name": "Gil", "password": "open-sesame"}, headers={"X-Forwarded-Proto": "https"})
        assert r.cookies["marvin_session"]["secure"]


async def test_password_wrong_and_admin(upstream):
    async with await client(pw_auth()) as c:
        r = await c.post("/api/login", json={"name": "Gil", "password": "nope"})
        assert r.status == 401 and "marvin_session" not in r.cookies
        assert (await c.post("/api/login", json={"name": "", "password": "open-sesame"})).status == 401
        r = await c.post("/api/login", json={"name": "Gil", "password": "root-pw"})
        assert r.status == 200 and (await r.json())["identity"]["roles"] == ["admin", "participant"]
        p = jwt_payload((await (await c.get("/api/token?room=dev")).json())["token"])
        assert json.loads(p["metadata"]) == {"roles": ["admin", "participant"]}


async def test_password_rate_limit(upstream):
    async with await client(pw_auth()) as c:
        for _ in range(10):
            assert (await c.post("/api/login", json={"name": "Gil", "password": "nope"})).status == 401
        assert (await c.post("/api/login", json={"name": "Gil", "password": "open-sesame"})).status == 429


def test_session_token_expiry_and_tampering():
    a = pw_auth()
    ident = Identity(id="gil", name="Gil", roles=frozenset({"participant", "admin"}))
    tok = a.make_session(ident, now=1000)
    assert a.read_session(tok, now=1000 + 11 * 3600) == ident
    assert a.read_session(tok, now=1000 + 13 * 3600) is None  # expired (12 h)
    body, sig = tok.split(".")
    assert a.read_session(body + "x." + sig) is None and a.read_session(body + "." + sig[:-2] + "AA") is None
    assert a.read_session("") is None and a.read_session("garbage") is None
    assert Auth("password", room_password="x", session_secret="other").read_session(tok, now=1000) is None


async def test_expired_cookie_rejected(upstream):
    a = pw_auth(session_hours=-1)  # already expired when issued
    async with await client(a) as c:
        r = await c.post("/api/login", json={"name": "Gil", "password": "open-sesame"})
        assert r.status == 200
        assert (await (await c.get("/api/me")).json())["identity"] is None
        assert (await c.get("/api/token?room=dev")).status == 401


# -- none mode -----------------------------------------------------------------------------
def test_none_mode_refuses_non_loopback():
    Auth("none").check_startup("127.0.0.1")
    Auth("none").check_startup("localhost")
    with pytest.raises(SystemExit):
        Auth("none").check_startup("0.0.0.0")
    Auth("none", insecure_ok=True).check_startup("0.0.0.0")


def test_mode_defaults_and_validation(monkeypatch):
    for k in ("MARVIN_AUTH", "MARVIN_ROOM_PASSWORD", "MARVIN_SESSION_SECRET", "MARVIN_ADMIN_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit, match="MARVIN_AUTH is not set"):
        Auth.from_env()
    monkeypatch.setenv("MARVIN_ROOM_PASSWORD", "pw")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret")
    assert Auth.from_env().mode == "password"
    monkeypatch.setenv("MARVIN_AUTH", "bogus")
    with pytest.raises(SystemExit):
        Auth.from_env()
    monkeypatch.setenv("MARVIN_AUTH", "password")
    monkeypatch.delenv("MARVIN_ROOM_PASSWORD")
    with pytest.raises(SystemExit, match="MARVIN_ROOM_PASSWORD"):
        Auth.from_env()


async def test_none_mode_name_from_query_everyone_admin(upstream):
    async with await client(Auth("none")) as c:
        assert (await (await c.get("/api/me")).json()) == {"auth": "none", "identity": None}
        r = await c.get("/api/token?room=dev&name=Marvin")
        p = jwt_payload((await r.json())["token"])
        assert p["sub"] == "human-marvin" and json.loads(p["metadata"]) == {"roles": ["admin", "participant"]}
        assert (await c.get("/api/token?room=dev")).status == 200  # unnamed -> "dev"
        assert (await c.post("/api/rooms", json={"name": "x"})).status == 200
        assert (await c.post("/api/login", json={})).status == 404


def test_slug():
    assert slug("Gil Moreno") == "gil-moreno" and slug("  ") == "guest" and slug("MARVIN") == "human-marvin" and slug("a.b@c") == "a-b-c"


# -- admin proxy role checks -----------------------------------------------------------------
async def test_proxy_roles(upstream):
    async with await client(Auth("header", admin_users="root")) as c:
        p = {"X-Forwarded-User": "pat"}
        a = {"X-Forwarded-User": "root"}
        assert (await c.get("/api/rooms", headers=p)).status == 200
        assert (await c.get("/api/harnesses", headers=p)).status == 200
        assert (await c.post("/api/rooms", headers=p, json={"name": "x"})).status == 403
        assert (await c.patch("/api/rooms/dev", headers=p, json={"model": "m"})).status == 403
        assert (await c.delete("/api/rooms/dev", headers=p)).status == 403
        assert (await c.post("/api/repos/clone", headers=p, json={"url": "u"})).status == 403
        assert (await c.get("/api/notes", headers=p)).status == 403
        assert (await c.get("/api/harness-creds", headers=p)).status == 403
        assert (await c.put("/api/notes", headers=p, json={"text": "x"})).status == 403
        assert (await c.post("/api/rooms", headers=a, json={"name": "x"})).status == 200
        assert (await c.patch("/api/rooms/dev", headers=a, json={"model": "m"})).status == 200
        assert (await c.delete("/api/rooms/dev", headers=a)).status == 200
        assert (await c.get("/api/notes", headers=a)).status == 200
        assert (await c.get("/api/harness-creds", headers=a)).status == 200
        assert (await c.put("/api/notes", headers=a, json={"text": "x"})).status == 200
        # GitHub: connecting one's own account is self-service, the machine's client id is admin-only
        assert (await c.post("/api/github/connect", headers=p)).status == 200
        assert (await c.delete("/api/github/me", headers=p)).status == 200
        assert (await c.put("/api/github/config", headers=p, json={"client_id": "Iv1.x"})).status == 403
        assert (await c.put("/api/github/config", headers=a, json={"client_id": "Iv1.x"})).status == 200
    writes = [s for s in upstream if s[0] != "GET" and not s[1].startswith("/github/")]
    assert writes and all(s[2] == "root" and s[3] == "admin,participant" for s in writes)
    assert ("POST", "/github/connect", "pat", "participant") in upstream
    assert ("PUT", "/github/config", "root", "admin,participant") in upstream
    assert ("GET", "/rooms", "pat", "participant") in upstream
