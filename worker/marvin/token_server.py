"""Web entrypoint: who you are (/api/me, /api/login), a LiveKit token for a room (/api/token?room=), the admin API behind
role checks (/api/rooms, ...), and (optionally) the built web UI. Authentication modes: marvin/auth.py."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, web
from livekit import api

from marvin.auth import ADMIN, COOKIE, Auth, Identity, cookie_kwargs
from marvin.config import load_config
from marvin.ports import AppsRouting
from marvin.room.protocol import AGENT_IDENTITY
from marvin.update import Install

KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
# "self" = the page's own origin proxies /rtc to LiveKit (Vite dev server, Caddy, or the k8s ingress).
URL = os.environ.get("LIVEKIT_PUBLIC_URL", "self")
# When clients sit behind a VPN/firewall that only lets hostnames through, the browser can reach LiveKit's TURN
# hostname but never its Pod IP: force relay candidates.
RELAY_ONLY = os.environ.get("MARVIN_ICE_RELAY_ONLY", "").lower() in ("1", "true", "yes")
AGENT_NAME = os.environ.get("MARVIN_NAME", "Marvin")  # what people say to wake the agent; shown in the UI
CONFIG = os.environ.get("MARVIN_CONFIG")
ADMIN_URL = os.environ.get("MARVIN_ADMIN_URL", "http://127.0.0.1:8090")  # the worker's admin API (same Pod / same machine / compose network)
WEB_DIST = os.environ.get("MARVIN_WEB_DIST")  # directory with the built web UI; unset in dev (Vite serves it)

# Proxied admin routes. Everything needs a session; writes need `admin`; the machine notes need `admin` even to read
# (they are a prompt-injection surface into every room).
PROXIED = (
    "/api/rooms", "/api/rooms/{name}", "/api/repos", "/api/repos/clone", "/api/ports", "/api/changes", "/api/changes/file", "/api/files", "/api/files/text", "/api/files/image", "/api/edits", "/api/models", "/api/harnesses", "/api/notes",
    "/api/setup",
    "/api/github/me", "/api/github/connect", "/api/github/connect/{flow}", "/api/github/config", "/api/github/machine", "/api/github/repos",
    "/api/harness-creds", "/api/harness-creds/default", "/api/harness-creds/{id}",
    "/api/harness-creds/grok/login", "/api/harness-creds/grok/login/{flow}",
    "/api/license",
    "/api/access",
    "/api/sessions",
    "/api/sessions/{id}",
    "/api/export",
    "/api/github/app",
    "/api/github/app/callback",
    "/api/github/app/install",
)
ADMIN_ONLY_PREFIXES = ("/api/notes", "/api/github/config", "/api/github/machine", "/api/github/app", "/api/harness-creds", "/api/update", "/api/access", "/api/export")
# Self-service: every signed-in user may write here, because it only touches their own record (keyed by X-Marvin-User).
SELF_SERVICE_PREFIXES = ("/api/github/", "/api/files/text")


def auth_of(req: web.Request) -> Auth:
    return req.app["auth"]


def identity_of(req: web.Request) -> Identity | None:
    return auth_of(req).identity_from_request(req)


async def admin_rooms() -> list[dict] | None:
    """Rooms as the worker sees them (static + dynamic); None if the worker is unreachable."""
    try:
        async with ClientSession(timeout=ClientTimeout(total=3)) as cs, cs.get(f"{ADMIN_URL}/rooms") as r:
            return (await r.json())["rooms"] if r.status == 200 else None
    except Exception:
        return None


def known_rooms() -> list[str] | None:
    if not CONFIG:
        return None
    return [r.name for r in load_config(CONFIG).rooms]


async def proxy_admin(req: web.Request) -> web.Response:
    """/api/{rooms,repos,ports,...} -> worker admin API, once the caller is known and allowed."""
    ident = identity_of(req)
    if ident is None:
        return web.json_response({"error": "not signed in"}, status=401)
    needs_admin = req.path.startswith(ADMIN_ONLY_PREFIXES) or (req.method not in ("GET", "HEAD") and not req.path.startswith(SELF_SERVICE_PREFIXES))
    if not ident.is_admin and needs_admin:
        return web.json_response({"error": "admin role required"}, status=403)
    path = req.path[len("/api"):]
    headers = {"content-type": req.content_type, "X-Marvin-User": ident.id, "X-Marvin-Roles": ",".join(sorted(ident.roles))}
    try:
        async with ClientSession(timeout=ClientTimeout(total=300)) as cs:
            async with cs.request(req.method, f"{ADMIN_URL}{path}", params=req.query, data=await req.read(), headers=headers) as r:
                body = await r.read()
                return web.Response(status=r.status, body=body, content_type=r.content_type)
    except Exception as e:
        return web.json_response({"error": _update_downtime_hint() or f"worker admin unreachable: {e}"}, status=503)


async def token(req: web.Request) -> web.Response:
    room = req.query.get("room", "").strip()
    if not room:
        return web.Response(status=400, text="room is required")
    ident = identity_of(req)
    if ident is None:
        return web.json_response({"error": "not signed in"}, status=401)
    live = await admin_rooms()
    allowed = [r["name"] for r in live] if live is not None else known_rooms()
    if allowed is not None and room not in allowed:
        return web.Response(status=404, text=f"unknown room {room!r}; rooms: {', '.join(allowed)}")
    identity = ident.id if ident.id != AGENT_IDENTITY else "human-" + ident.id
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True, can_publish_data=True)
    metadata = json.dumps({"roles": sorted(ident.roles), **({"email": ident.email} if ident.email else {})})
    jwt = api.AccessToken(KEY, SECRET).with_identity(identity).with_name(ident.name).with_metadata(metadata).with_grants(grants).to_jwt()
    return web.json_response({"serverUrl": URL, "token": jwt, "relayOnly": RELAY_ONLY, "agentName": AGENT_NAME, "identity": ident.to_wire()})


async def me(req: web.Request) -> web.Response:
    """200 whether or not the caller is signed in, so the UI can render the right screen."""
    auth = auth_of(req)
    ident = identity_of(req) if auth.mode != "none" else None  # none: the UI still asks for a name
    notice = auth.access.notice() if auth.access else None
    return web.json_response({"auth": auth.mode, "identity": ident.to_wire() if ident else None, "notice": notice})


async def login(req: web.Request) -> web.Response:
    auth = auth_of(req)
    if auth.mode != "password":
        return web.json_response({"error": f"login is not used in {auth.mode} mode"}, status=404)
    if auth.too_many_failures(req.remote):
        return web.json_response({"error": "too many failed logins; wait a minute"}, status=429)
    try:
        body = await req.json()
        who, password = str(body.get("email") or body.get("name") or ""), str(body.get("password", ""))
    except Exception:
        return web.json_response({"error": "expected JSON {email, password}"}, status=400)
    ident = auth.login(who, password)
    if ident is None:
        auth.record_failure(req.remote)
        await asyncio.sleep(auth.fail_delay)
        return web.json_response({"error": "wrong password"}, status=401)
    if not auth.email_allowed(ident.email):
        return web.json_response({"error": auth.email_refusal()}, status=403)
    resp = web.json_response({"auth": auth.mode, "identity": ident.to_wire()})
    resp.set_cookie(COOKIE, auth.make_session(ident), **cookie_kwargs(req, auth.session_seconds))
    return resp


async def logout(req: web.Request) -> web.Response:
    resp = web.json_response({"auth": auth_of(req).mode, "identity": None})
    resp.del_cookie(COOKIE, path="/")
    return resp


async def agent(req: web.Request) -> web.Response:
    routing = AppsRouting.from_env()
    return web.json_response({
        "name": AGENT_NAME,
        "public_host": routing.domain,
        "preview_pattern": routing.preview_pattern(),
    })


async def tls_ask(req: web.Request) -> web.Response:
    """Caddy on-demand TLS: 200 only for a preview host of this install (`p3000.<MARVIN_DOMAIN>`). Unauthenticated."""
    name = (req.query.get("domain") or "").strip()
    if AppsRouting.from_env().allows_preview_host(name):
        return web.Response(text="ok")
    return web.Response(status=404, text="not a preview host")


async def health(req: web.Request) -> web.Response:
    return web.Response(text="ok")


def _update_downtime_hint() -> str | None:
    """While an update is rebuilding the worker, every proxied route 503s — say why, not just 'unreachable'."""
    try:
        prog = Install.from_env().progress()
    except Exception:
        return None
    if not prog.get("applying"):
        return None
    step = prog.get("step") or "in progress"
    return f"An update is running ({step}). The worker restarts; that is expected. Settings → This machine shows the log."


async def update_status(req: web.Request) -> web.Response:
    """GET /api/update from the state volume so Settings still has a log after the worker is killed."""
    ident = identity_of(req)
    if ident is None:
        return web.json_response({"error": "not signed in"}, status=401)
    if not ident.is_admin:
        return web.json_response({"error": "admin role required"}, status=403)
    inst = Install.from_env()
    local = inst.progress()
    headers = {"X-Marvin-User": ident.id, "X-Marvin-Roles": ",".join(sorted(ident.roles))}
    try:
        async with ClientSession(timeout=ClientTimeout(total=8)) as cs:
            async with cs.get(f"{ADMIN_URL}/update", headers=headers) as r:
                if r.status == 200:
                    remote = await r.json()
                    remote["worker_up"] = True
                    remote["applying"] = bool(local.get("applying") or remote.get("applying"))
                    remote["step"] = local.get("step") or remote.get("step")
                    if local.get("log"):
                        remote["log"] = local["log"]
                    else:
                        remote.setdefault("log", "")
                    if local.get("last_error") and not remote.get("last_error"):
                        remote["last_error"] = local["last_error"]
                    if local.get("started_at") and not remote.get("started_at"):
                        remote["started_at"] = local["started_at"]
                    return web.json_response(remote)
    except Exception:
        pass
    body = inst.snapshot(worker_up=False)
    if local.get("applying"):
        body["note"] = _update_downtime_hint()
    return web.json_response(body)


def make_app(auth: Auth | None = None) -> web.Application:
    app = web.Application()
    app["auth"] = auth or Auth.from_env()
    app.router.add_get("/api/me", me)
    app.router.add_post("/api/login", login)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/api/token", token)
    app.router.add_get("/api/update", update_status)
    app.router.add_route("*", "/api/update", proxy_admin)
    for route in PROXIED:
        app.router.add_route("*", route, proxy_admin)
    app.router.add_get("/api/agent", agent)
    app.router.add_get("/tls-ask", tls_ask)
    app.router.add_get("/healthz", health)
    if WEB_DIST:
        dist = Path(WEB_DIST)
        index = dist / "index.html"

        async def spa(req: web.Request) -> web.Response:
            return web.FileResponse(index)

        app.router.add_static("/assets", dist / "assets")
        app.router.add_get("/", spa)
        app.router.add_get("/{tail:(?!api/|rtc).*}", spa)
    return app


def main() -> None:
    host = os.environ.get("MARVIN_TOKEN_HOST", "127.0.0.1")
    auth = Auth.from_env()
    auth.check_startup(host)
    web.run_app(make_app(auth), host=host, port=int(os.environ.get("MARVIN_TOKEN_PORT", "8080")))


if __name__ == "__main__":
    main()
