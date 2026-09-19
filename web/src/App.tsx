import { useContext, useEffect, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer, ControlBar, StartAudio } from "@livekit/components-react";
import { People } from "./People";
import { MarvinPane } from "./MarvinPane";
import { Transcript } from "./Transcript";
import { useMarvin } from "./useMarvin";
import { JoinGate } from "./JoinGate";
import { Workspace } from "./Workspace";
import { SettingsPage } from "./Settings";
import { agent, loadAgentName } from "./agent";
import { RoomAndMachine, useRoomInfo } from "./RoomSettings";
import { Gutter, useColumns } from "./Columns";
import { MeContext, fetchMe, login, type Me } from "./auth";
import { MobileRoom, useIsMobile } from "./Mobile";
import { useEnterprise } from "./License";
import { useAppNav } from "./nav";
import { AppNavProvider, AppShell, BrandLogo, useProfile } from "./shell";

type Join = { serverUrl: string; token: string; room: string; relayOnly: boolean };

class Unauthorized extends Error {}

/** A LiveKit token for `room`. Who you are comes from the session (cookie or proxy headers); only `none` mode still
 * takes the typed name. */
async function fetchToken(room: string, name: string | null): Promise<Join> {
  const q = new URLSearchParams({ room });
  if (name !== null) q.set("name", name);
  const r = await fetch(`/api/token?${q}`);
  if (r.status === 401) throw new Unauthorized("Your session has expired. Please sign in again.");
  if (!r.ok) throw new Error(await r.text());
  const j = await r.json();
  // "self": LiveKit signaling is proxied by this same origin (Vite, Caddy or the ingress), so derive ws(s):// from it.
  const serverUrl = j.serverUrl === "self" ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}` : j.serverUrl;
  return { serverUrl, token: j.token, room, relayOnly: Boolean(j.relayOnly) };
}

export default function App() {
  return <Shell />;
}

function Shell() {
  const [me, setMe] = useState<Me | null>(null); // null until /api/me answered
  useEffect(() => { void fetchMe().then(setMe); }, []);
  if (!me) return <div className="join"><p className="hint">loading…</p></div>;
  return (
    <MeContext.Provider value={{ me, setMe }}>
      <JoinOrRoom me={me} setMe={setMe} />
    </MeContext.Provider>
  );
}

function JoinOrRoom({ me, setMe }: { me: Me; setMe: (m: Me) => void }) {
  const [name, setName] = useState(localStorage.getItem("marvin.name") ?? "");
  const [agentName, setAgentName] = useState(agent.name);
  const [join, setJoin] = useState<Join | null>(null);
  useEffect(() => { void loadAgentName().then(setAgentName); }, []);
  if (me.auth === "password" && !me.identity) return <LoginScreen agentName={agentName} onLogin={setMe} notice={null} />;
  if (me.auth === "header" && !me.identity) return <SsoRequiredScreen />;
  return (
    <AppNavProvider hasRoom={Boolean(join)}>
      <SignedIn me={me} setMe={setMe} name={name} setName={setName} agentName={agentName} join={join} setJoin={setJoin} />
    </AppNavProvider>
  );
}

function SignedIn({ me, setMe, name, setName, agentName, join, setJoin }: {
  me: Me;
  setMe: (m: Me) => void;
  name: string;
  setName: (name: string) => void;
  agentName: string;
  join: Join | null;
  setJoin: (join: Join | null) => void;
}) {
  const nav = useAppNav();
  const [error, setError] = useState<string | null>(null);
  const [deviceError, setDeviceError] = useState<string | null>(null);

  useEffect(() => {
    if (nav.page === "projects") {
      setJoin(null);
      return;
    }
    if (nav.page !== "room" || !nav.room) return;
    if (join?.room === nav.room) return;
    let cancelled = false;
    fetchToken(nav.room, me.auth === "none" ? name : null)
      .then((next) => { if (!cancelled) { setError(null); setJoin(next); } })
      .catch((cause) => {
        if (cancelled) return;
        setError(String(cause instanceof Error ? cause.message : cause));
        setJoin(null);
        if (cause instanceof Unauthorized) setMe({ ...me, identity: null });
        nav.goProjects();
      });
    return () => { cancelled = true; };
  }, [nav.page, nav.room, me.auth, name]);

  if (join && (nav.page === "room" || nav.page === "settings")) {
    return (
      <LiveKitRoom
        serverUrl={join.serverUrl}
        token={join.token}
        connect
        audio
        video={false}
        connectOptions={join.relayOnly ? { rtcConfig: { iceTransportPolicy: "relay" } } : undefined}
        onDisconnected={() => {
          setJoin(null);
          if (nav.page === "room") nav.goProjects();
        }}
        onMediaDeviceFailure={(failure) => setDeviceError(failure ? deviceHint("microphone", String(failure)) : null)}
      >
        <Room roomName={join.room} deviceError={deviceError} setDeviceError={setDeviceError} />
        <RoomAudioRenderer />
      </LiveKitRoom>
    );
  }

  return (
    <JoinGate
      onJoin={(room) => nav.openProject(room)}
      error={error}
      needsName={me.auth === "none"}
      name={name}
      setName={setName}
      agentName={agentName}
    />
  );
}

function deviceHint(source: string, reason: string): string {
  if (/NotAllowed|PermissionDenied/i.test(reason)) {
    return `Chrome blocked the ${source}. Click the icon left of the address bar, set ${source === "microphone" ? "Microphone" : "Screen"} to Allow, then reload.`;
  }
  if (/NotFound/i.test(reason)) return `No ${source} found on this computer.`;
  return `${source}: ${reason}`;
}

function Room({ roomName, deviceError, setDeviceError }: { roomName: string; deviceError: string | null; setDeviceError: (s: string | null) => void }) {
  const nav = useAppNav();
  const marvin = useMarvin();
  const columns = useColumns();
  const ee = useEnterprise();
  const profile = useProfile();
  const [side, setSide] = useState<"marvin" | "transcript">("transcript"); // the live transcript is the default view
  const [wanted, setWanted] = useState<string | null>(null);
  const roomInfoForSettings = useRoomInfo(roomName, 0);
  const last = marvin.turns[marvin.turns.length - 1];
  const refreshKey = marvin.turns.length * 2 + (last?.result ? 1 : 0); // re-read git when a turn starts and when it ends
  const mobile = useIsMobile();
  const repos = roomInfoForSettings.info?.repos ?? [];
  const settings = (
    <SettingsPage
      room={roomName}
      pane={nav.settingsPane}
      onPane={nav.setSettingsPane}
      extra={<RoomAndMachine room={roomName} info={roomInfoForSettings.info} reload={roomInfoForSettings.reload} />}
    />
  );

  if (mobile) {
    return (
      <AppShell ee={ee} section={nav.page === "settings" ? "settings" : "projects"} profile={profile} onProjects={nav.goProjects} onSettings={() => nav.openSettings()} room={nav.page === "room"}>
        {nav.page === "settings" ? settings : (
          <div className="layout" data-state={marvin.state} data-mobile="">
            <MobileRoom roomName={roomName} marvin={marvin} repos={repos} refreshKey={refreshKey} onSettings={() => nav.openSettings()} />
            {deviceError && <p className="error devhint">{deviceError}</p>}
          </div>
        )}
      </AppShell>
    );
  }

  if (nav.page === "settings") {
    return (
      <AppShell ee={ee} section="settings" profile={profile} onProjects={nav.goProjects} onSettings={() => nav.openSettings()}>
        {settings}
      </AppShell>
    );
  }

  return (
    <AppShell ee={ee} section="projects" profile={profile} onProjects={nav.goProjects} onSettings={() => nav.openSettings()} room>
      <div className="room-workspace" data-state={marvin.state}>
        <header className="room-bar">
          <b>#{roomName}</b>
          {deviceError && <p className="error devhint">{deviceError}</p>}
          <StartAudio label="Click to hear the room" />
          <span className="sp" />
          <div className="room-controls">
            <ControlBar
              variation="minimal"
              controls={{ microphone: true, camera: false, screenShare: true, leave: true, chat: false }}
              onDeviceError={({ source, error }) => setDeviceError(deviceHint(source, `${error.name} ${error.message}`))}
            />
          </div>
        </header>
        <div className="room-layout" style={columns.style}>
          <main className="center">
            <Workspace room={roomName} repos={repos} appLinks={marvin.appLinks} refreshKey={refreshKey} send={marvin.send} wanted={wanted} onShown={() => setWanted(null)} />
          </main>
          <Gutter side="right" resize={columns.resize} reset={columns.reset} />
          <aside className="right">
            <People agentState={marvin.state} />
            <AppLinks links={marvin.appLinks} onOpen={setWanted} />
            <div className="side-tabs">
              <button
                className={`${side === "marvin" ? "on" : ""} ${side !== "marvin" && marvin.state === "thinking" ? "busy" : ""} ${marvin.state === "waiting_approval" ? "attention" : ""}`.trim()}
                onClick={() => setSide("marvin")}
                title={marvin.state === "thinking" ? `${agent.name} is working` : marvin.state === "waiting_approval" ? `${agent.name} is waiting for an approval` : undefined}
              >
                <span className={`dot ${marvin.state}`} /> {agent.name}
              </button>
              <button className={side === "transcript" ? "on" : ""} onClick={() => setSide("transcript")}>Transcript</button>
            </div>
            {side === "marvin" ? <MarvinPane marvin={marvin} room={roomName} /> : <Transcript lines={marvin.transcript} />}
          </aside>
        </div>
      </div>
    </AppShell>
  );
}

function AppLinks({ links, onOpen }: { links: { label: string; url: string }[]; onOpen: (url: string) => void }) {
  if (links.length === 0) return null;
  return (
    <div className="applinks">
      <h2 className="left-sect">app</h2>
      {links.map((l) =>
        l.url ? (
          <a key={l.label + l.url} href={l.url} onClick={(e) => { e.preventDefault(); onOpen(l.url); }} title="open as a preview in the middle">
            {l.label} <span className="url">{l.url.replace(/^https?:\/\//, "")}</span>
          </a>
        ) : (
          <span key={l.label} className="applink-dead">{l.label}</span>
        ),
      )}
    </div>
  );
}

function ssoDevUrl() {
  const host = typeof location === "undefined" ? "" : location.hostname;
  if (host === "127.0.0.1" || host === "localhost") return "http://127.0.0.1:8088";
  return "";
}

function SsoRequiredScreen() {
  const href = ssoDevUrl();
  return (
    <main className="login-workspace">
      <aside className="login-rail">
        <div className="login-brand"><BrandLogo /></div>
        <div>
          <h1>Sign in at the proxy.</h1>
          <p>This address is the Vite app. Company sign-in only lands when you open the URL Caddy is serving.</p>
        </div>
      </aside>
      <div className="join login-card">
        <span className="login-ready">Identity proxy</span>
        <h1>You’re not signed in here</h1>
        <p>
          Marvin is in header mode, and this page never received who you are. The name in the corner was leftover from local development — it is not a login.
        </p>
        {href ? (
          <>
            <p className="dim small">Local test: maria@acme.com / maria is admin. alex@acme.com / alex is a participant.</p>
            <a className="join-primary" href={href}>Open {href}</a>
          </>
        ) : (
          <p>Ask an administrator for the signed-in machine URL.</p>
        )}
      </div>
    </main>
  );
}

function LoginScreen({ agentName, onLogin, notice }: { agentName: string; onLogin: (m: Me) => void; notice: string | null }) {
  const [email, setEmail] = useState(localStorage.getItem("marvin.name") ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <main className="login-workspace">
      <aside className="login-rail">
        <div className="login-brand"><BrandLogo /></div>
        <div><h1>A workspace you can talk to.</h1><p>Join your team’s coding room and say “{agentName}” when you need the agent.</p></div>
      </aside>
      <form
        className="join login-card"
        onSubmit={(e) => {
          e.preventDefault();
          if (!email || !password) return;
          setBusy(true);
          setError(null);
          login(email, password)
            .then((m) => { localStorage.setItem("marvin.name", email); onLogin(m); })
            .catch((err) => setError(String(err instanceof Error ? err.message : err)))
            .finally(() => setBusy(false));
        }}
      >
        <span className="login-ready">Secure machine access</span>
        <h1>Welcome back</h1>
        <p>Sign in to open your projects.</p>
        <label>Email <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus autoComplete="username" /></label>
        <label>
          Room password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        </label>
        <button type="submit" disabled={busy || !email || !password}>{busy ? "Signing in…" : "Sign in"}</button>
        {(error || notice) && <p className="error">{error ?? notice}</p>}
      </form>
    </main>
  );
}
