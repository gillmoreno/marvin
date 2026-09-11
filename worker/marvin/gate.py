"""The power switch: a tiny always-on service that puts Marvin to sleep and wakes it up.

Sleep = scale the `marvin` StatefulSet and the `marvin-stt` Deployment to 0 (the GPU node goes away with it; the
volumes stay). The ingress uses this service as its default backend, so while Marvin sleeps the same URL shows a
"Marvin is asleep" page with a Wake button; `/power/*` is routed here always, so the room UI can call Sleep.
A schedule (MARVIN_SLEEP_AT / MARVIN_WAKE_AT, in the TZ timezone) puts it to sleep at night unless someone is in a
room and wakes it on weekday mornings.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import ssl
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import web

log = logging.getLogger("marvin.gate")

NAMESPACE = os.environ.get("MARVIN_NAMESPACE", "marvin")
WORKLOADS = (("statefulsets", "marvin"), ("deployments", "marvin-stt"))  # what sleep/wake scales
WEB_SERVICE = os.environ.get("MARVIN_WEB_SERVICE", "marvin-web")  # "awake" = this Service has endpoints


# ---------------------------------------------------------------- kubernetes (in-cluster REST, no client library)
class K8s:
    def __init__(self, base: str | None = None, token: str | None = None, ca: str | None = None) -> None:
        host, port = os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc"), os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        self.base = base or f"https://{host}:{port}"
        sa = "/var/run/secrets/kubernetes.io/serviceaccount"
        self.token = token if token is not None else (open(f"{sa}/token").read().strip() if os.path.exists(f"{sa}/token") else "")
        ca = ca if ca is not None else (f"{sa}/ca.crt" if os.path.exists(f"{sa}/ca.crt") else None)
        self.ssl = ssl.create_default_context(cafile=ca) if ca else False

    async def _req(self, method: str, path: str, body: dict | None = None, content_type: str = "application/json") -> dict:
        async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {self.token}"}) as s:
            async with s.request(method, self.base + path, data=json.dumps(body) if body is not None else None, headers={"Content-Type": content_type}, ssl=self.ssl) as r:
                if r.status >= 300:
                    raise RuntimeError(f"{method} {path}: {r.status} {(await r.text())[:200]}")
                return await r.json()

    async def replicas(self, kind: str, name: str) -> tuple[int, int]:
        """(desired, ready)"""
        d = await self._req("GET", f"/apis/apps/v1/namespaces/{NAMESPACE}/{kind}/{name}")
        return int(d["spec"].get("replicas", 0)), int(d.get("status", {}).get("readyReplicas") or 0)

    async def scale(self, kind: str, name: str, n: int) -> None:
        await self._req("PATCH", f"/apis/apps/v1/namespaces/{NAMESPACE}/{kind}/{name}/scale", {"spec": {"replicas": n}}, content_type="application/merge-patch+json")

    async def has_endpoints(self, service: str) -> bool:
        d = await self._req("GET", f"/api/v1/namespaces/{NAMESPACE}/endpoints/{service}")
        return any(sub.get("addresses") for sub in d.get("subsets") or [])


# ---------------------------------------------------------------- power
@dataclass
class Status:
    state: str  # asleep | waking | awake | sleeping
    workloads: dict[str, tuple[int, int]]
    since: str | None = None

    def to_wire(self) -> dict:
        return {"state": self.state, "workloads": {k: {"desired": v[0], "ready": v[1]} for k, v in self.workloads.items()}, "since": self.since}


class Power:
    def __init__(self, k8s: K8s) -> None:
        self.k8s = k8s
        self.changed_at: str | None = None

    async def status(self) -> Status:
        wl = {name: await self.k8s.replicas(kind, name) for kind, name in WORKLOADS}
        desired_any = any(d > 0 for d, _ in wl.values())
        awake = await self.k8s.has_endpoints(WEB_SERVICE)
        if not desired_any:
            state = "sleeping" if awake else "asleep"
        else:
            state = "awake" if awake else "waking"
        return Status(state=state, workloads=wl, since=self.changed_at)

    async def wake(self) -> Status:
        for kind, name in WORKLOADS:
            await self.k8s.scale(kind, name, 1)
        self.changed_at = dt.datetime.now(dt.timezone.utc).isoformat()
        log.info("wake requested")
        return await self.status()

    async def sleep(self) -> Status:
        for kind, name in WORKLOADS:
            await self.k8s.scale(kind, name, 0)
        self.changed_at = dt.datetime.now(dt.timezone.utc).isoformat()
        log.info("sleep requested")
        return await self.status()


# ---------------------------------------------------------------- schedule
@dataclass(frozen=True)
class Schedule:
    sleep_at: dt.time | None  # e.g. 20:00
    wake_at: dt.time | None  # e.g. 08:00, weekdays only
    tz: str = "UTC"
    weekdays_only_wake: bool = True

    @classmethod
    def from_env(cls, env=os.environ) -> "Schedule":
        def t(v: str | None) -> dt.time | None:
            return dt.time.fromisoformat(v) if v else None

        return cls(sleep_at=t(env.get("MARVIN_SLEEP_AT")), wake_at=t(env.get("MARVIN_WAKE_AT")), tz=env.get("TZ", "UTC"))

    def decide(self, now: dt.datetime, state: str, someone_in_a_room: bool) -> str | None:
        """Return 'sleep', 'wake' or None for this minute."""
        local = now.astimezone(ZoneInfo(self.tz))
        hm = local.time().replace(second=0, microsecond=0)
        if self.sleep_at and hm == self.sleep_at and state in ("awake", "waking"):
            return None if someone_in_a_room else "sleep"
        if self.wake_at and hm == self.wake_at and state in ("asleep", "sleeping"):
            if self.weekdays_only_wake and local.weekday() >= 5:
                return None
            return "wake"
        return None


async def someone_in_a_room() -> bool:
    """Ask LiveKit whether any human is connected (the agent's identity is 'marvin')."""
    url = os.environ.get("LIVEKIT_URL", "http://marvin-livekit:7880")
    key, secret = os.environ.get("LIVEKIT_API_KEY"), os.environ.get("LIVEKIT_API_SECRET")
    if not (key and secret):
        return False
    try:
        from livekit import api

        lk = api.LiveKitAPI(url.replace("ws://", "http://").replace("wss://", "https://"), key, secret)
        try:
            rooms = await lk.room.list_rooms(api.ListRoomsRequest())
            for room in rooms.rooms:
                parts = await lk.room.list_participants(api.ListParticipantsRequest(room=room.name))
                if any(p.identity != "marvin" for p in parts.participants):
                    return True
            return False
        finally:
            await lk.aclose()
    except Exception as e:
        log.warning("cannot ask LiveKit who is connected: %s (assuming someone is)", e)
        return True


# ---------------------------------------------------------------- web
PAGE = """<!doctype html><meta charset="utf-8"><title>Marvin</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0;background:#0f1115;color:#e6e8eb;font:15px/1.5 system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{width:min(460px,92vw);background:#161a21;border:1px solid #262c36;border-radius:12px;padding:28px 30px}
h1{font-size:20px;margin:0 0 6px}p{margin:8px 0;color:#8b949e}
button{background:#7aa2f7;color:#0b0d11;border:0;border-radius:8px;padding:11px 18px;font-weight:700;font-size:15px;cursor:pointer}
button:disabled{opacity:.5;cursor:default}.bar{height:6px;background:#262c36;border-radius:3px;overflow:hidden;margin:14px 0}
.bar i{display:block;height:100%;width:30%;background:#7aa2f7;animation:m 1.2s infinite}@keyframes m{0%{margin-left:-30%}100%{margin-left:100%}}
.wl{font-size:13px;color:#8b949e}.wl b{color:#e6e8eb}
</style>
<div class="card" id="c"><h1>Marvin is asleep</h1><p>The machine is scaled to zero to save money. Waking takes about a minute for the room and a few minutes for the GPU transcription.</p>
<button id="w">Wake Marvin</button><div id="s"></div></div>
<script>
const c=document.getElementById('c'),s=document.getElementById('s'),w=document.getElementById('w');
async function st(){const r=await fetch('/power/status');return r.json()}
function render(j){const wl=Object.entries(j.workloads).map(([k,v])=>`<div class="wl">${k}: <b>${v.ready}/${v.desired}</b> ready</div>`).join('');
 if(j.state==='awake'){c.innerHTML='<h1>Marvin is awake</h1><p>Opening the room…</p>';setTimeout(()=>location.replace('/'),1500);return}
 if(j.state==='waking'){c.innerHTML='<h1>Marvin is waking up</h1><p>The room comes first; transcription on the GPU follows a few minutes later (Whisper covers meanwhile).</p><div class="bar"><i></i></div>'+wl;return}
 if(j.state==='sleeping'){c.innerHTML='<h1>Marvin is going to sleep</h1><div class="bar"><i></i></div>'+wl;return}
 s.innerHTML=wl}
w.onclick=async()=>{w.disabled=true;await fetch('/power/wake',{method:'POST'});poll()};
async function poll(){try{render(await st())}catch(e){}setTimeout(poll,3000)}
st().then(render).catch(()=>{});setInterval(()=>st().then(render).catch(()=>{}),3000);
</script>"""


def make_app(power: Power) -> web.Application:
    app = web.Application()

    async def page(req: web.Request) -> web.Response:
        return web.Response(text=PAGE, content_type="text/html")

    async def status(req: web.Request) -> web.Response:
        return web.json_response((await power.status()).to_wire())

    async def wake(req: web.Request) -> web.Response:
        return web.json_response((await power.wake()).to_wire())

    async def sleep(req: web.Request) -> web.Response:
        return web.json_response((await power.sleep()).to_wire())

    async def api_asleep(req: web.Request) -> web.Response:
        return web.json_response({"error": "Marvin is asleep; open the page to wake it"}, status=503)

    app.router.add_get("/power/status", status)
    app.router.add_post("/power/wake", wake)
    app.router.add_post("/power/sleep", sleep)
    app.router.add_get("/power", page)
    app.router.add_get("/power/", page)
    app.router.add_get("/healthz", lambda r: web.Response(text="ok"))
    app.router.add_route("*", "/api/{tail:.*}", api_asleep)
    app.router.add_get("/{tail:.*}", page)  # default backend while asleep: any path shows the wake page
    return app


async def run_schedule(power: Power, schedule: Schedule) -> None:
    last_minute = None
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        minute = now.replace(second=0, microsecond=0)
        if minute != last_minute:
            last_minute = minute
            try:
                state = (await power.status()).state
                busy = await someone_in_a_room() if schedule.sleep_at else False
                action = schedule.decide(now, state, busy)
                if action == "sleep":
                    log.info("schedule: sleeping (nobody in a room)")
                    await power.sleep()
                elif action == "wake":
                    log.info("schedule: waking")
                    await power.wake()
                elif schedule.sleep_at and now.astimezone(ZoneInfo(schedule.tz)).time().replace(second=0, microsecond=0) == schedule.sleep_at and busy:
                    log.info("schedule: someone is in a room, not sleeping")
            except Exception:
                log.exception("schedule tick")
        await asyncio.sleep(20)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    power = Power(K8s())
    schedule = Schedule.from_env()
    app = make_app(power)

    async def on_start(app: web.Application) -> None:
        app["schedule"] = asyncio.create_task(run_schedule(power, schedule))
        log.info("gate up; schedule sleep_at=%s wake_at=%s tz=%s", schedule.sleep_at, schedule.wake_at, schedule.tz)

    app.on_startup.append(on_start)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("MARVIN_GATE_PORT", "8091")))


if __name__ == "__main__":
    main()
