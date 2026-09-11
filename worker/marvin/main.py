"""Marvin worker: one process, many rooms. Rooms come from rooms.yaml and/or are created at runtime via the admin API."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from marvin.adapters import registry
from marvin.admin import serve_admin
from marvin.config import Config, RoomConfig, load_config
from marvin.ports import AppsRouting
from marvin.room.manager import RoomManager
from marvin.stt import make_stt

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
    stt = make_stt(stt_url=args.stt_url, whisper_model=args.whisper_model)
    mgr = RoomManager(
        config,
        repos_dir=args.repos_dir,
        state_dir=args.state_dir,
        routing=AppsRouting.from_env(),
        session_kwargs=dict(url=args.url, api_key=args.api_key, api_secret=args.api_secret, stt=stt, agent_name=args.name, state_dir=args.state_dir),
    )
    await mgr.start_all()
    log.info("serving %d room(s): %s", len(mgr.sessions), ", ".join(sorted(mgr.sessions)) or "(none yet; create one from the UI)")
    runner = await serve_admin(mgr, port=args.admin_port) if args.admin_port else None
    try:
        await asyncio.Event().wait()
    finally:
        await mgr.close()
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
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
