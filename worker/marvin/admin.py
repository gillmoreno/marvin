"""Worker admin API on 127.0.0.1:<port>: rooms, repos, ports. Reached through the web container's /api proxy."""
from __future__ import annotations

import logging

from aiohttp import web

from marvin.changes import changes as repo_changes, file_diff
from marvin.room.manager import RoomManager
from marvin import notes as notes_mod

log = logging.getLogger("marvin.admin")

# Models people can pick per room. "" (default) lets the harness decide.
DEFAULT_MODEL = "claude-fable-5-1"
MODELS = [
    {"id": "claude-fable-5-1", "label": "Fable 5.1", "note": "most capable"},
    {"id": "claude-opus-5", "label": "Opus 5", "note": "strong, cheaper"},
    {"id": "claude-sonnet-5", "label": "Sonnet 5", "note": "fast"},
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5", "note": "fastest, cheapest"},
]


def make_admin_app(mgr: RoomManager) -> web.Application:
    app = web.Application()

    async def rooms(req: web.Request) -> web.Response:
        return web.json_response({"rooms": mgr.describe()})

    async def create_room(req: web.Request) -> web.Response:
        body = await req.json()
        try:
            room = await mgr.create_room(str(body.get("name", "")).strip(), repo=body.get("repo") or None, git_url=body.get("git_url") or None, branch=body.get("branch") or None, language=body.get("language") or None)
        except (ValueError, KeyError) as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            log.exception("create room")
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=500)
        return web.json_response(room, status=201)

    async def patch_room(req: web.Request) -> web.Response:
        body = await req.json()
        try:
            room = await mgr.update_room(req.match_info["name"], model=body.get("model") or None, clear_model=body.get("model") == "", linked=body.get("linked"))
        except KeyError:
            return web.json_response({"error": "no such room"}, status=404)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            log.exception("update room")
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=500)
        return web.json_response(room)

    async def models(req: web.Request) -> web.Response:
        return web.json_response({"models": MODELS, "default": DEFAULT_MODEL})

    async def get_notes(req: web.Request) -> web.Response:
        return web.json_response({"path": str(notes_mod.notes_path()), "text": notes_mod.read_notes()})

    async def put_notes(req: web.Request) -> web.Response:
        body = await req.json()
        notes_mod.write_notes(str(body.get("text", "")))
        return web.json_response({"path": str(notes_mod.notes_path()), "text": notes_mod.read_notes()})

    async def delete_room(req: web.Request) -> web.Response:
        try:
            await mgr.delete_room(req.match_info["name"])
        except KeyError:
            return web.json_response({"error": "no such room"}, status=404)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=409)
        return web.Response(status=204)

    async def repos(req: web.Request) -> web.Response:
        return web.json_response({"repos": mgr.repos(), "dir": str(mgr.repos_dir)})

    async def clone(req: web.Request) -> web.Response:
        body = await req.json()
        try:
            return web.json_response(await mgr.clone_repo(str(body["url"]).strip(), body.get("name") or None, body.get("branch") or None), status=201)
        except (ValueError, KeyError) as e:
            return web.json_response({"error": str(e)}, status=400)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=502)

    def _repo_for(req: web.Request) -> str | None:
        cfg = mgr.configs().get(req.query.get("room", ""))
        return cfg.repo if cfg else None

    async def changes(req: web.Request) -> web.Response:
        repo = _repo_for(req)
        if not repo:
            return web.json_response({"error": "unknown room"}, status=404)
        try:
            return web.json_response((await repo_changes(repo)).to_wire())
        except Exception as e:
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=500)

    async def changes_file(req: web.Request) -> web.Response:
        repo = _repo_for(req)
        if not repo:
            return web.json_response({"error": "unknown room"}, status=404)
        try:
            return web.Response(text=await file_diff(repo, req.query.get("path", "")), content_type="text/plain")
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=500)

    async def ports(req: web.Request) -> web.Response:
        return web.json_response({"ports": mgr.ports()})

    app.router.add_get("/rooms", rooms)
    app.router.add_post("/rooms", create_room)
    app.router.add_patch("/rooms/{name}", patch_room)
    app.router.add_delete("/rooms/{name}", delete_room)
    app.router.add_get("/models", models)
    app.router.add_get("/notes", get_notes)
    app.router.add_put("/notes", put_notes)
    app.router.add_get("/repos", repos)
    app.router.add_post("/repos/clone", clone)
    app.router.add_get("/ports", ports)
    app.router.add_get("/changes", changes)
    app.router.add_get("/changes/file", changes_file)
    return app


async def serve_admin(mgr: RoomManager, host: str = "127.0.0.1", port: int = 8090) -> web.AppRunner:
    runner = web.AppRunner(make_admin_app(mgr))
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("admin api on http://%s:%d", host, port)
    return runner
