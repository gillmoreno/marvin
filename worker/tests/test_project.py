"""A room is a project: several repos with roles (marvin.config.ProjectRepo), created and edited as a list."""
from __future__ import annotations

import asyncio
import json
import subprocess

import pytest
from aiohttp.test_utils import TestClient, TestServer

from marvin.config import Config, ProjectRepo, RoomConfig, load_config, room_from_dict
from marvin.room import manager as mgr_mod
from marvin.room.manager import RoomManager
from tests.test_manager import FakeSession


# -- model -----------------------------------------------------------------------------------
def test_single_repo_form_is_a_one_repo_project():
    cfg = RoomConfig(name="r", repo="/w/front", git_url="https://x/front.git", branch="dev", linked=("/w/api", "/w/lib"))
    assert [r.path for r in cfg.repos] == ["/w/front", "/w/api", "/w/lib"]
    assert cfg.repos[0] == ProjectRepo(path="/w/front", git_url="https://x/front.git", branch="dev")
    assert cfg.repo == "/w/front" and cfg.linked == ("/w/api", "/w/lib") and cfg.branch == "dev"
    assert "several repos" in cfg.project_text() and "/w/api" in cfg.project_text()


def test_project_form_drives_the_derived_fields():
    cfg = RoomConfig(name="shop", repos=(
        {"path": "/w/web", "role": "frontend", "branch": "main"},  # dicts are accepted (rooms.json / API)
        ProjectRepo(path="/w/api", role="api", git_url="git@github.com:acme/api.git"),
        ProjectRepo(path="/w/web"),  # duplicates collapse
    ))
    assert cfg.repo == "/w/web" and cfg.branch == "main" and cfg.git_url is None
    assert cfg.linked == ("/w/api",) and [r.role for r in cfg.repos] == ["frontend", "api"]
    assert cfg.repo_for(None).path == "/w/web" and cfg.repo_for("/w/api").role == "api" and cfg.repo_for("/w/nope") is None
    text = cfg.project_text()
    assert "web (frontend): /w/web [branch main] <- your working directory" in text and "api (api): /w/api" in text
    assert RoomConfig(name="solo", repo="/w/one").project_text() == ""
    with pytest.raises(ValueError):
        RoomConfig(name="empty")


def test_yaml_accepts_both_forms(tmp_path):
    (tmp_path / "rooms.yaml").write_text(
        "rooms:\n"
        "  - name: old\n    repo: /w/old\n    linked: [/w/other]\n"
        "  - name: new\n    repos:\n      - {path: /w/web, role: frontend}\n      - {path: /w/api, role: api, git_url: https://github.com/acme/api, branch: dev}\n"
    )
    cfg = load_config(tmp_path / "rooms.yaml")
    assert cfg.room("old").repos == (ProjectRepo(path="/w/old"), ProjectRepo(path="/w/other"))
    assert cfg.room("new").repos[1] == ProjectRepo(path="/w/api", role="api", git_url="https://github.com/acme/api", branch="dev")
    # rooms.json written by an older worker (repo + linked, app_links, no repos key)
    old = room_from_dict({"name": "j", "repo": "/w/j", "git_url": None, "branch": None, "model": None, "harness": None, "language": None, "app_links": [{"label": "ui", "url": "http://x", "port": 3000}], "linked": ["/w/k"]})
    assert old.linked == ("/w/k",) and old.app_links[0].port == 3000


# -- manager ---------------------------------------------------------------------------------
class ReconfSession(FakeSession):
    def __init__(self, cfg, **kw):
        super().__init__(cfg, **kw)
        self.reconfigured = []

    @property
    def harness(self):
        return None

    async def reconfigure(self, cfg):
        self.cfg = cfg
        self.reconfigured.append(cfg)


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    monkeypatch.setattr(mgr_mod, "RoomSession", ReconfSession)
    monkeypatch.setattr(mgr_mod, "listening_ports", lambda: set())
    (tmp_path / "repos" / "web").mkdir(parents=True)
    (tmp_path / "repos" / "api").mkdir()
    return RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})


