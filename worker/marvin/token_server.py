"""Web entrypoint: GET /api/token?room=dev&name=Gil, GET /api/rooms, and (optionally) the built web UI."""
from __future__ import annotations

import os
import re
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, web
from livekit import api

from marvin.config import load_config
from marvin.room.protocol import AGENT_IDENTITY

KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
# "self" = the page's own origin proxies /rtc to LiveKit (Vite dev server or the k8s ingress).
URL = os.environ.get("LIVEKIT_PUBLIC_URL", "self")
# When clients sit behind a VPN/firewall that only lets hostnames through, the browser can reach LiveKit's TURN
# hostname but never its Pod IP: force relay candidates.
RELAY_ONLY = os.environ.get("MARVIN_ICE_RELAY_ONLY", "").lower() in ("1", "true", "yes")
AGENT_NAME = os.environ.get("MARVIN_NAME", "Marvin")  # what people say to wake the agent; shown in the UI
CONFIG = os.environ.get("MARVIN_CONFIG")
ADMIN = os.environ.get("MARVIN_ADMIN_URL", "http://127.0.0.1:8090")  # the worker's admin API (same Pod / same machine)
WEB_DIST = os.environ.get("MARVIN_WEB_DIST")  # directory with the built web UI; unset in dev (Vite serves it)


async def admin_rooms() -> list[dict] | None:
    """Rooms as the worker sees them (static + dynamic); None if the worker is unreachable."""
    try:
        async with ClientSession(timeout=ClientTimeout(total=3)) as cs, cs.get(f"{ADMIN}/rooms") as r:
            return (await r.json())["rooms"] if r.status == 200 else None
    except Exception:
        return None


def known_rooms() -> list[str] | None:
    if not CONFIG:
        return None
    return [r.name for r in load_config(CONFIG).rooms]


async def proxy_admin(req: web.Request) -> web.Response:
    """GET/POST/DELETE /api/{rooms,repos,ports}... -> worker admin API."""
    path = req.path[len("/api"):]
    try:
        async with ClientSession(timeout=ClientTimeout(total=300)) as cs:
            async with cs.request(req.method, f"{ADMIN}{path}", params=req.query, data=await req.read(), headers={"content-type": req.content_type}) as r:
                body = await r.read()
                return web.Response(status=r.status, body=body, content_type=r.content_type)
    except Exception as e:
        return web.json_response({"error": f"worker admin unreachable: {e}"}, status=503)


async def token(req: web.Request) -> web.Response:
    room = req.query.get("room", "").strip()
    name = req.query.get("name", "").strip()
    if not room or not name:
        return web.Response(status=400, text="room and name are required")
    live = await admin_rooms()
    allowed = [r["name"] for r in live] if live is not None else known_rooms()
    if allowed is not None and room not in allowed:
        return web.Response(status=404, text=f"unknown room {room!r}; rooms: {', '.join(allowed)}")
    identity = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-") or "guest"
    if identity == AGENT_IDENTITY:
        identity = "human-" + identity
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True, can_publish_data=True)
    jwt = api.AccessToken(KEY, SECRET).with_identity(identity).with_name(name).with_grants(grants).to_jwt()
    return web.json_response({"serverUrl": URL, "token": jwt, "relayOnly": RELAY_ONLY, "agentName": AGENT_NAME})


async def agent(req: web.Request) -> web.Response:
    return web.json_response({"name": AGENT_NAME})


async def health(req: web.Request) -> web.Response:
    return web.Response(text="ok")


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/token", token)
    for route in ("/api/rooms", "/api/rooms/{name}", "/api/repos", "/api/repos/clone", "/api/ports", "/api/changes", "/api/changes/file", "/api/models", "/api/harnesses", "/api/notes"):
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
    web.run_app(make_app(), host=os.environ.get("MARVIN_TOKEN_HOST", "127.0.0.1"), port=int(os.environ.get("MARVIN_TOKEN_PORT", "8080")))


if __name__ == "__main__":
    main()
