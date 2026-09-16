"""One RoomSession per room: LiveKit connection, per-speaker STT, conductor, harness, saved session id."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import numpy as np
from livekit import api, rtc

from marvin.adapters import registry
from marvin.adapters.base import Harness
from marvin.adapters.registry import create_harness
from marvin.bridge import Timeline
from marvin.config import RoomConfig
from marvin.audit import Audit
from marvin.github import GitIdentity
from marvin.harness_creds import HarnessCreds
from marvin.sandbox import Sandbox
from marvin.stt import SegmenterFactory

from .conductor import Conductor
from .protocol import AGENT_IDENTITY, TOPIC_CONTROL, TOPIC_EVENTS, decode, encode

log = logging.getLogger("marvin.session")


def agent_token(api_key: str, api_secret: str, room: str, name: str) -> str:
    grants = api.VideoGrants(room_join=True, room=room, can_subscribe=True, can_publish=False, can_publish_data=True)
    return api.AccessToken(api_key, api_secret).with_identity(AGENT_IDENTITY).with_name(name).with_grants(grants).to_jwt()


def roles_of(participant: rtc.RemoteParticipant) -> frozenset[str]:
    """Roles the token server put in the participant's (server-signed) metadata: {"roles": ["participant", "admin"]}.
    Empty, missing or malformed metadata means no roles."""
    try:
        meta = json.loads(participant.metadata or "")
        roles = meta.get("roles") if isinstance(meta, dict) else None
        return frozenset(str(r) for r in roles) if isinstance(roles, list) else frozenset()
    except Exception:
        return frozenset()


def git_url_for_clone(url: str) -> str:
    """git@github.com:org/repo.git -> https://github.com/org/repo.git when we authenticate with GITHUB_TOKEN."""
    if os.environ.get("GITHUB_TOKEN") and url.startswith("git@github.com:"):
        return "https://github.com/" + url[len("git@github.com:"):]
    return url


def ensure_repo(cfg: RoomConfig) -> None:
    """Every project repo exists before the harness starts: clone the ones with a git_url (static rooms; dynamic
    ones were cloned at creation with the requester's token), create the primary when it is a fresh empty project."""
    for i, r in enumerate(cfg.repos):
        path = Path(r.path)
        if path.exists():
            continue
        if r.git_url:
            path.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["git", "clone", *(["--branch", r.branch] if r.branch else []), git_url_for_clone(r.git_url), str(path)]
            log.info("room %s: %s", cfg.name, " ".join(cmd))
            subprocess.run(cmd, check=True)
        elif i == 0:
            # No repo to clone: start as an empty project so the room is usable (and Marvin can `git clone` on request).
            log.warning("room %s: %s does not exist and no git_url set; creating an empty directory", cfg.name, r.path)
            path.mkdir(parents=True, exist_ok=True)
        else:
            log.warning("room %s: project repo %s does not exist on this machine", cfg.name, r.path)


