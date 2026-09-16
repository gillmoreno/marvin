"""Worker admin API on 127.0.0.1:<port>: rooms, repos, ports. Reached through the web container's /api proxy."""
from __future__ import annotations

import logging
import time

from aiohttp import web

from marvin.adapters import registry
from marvin.changes import changes as repo_changes, file_diff
from marvin.github import GitHubConnect
from marvin.harness_creds import HarnessCreds
from marvin.access import Access
from marvin.audit import Audit
from marvin.export import Exporter
from marvin.license import LicenseStore
from marvin.room.manager import RoomManager
from marvin import notes as notes_mod
from marvin.update import Install

log = logging.getLogger("marvin.admin")


def who(req: web.Request) -> str:
    """The signed-in user, as the token server saw them (X-Marvin-User/-Roles set by its proxy); "?" when called directly."""
    user = req.headers.get("X-Marvin-User", "?")
    roles = req.headers.get("X-Marvin-Roles", "")
    return f"{user} [{roles}]" if roles else user


def make_admin_app(mgr: RoomManager, github: GitHubConnect | None = None, harness_creds: HarnessCreds | None = None, install: Install | None = None, licenses: LicenseStore | None = None, access: Access | None = None, audit: Audit | None = None, exporter: Exporter | None = None) -> web.Application:
    app = web.Application()
    install = install or Install.from_env()
    licenses = licenses or LicenseStore(None, secret="dev")
    access = access or Access(None, "dev")
    exporter = exporter or Exporter(None, "dev")

    # -- GitHub connection (self-service: the token server lets every signed-in user call /github/*) --------------
    def _user(req: web.Request) -> str | None:
        u = req.headers.get("X-Marvin-User", "").strip()
        return u if u and u != "?" else None

    def _is_admin(req: web.Request) -> bool:
        return "admin" in req.headers.get("X-Marvin-Roles", "").split(",")

    async def github_me(req: web.Request) -> web.Response:
        if github is None:
            return web.json_response({"configured": False, "connected": None, "machine_identity": False, "machine": None})
        user = _user(req)
        if not user:
            return web.json_response({"error": "no signed-in user"}, status=400)
        if req.query.get("verify") and github.store.get(user):
            await github.verify(user)
        return web.json_response(github.status(user, admin=_is_admin(req)))

    async def github_token(req: web.Request) -> web.Response:
        """Paste a PAT as this person's optional GitHub."""
        if github is None:
            return web.json_response({"error": "GitHub connection is not available"}, status=501)
        user = _user(req)
        if not user:
            return web.json_response({"error": "no signed-in user"}, status=400)
        body = await req.json()
        try:
            await github.connect_token(user, str(body.get("token", "")))
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            return web.json_response({"error": f"GitHub: {type(e).__name__}: {e}"}, status=502)
        log.info("%s pastes a personal GitHub token", who(req))
        return web.json_response(github.status(user, admin=_is_admin(req)))

    async def github_machine(req: web.Request) -> web.Response:
        """Admin sets or clears the shared machine GitHub account."""
        if github is None:
            return web.json_response({"error": "GitHub connection is not available"}, status=501)
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        user = _user(req) or "?"
        if req.method == "DELETE":
            github.forget_machine()
            log.info("%s clears the machine GitHub account", who(req))
            return web.json_response(github.status(user, admin=True))
        body = await req.json()
        try:
            await github.connect_machine_token(str(body.get("token", "")))
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            return web.json_response({"error": f"GitHub: {type(e).__name__}: {e}"}, status=502)
        log.info("%s sets the machine GitHub account", who(req))
        return web.json_response(github.status(user, admin=True))

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
        dest = "machine" if req.query.get("dest") == "machine" else "user"
        if dest == "machine" and not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        try:
            flow = await github.start(user, dest=dest)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=503)
        log.info("%s starts a GitHub device flow (%s)", who(req), dest)
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
        return web.json_response(github.status(user, admin=_is_admin(req)))

    async def github_repos(req: web.Request) -> web.Response:
        if github is None:
            return web.json_response({"error": "GitHub connection is not available"}, status=501)
        q = req.query.get("q", "").strip()
        if github.app.public().get("installed"):
            try:
                return web.json_response({"repos": await github.app.repos(q)})
            except Exception as e:
                return web.json_response({"error": f"GitHub App: {e}", "repos": []}, status=502)
        try:
            repos = await github.list_repos(_user(req), query=q)
        except LookupError as e:
            return web.json_response({"error": str(e), "repos": []}, status=409)
        except Exception as e:
            return web.json_response({"error": f"GitHub: {type(e).__name__}: {e}"}, status=502)
        return web.json_response({"repos": repos})

    async def setup(req: web.Request) -> web.Response:
        """Join-gate status: machine GitHub and a coding agent are required; personal GitHub is not."""
        user = _user(req)
        if not user:
            return web.json_response({"error": "no signed-in user"}, status=400)
        machine = github.machine_public() if github else None
        personal = github.store.get(user).public() if github and github.store.get(user) else None
        agent = _creds().ready() if _creds() else {"ready": False, "label": None, "default_harness": None}
        return web.json_response({
            "ready": bool(machine) and bool(agent.get("ready")),
            "machine_github": machine,
            "agent": agent,
            "personal": personal,
            "oauth_configured": bool(github and github.configured),
        })

    app.router.add_get("/setup", setup)
    app.router.add_get("/github/repos", github_repos)
    app.router.add_get("/github/me", github_me)
    app.router.add_put("/github/me", github_token)
    app.router.add_put("/github/config", github_config)
    app.router.add_put("/github/machine", github_machine)
    app.router.add_delete("/github/machine", github_machine)
    app.router.add_delete("/github/me", github_disconnect)
    app.router.add_post("/github/connect", github_connect)
    app.router.add_get("/github/connect/{flow}", github_flow)

    # -- Coding-agent credentials (admin-only: machine-wide keys / Grok subscription) ----------------
    def _creds() -> HarnessCreds | None:
        return harness_creds

    async def harness_status(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        if _creds() is None:
            return web.json_response({"error": "harness credentials are not available"}, status=501)
        return web.json_response(_creds().status())

    async def harness_put_key(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        if _creds() is None:
            return web.json_response({"error": "harness credentials are not available"}, status=501)
        body = await req.json()
        try:
            _creds().put_key(req.match_info["id"], str(body.get("key", "")))
        except KeyError as e:
            return web.json_response({"error": str(e)}, status=404)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        log.info("%s sets the %s harness key", who(req), req.match_info["id"])
        return web.json_response(_creds().status())

    async def harness_forget_key(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        if _creds() is None:
            return web.json_response({"error": "harness credentials are not available"}, status=501)
        try:
            _creds().forget_key(req.match_info["id"])
        except KeyError as e:
            return web.json_response({"error": str(e)}, status=404)
        log.info("%s clears the %s harness key", who(req), req.match_info["id"])
        return web.json_response(_creds().status())

    async def harness_default(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        if _creds() is None:
            return web.json_response({"error": "harness credentials are not available"}, status=501)
        body = await req.json()
        try:
            hid = body.get("harness")
            _creds().set_default_harness(str(hid) if hid else None)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        log.info("%s sets the default harness to %s", who(req), body.get("harness") or "(builtin)")
        return web.json_response(_creds().status())

    async def grok_login(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        if _creds() is None:
            return web.json_response({"error": "harness credentials are not available"}, status=501)
        try:
            flow = await _creds().start_grok_login()
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=503)
        log.info("%s starts a Grok device login", who(req))
        return web.json_response(flow.public(), status=201)

    async def grok_flow(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        if _creds() is None:
            return web.json_response({"error": "harness credentials are not available"}, status=501)
        flow = _creds().get_flow(req.match_info["flow"])
        if not flow:
            return web.json_response({"error": "no such flow"}, status=404)
        return web.json_response(flow.public())

    async def grok_logout(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        if _creds() is None:
            return web.json_response({"error": "harness credentials are not available"}, status=501)
        _creds().forget_grok_session()
        log.info("%s disconnects the Grok subscription", who(req))
        return web.json_response(_creds().status())

    app.router.add_get("/harness-creds", harness_status)
    app.router.add_put("/harness-creds/default", harness_default)
    app.router.add_post("/harness-creds/grok/login", grok_login)
    app.router.add_get("/harness-creds/grok/login/{flow}", grok_flow)
    app.router.add_delete("/harness-creds/grok/login", grok_logout)
    app.router.add_put("/harness-creds/{id}", harness_put_key)
    app.router.add_delete("/harness-creds/{id}", harness_forget_key)

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

    async def update_status(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        return web.json_response(await install.describe())

    async def update_apply(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        try:
            return web.json_response(install.start(), status=202)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=409)

    app.router.add_get("/update", update_status)
    app.router.add_post("/update", update_apply)

    async def license_status(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        return web.json_response(licenses.status().public())

    async def license_put(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        try:
            body = await req.json()
            key = str(body.get("key") or "")
        except Exception:
            return web.json_response({"error": "expected JSON {key}"}, status=400)
        try:
            return web.json_response(licenses.put(key).public())
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=409)

    async def license_clear(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        try:
            return web.json_response(licenses.clear().public())
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=409)

    app.router.add_get("/license", license_status)
    app.router.add_put("/license", license_put)
    app.router.add_delete("/license", license_clear)

    async def access_get(req: web.Request) -> web.Response:
        return web.json_response(access.public(admin=_is_admin(req)))

    async def access_put(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        try:
            body = await req.json()
        except Exception:
            return web.json_response({"error": "expected JSON"}, status=400)
        sso_set = any(str(body.get(k) or "").strip() for k in ("issuer", "client_id", "client_secret", "cookie_secret"))
        if sso_set and not licenses.status().allows("sso"):
            return web.json_response({"error": "OIDC / SSO needs a Marvin Enterprise license. Paste it in Settings → Enterprise.", "feature": "sso"}, status=403)
        return web.json_response(access.put(body))

    async def sessions_list(req: web.Request) -> web.Response:
        if audit is None:
            return web.json_response({"sessions": []})
        return web.json_response({
            "sessions": audit.list(room=req.query.get("room") or None, who=_user(req), admin=_is_admin(req)),
            "retention_days": audit.retention_days,
        })

    async def session_get(req: web.Request) -> web.Response:
        if audit is None:
            return web.json_response({"error": "no audit"}, status=404)
        data = audit.read(req.match_info["id"], who=_user(req), admin=_is_admin(req))
        if not data:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(data)

    async def sessions_retention(req: web.Request) -> web.Response:
        if not _is_admin(req) or audit is None:
            return web.json_response({"error": "admin role required"}, status=403)
        body = await req.json()
        return web.json_response({"retention_days": audit.set_retention(int(body.get("days") or 90))})

    async def export_get(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        return web.json_response(exporter.public())

    async def export_put(req: web.Request) -> web.Response:
        if not _is_admin(req):
            return web.json_response({"error": "admin role required"}, status=403)
        try:
            body = await req.json()
        except Exception:
            return web.json_response({"error": "expected JSON"}, status=400)
        shipping = any(str(body.get(k) or "").strip() for k in ("bucket", "webhook", "access_key"))
        if shipping and not licenses.status().allows("audit"):
            return web.json_response({"error": "Audit export needs a Marvin Enterprise license. Paste it in Settings → Enterprise.", "feature": "audit"}, status=403)
        return web.json_response(exporter.put(body))

    def _app_origin(req: web.Request) -> str:
        origin = req.query.get("origin") or req.headers.get("X-Forwarded-Host") or ""
        proto = req.headers.get("X-Forwarded-Proto") or "https"
        if origin and "://" not in origin:
            origin = f"{proto}://{origin}"
        return origin or "https://localhost"

    def _app_done(message: str, *, error: str | None = None) -> web.Response:
        loc = "/?github_app=1"
        if error:
            body = f"<!doctype html><p>{error}</p><p><a href=\"/\">Back to Marvin</a></p>"
            return web.Response(text=body, content_type="text/html", status=400)
        body = f"<!doctype html><meta http-equiv=\"refresh\" content=\"0;url={loc}\"><p>{message} <a href=\"{loc}\">Back to Marvin</a></p>"
        return web.Response(text=body, content_type="text/html")

    async def github_app_get(req: web.Request) -> web.Response:
        if not _is_admin(req) or github is None:
            return web.json_response({"error": "admin role required"}, status=403)
        if not licenses.status().valid:
            return web.json_response({"error": "A GitHub App needs a Marvin Enterprise license. Paste it in Settings → Enterprise."}, status=403)
        origin = _app_origin(req)
        return web.json_response({**github.app.public(), "manifest": github.app.manifest(origin)})

    async def github_app_callback(req: web.Request) -> web.Response:
        if github is None:
            return _app_done("", error="GitHub App is not available on this machine.")
        if not licenses.status().valid:
            return _app_done("", error="A GitHub App needs a Marvin Enterprise license.")
        code = req.query.get("code") or ""
        inst = req.query.get("installation_id") or ""
        if inst:
            github.app.set_installation(inst)
            return _app_done("GitHub App installed.")
        if not code:
            return _app_done("", error="GitHub did not send a manifest code.")
        try:
            await github.app.convert(code)
            return _app_done("GitHub App created. Install it on the org if GitHub has not already sent you there.")
        except Exception as e:
            return _app_done("", error=str(e))

    async def github_app_install(req: web.Request) -> web.Response:
        if not _is_admin(req) or github is None:
            return web.json_response({"error": "admin role required"}, status=403)
        body = await req.json()
        if body.get("installation_id"):
            return web.json_response(github.app.set_installation(str(body["installation_id"])))
        return web.json_response({"error": "installation_id required"}, status=400)

    app.router.add_get("/access", access_get)
    app.router.add_put("/access", access_put)
    app.router.add_get("/sessions", sessions_list)
    app.router.add_put("/sessions", sessions_retention)
    app.router.add_get("/sessions/{id}", session_get)
    app.router.add_get("/export", export_get)
    app.router.add_put("/export", export_put)
    app.router.add_get("/github/app", github_app_get)
    app.router.add_get("/github/app/callback", github_app_callback)
    app.router.add_put("/github/app/install", github_app_install)
    app.router.add_get("/github/app/install", github_app_callback)
    return app


async def serve_admin(mgr: RoomManager, host: str = "127.0.0.1", port: int = 8090, github: GitHubConnect | None = None, harness_creds: HarnessCreds | None = None, install: Install | None = None, licenses: LicenseStore | None = None, access: Access | None = None, audit: Audit | None = None, exporter: Exporter | None = None) -> web.AppRunner:
    runner = web.AppRunner(make_admin_app(mgr, github, harness_creds, install, licenses, access, audit, exporter))
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("admin api on http://%s:%d", host, port)
    return runner
