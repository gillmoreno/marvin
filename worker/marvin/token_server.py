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
from marvin.room.protocol import AGENT_IDENTITY

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
    "/api/rooms", "/api/rooms/{name}", "/api/repos", "/api/repos/clone", "/api/ports", "/api/changes", "/api/changes/file", "/api/models", "/api/harnesses", "/api/notes",
    "/api/github/me", "/api/github/connect", "/api/github/connect/{flow}", "/api/github/config",
)
ADMIN_ONLY_PREFIXES = ("/api/notes", "/api/github/config")
# Self-service: every signed-in user may write here, because it only touches their own record (keyed by X-Marvin-User).
SELF_SERVICE_PREFIXES = ("/api/github/",)


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
        return web.json_response({"error": f"worker admin unreachable: {e}"}, status=503)


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
    metadata = json.dumps({"roles": sorted(ident.roles)})  # the worker reads roles from participant.metadata (server-signed)
    jwt = api.AccessToken(KEY, SECRET).with_identity(identity).with_name(ident.name).with_metadata(metadata).with_grants(grants).to_jwt()
    return web.json_response({"serverUrl": URL, "token": jwt, "relayOnly": RELAY_ONLY, "agentName": AGENT_NAME, "identity": ident.to_wire()})


async def me(req: web.Request) -> web.Response:
    """200 whether or not the caller is signed in, so the UI can render the right screen."""
    auth = auth_of(req)
    ident = identity_of(req) if auth.mode != "none" else None  # none: the UI still asks for a name
    return web.json_response({"auth": auth.mode, "identity": ident.to_wire() if ident else None})


async def login(req: web.Request) -> web.Response:
    auth = auth_of(req)
    if auth.mode != "password":
        return web.json_response({"error": f"login is not used in {auth.mode} mode"}, status=404)
    if auth.too_many_failures(req.remote):
        return web.json_response({"error": "too many failed logins; wait a minute"}, status=429)
    try:
        body = await req.json()
        name, password = str(body.get("name", "")), str(body.get("password", ""))
    except Exception:
        return web.json_response({"error": "expected JSON {name, password}"}, status=400)
    ident = auth.login(name, password)
    if ident is None:
        auth.record_failure(req.remote)
        await asyncio.sleep(auth.fail_delay)
        return web.json_response({"error": "wrong password"}, status=401)
    resp = web.json_response({"auth": auth.mode, "identity": ident.to_wire()})
    resp.set_cookie(COOKIE, auth.make_session(ident), **cookie_kwargs(req, auth.session_seconds))
    return resp


async def logout(req: web.Request) -> web.Response:
    resp = web.json_response({"auth": auth_of(req).mode, "identity": None})
    resp.del_cookie(COOKIE, path="/")
    return resp


async def agent(req: web.Request) -> web.Response:
    return web.json_response({"name": AGENT_NAME})


async def health(req: web.Request) -> web.Response:
    return web.Response(text="ok")


def make_app(auth: Auth | None = None) -> web.Application:
    app = web.Application()
    app["auth"] = auth or Auth.from_env()
    app.router.add_get("/api/me", me)
    app.router.add_post("/api/login", login)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/api/token", token)
    for route in PROXIED:
        app.router.add_route("*", route, proxy_admin)
    app.router.add_get("/api/agent", agent)
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