class RoomSession:
    def __init__(
        self,
        cfg: RoomConfig,
        *,
        url: str,
        api_key: str,
        api_secret: str,
        stt: SegmenterFactory,
        agent_name: str = "Marvin",
        state_dir: str | None = None,
        sandbox: Sandbox | None = None,
        git_identity: GitIdentity | None = None,
        harness_creds: HarnessCreds | None = None,
        audit: Audit | None = None,
    ) -> None:
        self.cfg = cfg
        self.url, self.api_key, self.api_secret = url, api_key, api_secret
        self.stt = stt
        self.agent_name = agent_name
        self.sandbox = sandbox if sandbox and sandbox.cfg.enabled else None
        self.git_identity = git_identity
        self.harness_creds = harness_creds
        self.audit = audit
        self.state_file = Path(state_dir) / f"{cfg.name}.json" if state_dir else None
        self.room = rtc.Room()
        self.consumers: dict[str, asyncio.Task] = {}
        self.conductor: Conductor | None = None

    # -- persisted state ---------------------------------------------------------
    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text()) if self.state_file and self.state_file.exists() else {}
        except Exception:
            return {}

    def _save_state(self, **kv) -> None:
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({**self._load_state(), **kv}))

    @staticmethod
    def harness_id(cfg: RoomConfig) -> str:
        return cfg.harness or registry.default_id()

    def _make_harness(self, cfg: RoomConfig, resume: str | None) -> Harness:
        env = {
            **(self.harness_creds.env() if self.harness_creds else {}),
            **(self.git_identity.env(cfg.name) if self.git_identity else {}),
        }
        if self.harness_creds:
            home = self.sandbox.home_dir(cfg.name) if self.sandbox else Path.home()
            self.harness_creds.install_home(home)
            env.setdefault("GROK_HOME", str(home / ".grok"))
        return create_harness(
            self.harness_id(cfg), cfg.repo, agent_name=self.agent_name, room=cfg.name, model=cfg.model, resume=resume, add_dirs=list(cfg.linked), permissions=None,
            sandbox=self.sandbox.for_room(cfg) if self.sandbox else None,
            env=env or None,
            project=cfg.project_text(),
        )

    def identity_of(self, name: str) -> str | None:
        """Marvin identity id of the participant the room knows as `name` (participant.name, or identity when unnamed)."""
        for p in self.room.remote_participants.values():
            if (p.name or p.identity) == name:
                return p.identity
        return None

    def email_of(self, name: str) -> str | None:
        for p in self.room.remote_participants.values():
            if (p.name or p.identity) != name:
                continue
            try:
                email = json.loads(p.metadata or "{}").get("email")
            except Exception:
                return None
            return str(email) if email else None
        return None

    def _audit_event(self, event: dict) -> None:
        kind = event.get("kind")
        room = self.cfg.name
        if kind == "transcript" and event.get("final"):
            self.audit.append(room, "transcript", str(event.get("speaker") or "?"), {"text": event.get("text"), "at": event.get("at")})
        elif kind == "turn_start":
            self.audit.append(room, "turn", str(event.get("asked_by") or "?"), {"question": event.get("question")})
        elif kind == "permission_request":
            self.audit.append(room, "permission", "marvin", {"id": event.get("id"), "tool": event.get("tool") or event.get("name")})
        elif kind == "permission_resolved":
            self.audit.append(room, "permission", str(event.get("by") or "?"), {"id": event.get("id"), "allow": event.get("allow")})
        elif kind == "error":
            self.audit.append(room, "error", "marvin", {"message": event.get("message")})
        elif kind in ("tool", "tool_call"):
            self.audit.append(room, "tool", "marvin", {"name": event.get("name") or event.get("tool")})

    async def _on_turn_begin(self, asked_by: str) -> None:
        """The person who asked becomes the git/gh identity for this turn (their connected GitHub, or the machine's)."""
        if not self.git_identity:
            return
        ident = self.identity_of(asked_by)
        meeting = self.audit.current(self.cfg.name) if self.audit else None
        who = await asyncio.to_thread(
            self.git_identity.apply, self.cfg.name, ident,
            author_name=asked_by,
            author_email=self.email_of(asked_by),
            session_id=meeting.id if meeting else None,
            turn=meeting.turn if meeting else None,
        )
        log.info("room %s: turn by %s, git identity: %s session=%s turn=%s", self.cfg.name, asked_by, who, meeting.id if meeting else "-", meeting.turn if meeting else "-")

    async def _ensure_sandbox(self, cfg: RoomConfig) -> None:
        """The room's container exists and matches cfg (repo, linked repos) before any harness process is spawned."""
        if self.sandbox:
            await self.sandbox.ensure(cfg)

    @property
    def harness(self):
        return self.conductor.harness if self.conductor else None

    async def reconfigure(self, cfg: RoomConfig) -> None:
        """Swap the harness (new model, harness and/or linked repos) while keeping the room, the conversation and the queue."""
        assert self.conductor is not None
        old = self.conductor.harness
        resume = getattr(old, "session_id", None) or self._load_state().get("session_id")
        if self.harness_id(cfg) != self.harness_id(self.cfg):
            # Session ids are not portable across harnesses: a new agent starts a new conversation.
            log.info("room %s: harness %s -> %s, dropping session %s", cfg.name, self.harness_id(self.cfg), self.harness_id(cfg), (resume or "")[:8])
            resume = None
            self._save_state(session_id=None)
        await self._ensure_sandbox(cfg)  # linked repos changed: the container is recreated with the new mounts
        new = self._make_harness(cfg, resume)
        new.permissions = self.conductor.permissions
        try:
            await new.start()
        except Exception as e:
            if not resume:
                raise
            log.warning("room %s: cannot resume session %s (%s); reconfiguring with a new one", cfg.name, resume[:8], str(e)[:120])
            self._save_state(session_id=None)
            new = self._make_harness(cfg, None)
            new.permissions = self.conductor.permissions
            await new.start()
        self.conductor.harness = new
        self.cfg = cfg
        try:
            await old.close()
        except Exception:
            log.exception("room %s: closing the old harness", cfg.name)
        log.info("room %s: harness reconfigured (harness=%s, model=%s, linked=%s)%s", cfg.name, self.harness_id(cfg), cfg.model or "default", list(cfg.linked), f", resuming {resume[:8]}" if resume else "")

    # -- lifecycle -----------------------------------------------------------------
    async def start(self) -> None:
        cfg = self.cfg
        await asyncio.to_thread(ensure_repo, cfg)
        await self._ensure_sandbox(cfg)
        resume = self._load_state().get("session_id")

        async def publish(event: dict) -> None:
            if event.get("kind") == "result" and event.get("session_id"):
                self._save_state(session_id=event["session_id"])
            if self.audit:
                self._audit_event(event)
            await self.room.local_participant.publish_data(encode(event), reliable=True, topic=TOPIC_EVENTS)

        if self.git_identity:
            await asyncio.to_thread(self.git_identity.apply, cfg.name, None)  # machine identity until someone asks
        harness = self._make_harness(cfg, resume)
        self.conductor = Conductor(
            harness, publish, agent_name=self.agent_name, timeline=Timeline(t0=time.monotonic()), app_links=[l.to_wire() for l in cfg.app_links],
            on_turn_begin=self._on_turn_begin if (self.git_identity or self.audit) else None,
        )
        harness.permissions = self.conductor.permissions
        conductor = self.conductor

        async def consume(track: rtc.Track, participant: rtc.RemoteParticipant) -> None:
            speaker = participant.name or participant.identity
            seg = self.stt(speaker, conductor.on_segment, language=cfg.language, clock=time.monotonic)
            stream = rtc.AudioStream(track, sample_rate=16_000, num_channels=1)
            log.info("room %s: transcribing %s", cfg.name, speaker)
            try:
                async for ev in stream:
                    await seg.push(np.frombuffer(ev.frame.data, dtype=np.int16))
            finally:
                await seg.flush()
                await stream.aclose()
                log.info("room %s: stopped transcribing %s", cfg.name, speaker)

        @self.room.on("track_subscribed")
        def on_track(track: rtc.Track, pub: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO and participant.identity != AGENT_IDENTITY:
                self.consumers[track.sid] = asyncio.create_task(consume(track, participant))

        @self.room.on("track_unsubscribed")
        def on_untrack(track: rtc.Track, pub: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant) -> None:
            if t := self.consumers.pop(track.sid, None):
                t.cancel()

        @self.room.on("participant_connected")
        def on_join(participant: rtc.RemoteParticipant) -> None:
            if participant.identity == AGENT_IDENTITY:
                return
            log.info("room %s: %s joined", cfg.name, participant.name or participant.identity)
            if self.audit:
                self.audit.join(cfg.name, participant.identity, name=participant.name or participant.identity)
            asyncio.create_task(conductor.announce())

        @self.room.on("participant_disconnected")
        def on_leave(participant: rtc.RemoteParticipant) -> None:
            if participant.identity == AGENT_IDENTITY:
                return
            log.info("room %s: %s left", cfg.name, participant.name or participant.identity)
            if self.audit:
                self.audit.leave(cfg.name, participant.identity)

        @self.room.on("data_received")
        def on_data(pkt: rtc.DataPacket) -> None:
            if pkt.topic != TOPIC_CONTROL or pkt.participant is None:
                return
            sender = pkt.participant.name or pkt.participant.identity
            try:
                msg = decode(pkt.data)
            except Exception:
                log.warning("room %s: bad control packet from %s", cfg.name, sender)
                return
            asyncio.create_task(conductor.on_control(sender, msg, roles=roles_of(pkt.participant)))

        token = agent_token(self.api_key, self.api_secret, cfg.name, self.agent_name)
        await self.room.connect(self.url, token, rtc.RoomOptions(auto_subscribe=True))
        log.info("room %s: joined at %s, repo %s%s", cfg.name, self.url, cfg.repo, f", resuming {resume[:8]}" if resume else "")
        try:
            await conductor.start()
        except Exception as e:
            if not resume:
                raise
            # The saved session no longer exists (new volume, pruned history): start fresh instead of failing the room.
            log.warning("room %s: cannot resume session %s (%s); starting a new one", cfg.name, resume[:8], str(e)[:120])
            self._save_state(session_id=None)
            conductor.harness = self._make_harness(cfg, None)
            conductor.harness.permissions = conductor.permissions
            await conductor.start()

    async def close(self) -> None:
        for t in self.consumers.values():
            t.cancel()
        if self.conductor:
            await self.conductor.close()
        await self.room.disconnect()
