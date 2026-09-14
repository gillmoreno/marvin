"""Marvin worker: one process, many rooms. Rooms come from rooms.yaml and/or are created at runtime via the admin API."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from marvin.adapters import registry
from marvin.admin import serve_admin
from marvin.config import Config, RoomConfig, load_config
from marvin.github import GitHubConnect, GitIdentity, TokenStore
from marvin.access import Access
from marvin.audit import Audit
from marvin.export import Exporter
from marvin.harness_creds import HarnessCreds
from marvin.license import LicenseStore, bind as bind_license
from marvin.ports import AppsRouting
from marvin.room.manager import RoomManager
from marvin.sandbox import Sandbox, SandboxConfig, SandboxError
from marvin.stt import make_stt
from marvin.themes import ThemeStore

log = logging.getLogger("marvin")


async def run(args: argparse.Namespace) -> None:
    if args.harness:
        os.environ["MARVIN_HARNESS"] = args.harness  # the registry reads the default from the environment
        if args.harness not in registry.ids():
            raise SystemExit(f"--harness {args.harness!r}: unknown; known harnesses: {', '.join(registry.ids())}")
    if args.config:
        config = load_config(args.config)
    elif args.room:
        config = Config(rooms=(RoomConfig(name=args.room, repo=args.repo, model=args.model, language=args.language),))
    else:
        config = Config(rooms=())
    if args.sandbox:
        os.environ["MARVIN_SANDBOX"] = args.sandbox
    # UI themes: custom ones live under <state>/themes, written from Settings or by the agent in any room (marvin.themes).
    themes = ThemeStore(args.state_dir)
    themes.install_docs()
    if not themes.enabled:
        log.info("themes: no --state-dir, custom themes are off (the built-in ones still work)")
    try:
        sandbox = Sandbox(SandboxConfig.from_env(), state_dir=args.state_dir, themes_dir=themes.dir)
        await sandbox.check()  # daemon reachable, image present; a clear message instead of every room failing later
    except (SandboxError, ValueError) as e:
        raise SystemExit(f"sandbox: {e}") from None
    # GitHub: per-user tokens (device flow, Settings -> Account) encrypted with the session secret; the per-turn git identity.
    secret = os.environ.get("MARVIN_SESSION_SECRET") or args.api_secret
    github = GitHubConnect(TokenStore(args.state_dir, secret=secret))
    if not github.configured:
        log.info("github: MARVIN_GITHUB_CLIENT_ID not set; 'Connect GitHub' is off, rooms use GITHUB_TOKEN / the system's git helpers")
    harness_creds = HarnessCreds(args.state_dir, secret=secret)
    licenses = LicenseStore(args.state_dir, secret=secret)
    bind_license(licenses)
    access = Access(args.state_dir, secret)
    exporter = Exporter(args.state_dir, secret)
    audit = Audit(args.state_dir, secret, on_close=lambda m, p: exporter.ship(m, p))
    lic = licenses.status()
    if lic.valid:
        log.info("license: %s (%s)", lic.message(), lic.source)
    else:
        log.info("license: core only (%s)", lic.reason or "missing")
    st = harness_creds.status()
    log.info("harness creds: default=%s (%s); keys from settings: %s",
             st["default_harness"], st["default_source"],
             ",".join(p["id"] for p in st["providers"] if p["key_source"] == "settings" or p.get("subscription_set")) or "none")
    stt = make_stt(stt_url=args.stt_url, whisper_model=args.whisper_model)
    mgr = RoomManager(
        config,
        repos_dir=args.repos_dir,
        state_dir=args.state_dir,
        routing=AppsRouting.from_env(),
        session_kwargs=dict(url=args.url, api_key=args.api_key, api_secret=args.api_secret, stt=stt, agent_name=args.name, state_dir=args.state_dir, sandbox=sandbox, git_identity=GitIdentity(args.state_dir, github), themes=themes, harness_creds=harness_creds, audit=audit),
    )
    await mgr.start_all()
    harness_creds.on_grok_session = lambda: asyncio.create_task(mgr.reload_harness("grok"))
    log.info("serving %d room(s): %s", len(mgr.sessions), ", ".join(sorted(mgr.sessions)) or "(none yet; create one from the UI)")
    runner = await serve_admin(mgr, host=args.admin_host, port=args.admin_port, github=github, themes=themes, harness_creds=harness_creds, licenses=licenses, access=access, audit=audit, exporter=exporter) if args.admin_port else None

    async def tick_audit() -> None:
        while True:
            await asyncio.sleep(15)
            audit.close_if_idle()

    idle = asyncio.create_task(tick_audit())
    try:
        await asyncio.Event().wait()
    finally:
        idle.cancel()
        await mgr.close()
        await github.aclose()
        if runner:
            await runner.cleanup()


def main() -> None:
    p = argparse.ArgumentParser(description="Marvin: a coding agent in a voice room")
    p.add_argument("--config", default=os.environ.get("MARVIN_CONFIG"), help="rooms.yaml with static rooms")
    p.add_argument("--room", default=os.environ.get("MARVIN_ROOM"), help="single static room (local dev)")
    p.add_argument("--repo", default=os.environ.get("MARVIN_REPO", os.getcwd()), help="repo for --room")
    p.add_argument("--repos-dir", default=os.environ.get("MARVIN_REPOS_DIR", "/work/repos"), help="where cloned repos live")
    p.add_argument("--url", default=os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880"))
    p.add_argument("--api-key", default=os.environ.get("LIVEKIT_API_KEY", "devkey"))
    p.add_argument("--api-secret", default=os.environ.get("LIVEKIT_API_SECRET", "secret"))
    p.add_argument("--name", default=os.environ.get("MARVIN_NAME", "Marvin"))
    p.add_argument("--model", default=os.environ.get("MARVIN_MODEL"))
    p.add_argument("--harness", default=os.environ.get("MARVIN_HARNESS"), help=f"default harness for rooms without one: {', '.join(registry.ids())}")
    p.add_argument("--whisper-model", default=os.environ.get("MARVIN_WHISPER", "small"))
    p.add_argument("--stt-url", default=os.environ.get("MARVIN_STT_URL"), help="ws://host:8765/v1/stream of the marvin-stt service; unset = local whisper")
    p.add_argument("--language", default=os.environ.get("MARVIN_LANGUAGE"))
    p.add_argument("--state-dir", default=os.environ.get("MARVIN_STATE_DIR"), help="per-room state + dynamic rooms; unset = nothing persists")
    p.add_argument("--admin-port", type=int, default=int(os.environ.get("MARVIN_ADMIN_PORT", "8090")), help="0 disables the admin API")
    p.add_argument("--admin-host", default=os.environ.get("MARVIN_ADMIN_HOST", "127.0.0.1"), help="bind address of the admin API; it has no auth of its own (the token server enforces roles), so only 127.0.0.1 or a private container network")
    p.add_argument("--sandbox", choices=["off", "docker"], default=None, help="run each room's agent in its own Docker container (MARVIN_SANDBOX; see MARVIN_SANDBOX_* for image, network, limits)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