def test_create_project_with_roles_and_edit_it(mgr, tmp_path):
    repos = tmp_path / "repos"

    async def run():
        await mgr.start_all()
        room = await mgr.create_room("shop", repos=[{"path": "web", "role": "Frontend"}, {"path": str(repos / "api"), "role": "api", "branch": "dev"}])
        assert room["repo"] == str(repos / "web") and room["linked"] == [str(repos / "api")]
        assert [(r["name"], r["role"], r["branch"], r["exists"]) for r in room["repos"]] == [("web", "frontend", None, True), ("api", "api", "dev", True)]
        cfg = mgr.configs()["shop"]
        assert cfg.repos[0].role == "frontend" and mgr.sessions["shop"].cfg.project_text()
        # a repo that is not on the machine and has no URL is refused
        with pytest.raises(ValueError):
            await mgr.create_room("bad", repos=[{"path": "web"}, {"path": "ghost", "role": "lib"}])
        # edit: reorder (api becomes the working directory), change a role, drop web
        r = await mgr.update_room("shop", repos=[{"path": "api", "role": "backend"}])
        assert r["repo"] == str(repos / "api") and r["repos"] == [dict(r["repos"][0], role="backend")] and r["linked"] == []
        assert mgr.sessions["shop"].reconfigured[-1].repos[0].role == "backend"
        with pytest.raises(ValueError):
            await mgr.update_room("shop", repos=[])
        # the old `linked` PATCH still works and keeps the roles it knows
        r = await mgr.update_room("shop", linked=["web"])
        assert [x["name"] for x in r["repos"]] == ["api", "web"] and r["repos"][0]["role"] == "backend"
        await mgr.close()
        # persisted as a project; an old-style `linked` override is still understood
        state = json.loads((tmp_path / "state" / "rooms.json").read_text())
        assert state["rooms"][0]["repos"][0]["role"] == "frontend"  # the record as created
        assert [r["role"] for r in state["overrides"]["shop"]["repos"]] == ["backend", ""]  # the edits on top
        state["overrides"]["shop"] = {"linked": [str(repos / "api"), str(repos / "web")]}  # primary + these, roles kept from the record
        (tmp_path / "state" / "rooms.json").write_text(json.dumps(state))
        m2 = RoomManager(Config(rooms=()), repos_dir=str(repos), state_dir=str(tmp_path / "state"), session_kwargs={})
        cfg = m2.configs()["shop"]
        assert [(r.name, r.role) for r in cfg.repos] == [("web", "frontend"), ("api", "api")]

    asyncio.run(run())


def test_create_project_clones_missing_repos_with_the_requesters_token(mgr, tmp_path, monkeypatch):
    # a local bare repo stands in for GitHub; the token must reach git through the credential helper env, not argv
    src = tmp_path / "src.git"
    subprocess.run(["git", "init", "-q", "--bare", str(src)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(src), str(work)], check=True)
    (work / "README").write_text("hi")
    subprocess.run(["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-A", "-m", "init"], check=False)
    subprocess.run(["git", "-C", str(work), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"], check=True)
    subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "HEAD:main"], check=True)

    seen: list[tuple[list[str], dict]] = []
    real = asyncio.create_subprocess_exec

    async def spy(*cmd, **kw):
        seen.append((list(cmd), kw.get("env") or {}))
        return await real(*cmd, **kw)

    monkeypatch.setattr(mgr_mod.asyncio, "create_subprocess_exec", spy)

    async def run():
        await mgr.start_all()
        room = await mgr.create_room("proj", repos=[{"path": "web", "role": "frontend"}, {"git_url": str(src), "role": "api", "branch": "main"}], clone_token="tok_secret")
        assert room["repos"][1]["name"] == "src" and room["repos"][1]["exists"] and room["repos"][1]["git"]
        cmd, env = seen[-1]
        assert "tok_secret" not in " ".join(cmd) and env["MARVIN_CLONE_TOKEN"] == "tok_secret" and env["GIT_CONFIG_KEY_0"] == "credential.helper"
        await mgr.close()

    asyncio.run(run())


# -- admin API -------------------------------------------------------------------------------
async def test_admin_create_with_repos_and_changes_per_repo(tmp_path, monkeypatch):
    from marvin.admin import make_admin_app
    monkeypatch.setattr(mgr_mod, "RoomSession", ReconfSession)
    monkeypatch.setattr(mgr_mod, "listening_ports", lambda: set())
    web_dir, api_dir = tmp_path / "repos" / "web", tmp_path / "repos" / "api"
    for d in (web_dir, api_dir):
        d.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(d)], check=True)
        (d / ".keep").write_text("")
        subprocess.run(["git", "-C", str(d), "add", "."], check=True)
        subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"], check=True)
    (api_dir / "a.txt").write_text("x")
    m = RoomManager(Config(rooms=()), repos_dir=str(tmp_path / "repos"), state_dir=str(tmp_path / "state"), session_kwargs={})
    async with TestClient(TestServer(make_admin_app(m))) as c:
        r = await c.post("/rooms", json={"name": "shop", "repos": [{"path": "web", "role": "frontend"}, {"path": "api", "role": "api"}]}, headers={"X-Marvin-User": "gil"})
        assert r.status == 201, await r.text()
        assert (await c.post("/rooms", json={"name": "x", "repos": "nope"})).status == 400
        # changes default to the primary repo; ?repo= selects another project repo; anything else is a 404
        j = await (await c.get("/changes?room=shop")).json()
        assert j.get("repo") == str(web_dir) and j["files"] == [], j
        j = await (await c.get(f"/changes?room=shop&repo={api_dir}")).json()
        assert j["repo"] == str(api_dir) and [f["path"] for f in j["files"]] == ["a.txt"]
        assert (await c.get("/changes?room=shop&repo=/elsewhere")).status == 404
        assert (await c.get(f"/changes/file?room=shop&repo={api_dir}&path=a.txt")).status == 200
    await m.close()
