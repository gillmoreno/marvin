"""Worker admin API on 127.0.0.1:<port>: rooms, repos, ports. Reached through the web container's /api proxy."""
from __future__ import annotations

import logging
import time

from aiohttp import web

from marvin.adapters import registry
from marvin.changes import changes as repo_changes, file_diff
from marvin.github import GitHubConnect
from marvin.room.manager import RoomManager
from marvin import notes as notes_mod
from marvin.themes import ThemeStore

log = logging.getLogger("marvin.admin")


def who(req: web.Request) -> str:
    """The signed-in user, as the token server saw them (X-Marvin-User/-Roles set by its proxy); "?" when called directly."""
    user = req.headers.get("X-Marvin-User", "?")
    roles = req.headers.get("X-Marvin-Roles", "")
    return f"{user} [{roles}]" if roles else user


def make_admin_app(mgr: RoomManager, github: GitHubConnect | None = None, themes: ThemeStore | None = None) -> web.Application:
    app = web.Application()
    themes = themes or ThemeStore(None)

    # -- GitHub connection (self-service: the token server lets every signed-in user call /github/*) --------------
    def _user(req: web.Request) -> str | None:
        u = req.headers.get("X-Marvin-User", "").strip()
        return u if u and u != "?" else None

    def _is_admin(req: web.Request) -> bool:
        return "admin" in req.headers.get("X-Marvin-Roles", "").split(",")

    async def github_me(req: web.Request) -> web.Response:
        if github is None:
            return web.json_response({"configured": False, "connected": None, "machine_identity": False})
        user = _user(req)
        if not user:
            return web.json_response({"error": "no signed-in user"}, status=400)
        if req.query.get("verify") and github.store.get(user):
            await github.verify(user)
        return web.json_response(github.status(user, admin=_is_admin(req)))

    async def github_config(req: web.Request) -> web.Response:
        """Admin sets the OAuth App client id from Settings (the token server only lets admins through; checked again here)."""
        if github is None:
            return web.json_response({"error": "GitHub connection is not available"}, status=501)
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        body = await req.json()
        try:
            github.set_client_id(body.get("client_id"))
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        log.info("%s sets the GitHub client id (%s)", who(req), "cleared" if not github.client_id else "set")
        return web.json_response(github.status(_user(req) or "?", admin=True))

    async def github_connect(req: web.Request) -> web.Response:
        if github is None:
            return web.json_response({"error": "GitHub connection is not available"}, status=501)
        user = _user(req)
        if not user:
            return web.json_response({"error": "no signed-in user"}, status=400)
        try:
            flow = await github.start(user)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=503)
        log.info("%s starts a GitHub device flow", who(req))
        return web.json_response({"flow": flow.id, "user_code": flow.user_code, "verification_uri": flow.verification_uri, "expires_in": int(flow.expires_at - time.time()), "interval": flow.interval}, status=201)

    async def github_flow(req: web.Request) -> web.Response:
        if github is None:
            return web.json_response({"error": "GitHub connection is not available"}, status=501)
        user = _user(req)
        flow = github.get_flow(req.match_info["flow"], user or "")
        if not flow:
            return web.json_response({"error": "no such flow"}, status=404)
        return web.json_response({"status": flow.status, "error": flow.error, "connected": flow.connection.public() if flow.connection else None})

    async def github_disconnect(req: web.Request) -> web.Response:
        if github is None:
            return web.json_response({"error": "GitHub connection is not available"}, status=501)
        user = _user(req)
        if not user:
            return web.json_response({"error": "no signed-in user"}, status=400)
        github.disconnect(user)
        log.info("%s disconnects GitHub", who(req))
        return web.json_response(github.status(user))

    async def github_repos(req: web.Request) -> web.Response:
        if github is None:
            return web.json_response({"error": "GitHub connection is not available"}, status=501)
        try:
            repos = await github.list_repos(_user(req), query=req.query.get("q", "").strip())
        except LookupError as e:
            return web.json_response({"error": str(e), "repos": []}, status=409)
        except Exception as e:
            return web.json_response({"error": f"GitHub: {type(e).__name__}: {e}"}, status=502)
        return web.json_response({"repos": repos})

    app.router.add_get("/github/repos", github_repos)
    app.router.add_get("/github/me", github_me)
    app.router.add_put("/github/config", github_config)
    app.router.add_delete("/github/me", github_disconnect)
    app.router.add_post("/github/connect", github_connect)
    app.router.add_get("/github/connect/{flow}", github_flow)

    async def rooms(req: web.Request) -> web.Response:
        return web.json_response({"rooms": mgr.describe()})

    def _clone_token(req: web.Request) -> str | None:
        """Clones run with the requester's connected GitHub account, else the machine's token."""
        return github.token_for(_user(req)) if github else None

    async def create_room(req: web.Request) -> web.Response:
        body = await req.json()
        log.info("%s creates room %r", who(req), body.get("name"))
        repos = body.get("repos")
        if repos is not None and not isinstance(repos, list):
            return web.json_response({"error": "repos must be a list"}, status=400)
        try:
            room = await mgr.create_room(
                str(body.get("name", "")).strip(), repo=body.get("repo") or None, git_url=body.get("git_url") or None, branch=body.get("branch") or None,
                language=body.get("language") or None, repos=repos or None, clone_token=_clone_token(req),
            )
        except (ValueError, KeyError) as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            log.exception("create room")
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=500)
        return web.json_response(room, status=201)

    async def patch_room(req: web.Request) -> web.Response:
        body = await req.json()
        log.info("%s updates room %s: %s", who(req), req.match_info["name"], body)
        try:
            room = await mgr.update_room(
                req.match_info["name"],
                model=body.get("model") or None, clear_model=body.get("model") == "",
                harness=body.get("harness") or None, clear_harness=body.get("harness") == "",
                linked=body.get("linked"), repos=body.get("repos"), clone_token=_clone_token(req),
            )
        except KeyError:
            return web.json_response({"error": "no such room"}, status=404)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            log.exception("update room")
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=500)
        return web.json_response(room)

    async def models(req: web.Request) -> web.Response:
        """Models people can pick per room. With `room=`, a live agent that reports its own models (ACP configOptions /
        availableModels) wins over the profile's static list; otherwise the list of `harness=` (default: the worker's
        default harness). "" lets the harness decide."""
        live = mgr.live_models(req.query.get("room", ""))
        if live is not None:
            return web.json_response(live)
        try:
            p = registry.get(req.query.get("harness") or None)
        except KeyError as e:
            return web.json_response({"error": str(e)}, status=404)
        return web.json_response({"harness": p.id, "models": p.models, "default": p.default_model or ""})

    async def harnesses(req: web.Request) -> web.Response:
        return web.json_response({"harnesses": [p.to_wire() for p in registry.profiles()], "default": registry.default_id()})

    async def get_notes(req: web.Request) -> web.Response:
        return web.json_response({"path": str(notes_mod.notes_path()), "text": notes_mod.read_notes()})

    async def put_notes(req: web.Request) -> web.Response:
        body = await req.json()
        log.info("%s writes the machine notes (%d chars)", who(req), len(str(body.get("text", ""))))
        notes_mod.write_notes(str(body.get("text", "")))
        return web.json_response({"path": str(notes_mod.notes_path()), "text": notes_mod.read_notes()})

    async def delete_room(req: web.Request) -> web.Response:
        log.info("%s deletes room %s", who(req), req.match_info["name"])
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
        log.info("%s clones %s", who(req), body.get("url"))
        try:
            return web.json_response(await mgr.clone_repo(str(body["url"]).strip(), body.get("name") or None, body.get("branch") or None, clone_token=_clone_token(req)), status=201)
        except (ValueError, KeyError) as e:
            return web.json_response({"error": str(e)}, status=400)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=502)

    def _repo_for(req: web.Request) -> str | None:
        """The repo a Changes request is about: ?repo=<path> must be one of the room's project repos; default primary."""
        cfg = mgr.configs().get(req.query.get("room", ""))
        if not cfg:
            return None
        r = cfg.repo_for(req.query.get("repo") or None)
        return r.path if r else None

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

    # -- UI themes: custom ones under <state>/themes (the agent writes them), plus the machine default ---------------
    async def list_themes(req: web.Request) -> web.Response:
        return web.json_response(themes.describe())

    async def theme_css(req: web.Request) -> web.Response:
        css = themes.css(req.match_info["id"])
        if css is None:
            return web.json_response({"error": "no such theme, or it is invalid"}, status=404)
        return web.Response(text=css, content_type="text/css", headers={"Cache-Control": "no-cache"})

    async def put_default_theme(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        body = await req.json()
        theme_id = body.get("id")
        try:
            themes.set_default(str(theme_id) if theme_id else None)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        log.info("%s sets the default theme to %s", who(req), theme_id or "(app default)")
        return web.json_response(themes.describe())

    async def delete_theme(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        try:
            themes.delete(req.match_info["id"])
        except KeyError:
            return web.json_response({"error": "no such theme"}, status=404)
        log.info("%s deletes theme %s", who(req), req.match_info["id"])
        return web.json_response(themes.describe())

    app.router.add_get("/themes", list_themes)
    app.router.add_put("/themes/default", put_default_theme)
    app.router.add_get("/themes/{id}/theme.css", theme_css)
    app.router.add_delete("/themes/{id}", delete_theme)

    app.router.add_get("/rooms", rooms)
    app.router.add_post("/rooms", create_room)
    app.router.add_patch("/rooms/{name}", patch_room)
    app.router.add_delete("/rooms/{name}", delete_room)
    app.router.add_get("/models", models)
    app.router.add_get("/harnesses", harnesses)
    app.router.add_get("/notes", get_notes)
    app.router.add_put("/notes", put_notes)
    app.router.add_get("/repos", repos)
    app.router.add_post("/repos/clone", clone)
    app.router.add_get("/ports", ports)
    app.router.add_get("/changes", changes)
    app.router.add_get("/changes/file", changes_file)
    return app


async def serve_admin(mgr: RoomManager, host: str = "127.0.0.1", port: int = 8090, github: GitHubConnect | None = None, themes: ThemeStore | None = None) -> web.AppRunner:
    runner = web.AppRunner(make_admin_app(mgr, github, themes))
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("admin api on http://%s:%d", host, port)
    return runner
