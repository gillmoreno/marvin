import { useContext, useEffect, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer, ControlBar, StartAudio } from "@livekit/components-react";
import { People } from "./People";
import { MarvinPane } from "./MarvinPane";
import { Transcript } from "./Transcript";
import { useMarvin } from "./useMarvin";
import { JoinGate } from "./JoinGate";
import { Workspace } from "./Workspace";
import { SettingsPanel } from "./Settings";
import { agent, loadAgentName } from "./agent";
import { RoomAndMachine, useRoomInfo, useHarnesses, useModels } from "./RoomSettings";
import { Gutter, useColumns } from "./Columns";
import { SlidersIcon } from "./icons";
import { MeContext, fetchMe, login, type Me } from "./auth";
import { ThemeProvider, useTheme } from "./theme/ThemeContext";
import { AgentPresence } from "./theme/Presence";
import { stateLabel } from "./People";
import { MobileRoom, useIsMobile } from "./Mobile";
import { useParticipants, useSpeakingParticipants } from "@livekit/components-react";
import { AGENT_IDENTITY } from "./protocol";

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
  return (
    <ThemeProvider>
      <Shell />
    </ThemeProvider>
  );
}

function Shell() {
  const [me, setMe] = useState<Me | null>(null); // null until /api/me answered
  const [join, setJoin] = useState<Join | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const themes = useTheme();
  useEffect(() => { void fetchMe().then(setMe); }, []);
  // Custom themes are only listed once signed in: re-read the list when the identity changes.
  const signedIn = Boolean(me?.identity);
  useEffect(() => { if (signedIn) void themes.refresh(); }, [signedIn, themes.refresh]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!me) return <div className="join"><p className="hint">loading…</p></div>;
  const ctx = { me, setMe };
  if (!join) {
    const onJoin = (room: string, name: string | null) =>
      fetchToken(room, name)
        .then((j) => { setError(null); setJoin(j); })
        .catch((e) => {
          setError(String(e instanceof Error ? e.message : e));
          if (e instanceof Unauthorized) setMe({ ...me, identity: null }); // back to the login screen
        });
    return (
      <MeContext.Provider value={ctx}>
        <JoinScreen onJoin={onJoin} error={error} />
      </MeContext.Provider>
    );
  }
  return (
    <MeContext.Provider value={ctx}>
    <LiveKitRoom
      serverUrl={join.serverUrl}
      token={join.token}
      connect
      audio
      video={false}
      // Behind a VPN/firewall that only allows hostnames, just LiveKit's TURN hostname is reachable: skip the unroutable direct candidates.
      connectOptions={join.relayOnly ? { rtcConfig: { iceTransportPolicy: "relay" } } : undefined}
      onDisconnected={() => setJoin(null)}
      // The `audio` prop asks for the mic at join; a denied prompt or a site-level block lands here, not in the toggle.
      onMediaDeviceFailure={(failure) => setDeviceError(failure ? deviceHint("microphone", String(failure)) : null)}
    >
      <Room roomName={join.room} deviceError={deviceError} setDeviceError={setDeviceError} />
      <RoomAudioRenderer />
    </LiveKitRoom>
    </MeContext.Provider>
  );
}

/** The status rail across the top of the room (shown by themes that want it, e.g. Control Room). */
function Rail({ roomName, state, info }: { roomName: string; state: "offline" | "idle" | "thinking" | "waiting_approval"; info: ReturnType<typeof useRoomInfo>["info"] }) {
  const speaking = useSpeakingParticipants().filter((p) => p.identity !== AGENT_IDENTITY);
  const people = useParticipants().filter((p) => p.identity !== AGENT_IDENTITY).length;
  const [t0] = useState(() => Date.now());
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const s = Math.floor((now - t0) / 1000);
  const clock = `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  const { harnesses } = useHarnesses();
  const { models } = useModels(roomName, info?.harness, info?.model);
  const [git, setGit] = useState<{ branch: string | null; base: string | null } | null>(null);
  useEffect(() => {
    fetch(`/api/changes?room=${encodeURIComponent(roomName)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j?.branch) setGit({ branch: j.branch, base: j.base ?? null }); })
      .catch(() => {});
  }, [roomName]);
  const branch = git?.branch ?? info?.repos?.[0]?.branch;
  const base = git?.base?.replace(/@[0-9a-f]+$/i, "");
  const harness = harnesses.find((h) => h.id === info?.harness)?.label ?? info?.harness;
  const model = models.find((m) => m.id === (info?.model ?? ""))?.label ?? info?.model;
  return (
    <header className="rail">
      <div className="rail-cell rail-room">{agent.name} <span className="room">#{roomName}</span></div>
      <div className="rail-cell"><span className="rail-state">{stateLabel(state)}</span></div>
      <div className="rail-cell rail-scope"><AgentPresence state={state} className="rail-presence" label={`${agent.name} is ${stateLabel(state)}`} /></div>
      {branch && (
        <div className="rail-cell rail-hide-m">
          <span className="rail-k">branch</span> {branch}
          {base && base !== branch && <><span className="dim"> → </span>{base}</>}
        </div>
      )}
      {(harness || model) && (
        <div className="rail-cell rail-hide-m">
          {harness && <><span className="rail-k">harness</span> {harness}</>}
          {harness && model && <span className="dim"> · </span>}
          {model}
        </div>
      )}
      <div className="rail-cell rail-hide-m rail-live">
        <span className="rail-k">live</span>
        <span className={`dot ${speaking.length ? "idle" : "offline"}`} />
        {speaking.length ? speaking.map((p) => p.name || p.identity).join(", ") : `${people} in the room`}
      </div>
      <div className="rail-cell rail-clock" title="time in this session">{clock}</div>
    </header>
  );
}

/** One line under the people list when a custom theme just appeared (the agent wrote it during the last turn). */
function FreshTheme() {
  const th = useTheme();
  if (!th.fresh) return null;
  return (
    <p className="fresh-theme">
      New theme <b>{th.fresh.name}</b>
      <button type="button" onClick={() => th.choose(th.fresh!.id)}>try it</button>
      <button type="button" className="ghost" onClick={th.dismissFresh}>later</button>
    </p>
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
  const marvin = useMarvin();
  const columns = useColumns();
  const [side, setSide] = useState<"marvin" | "transcript">("transcript"); // the live transcript is the default view
  const [wanted, setWanted] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const roomInfoForSettings = useRoomInfo(roomName, 0);
  const last = marvin.turns[marvin.turns.length - 1];
  const refreshKey = marvin.turns.length * 2 + (last?.result ? 1 : 0); // re-read git when a turn starts and when it ends
  const mobile = useIsMobile();
  const themes = useTheme();
  useEffect(() => { void themes.refresh(); }, [refreshKey, themes.refresh]); // a turn just ended: the agent may have written a theme
  const repos = roomInfoForSettings.info?.repos ?? [];
  const settings = showSettings && <SettingsPanel room={roomName} onClose={() => setShowSettings(false)} extra={<RoomAndMachine room={roomName} info={roomInfoForSettings.info} reload={roomInfoForSettings.reload} />} />;
  if (mobile) {
    return (
      <div className="layout" data-state={marvin.state} data-mobile="">
        <MobileRoom roomName={roomName} marvin={marvin} repos={repos} refreshKey={refreshKey} onSettings={() => setShowSettings(true)} />
        {deviceError && <p className="error devhint">{deviceError}</p>}
        {settings}
      </div>
    );
  }
  return (
    <div className="layout" data-state={marvin.state} style={columns.style}>
      <Rail roomName={roomName} state={marvin.state} info={roomInfoForSettings.info} />
      <aside className="left">
        <div className="left-head">
          <h1>{agent.name} <span className="room">#{roomName}</span></h1>
        </div>
        <div className="left-body">
          <People agentState={marvin.state} />
          <FreshTheme />
          <AppLinks links={marvin.appLinks} onOpen={setWanted} />
        </div>
        {deviceError && <p className="error devhint">{deviceError}</p>}
        <StartAudio label="Click to hear the room" />
        <div className="left-foot">
          <button type="button" className="settings-btn" onClick={() => setShowSettings(true)} aria-label="settings" title="settings"><SlidersIcon /></button>
          <span className="sp" />
          <ControlBar
            variation="minimal"
            controls={{ microphone: true, camera: false, screenShare: true, leave: true, chat: false }}
            onDeviceError={({ source, error }) => setDeviceError(deviceHint(source, `${error.name} ${error.message}`))}
          />
        </div>
      </aside>
      <Gutter side="left" resize={columns.resize} reset={columns.reset} />
      <main className="center">
        <Workspace room={roomName} repos={repos} appLinks={marvin.appLinks} refreshKey={refreshKey} send={marvin.send} wanted={wanted} onShown={() => setWanted(null)} />
      </main>
      <Gutter side="right" resize={columns.resize} reset={columns.reset} />
      <aside className="right">
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
      {settings}
    </div>
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

/** Join screen. Password mode without a session shows the login form; everyone else hits the three-step gate
 * (machine GitHub + an agent required; personal GitHub optional). none mode still asks for a display name. */
function JoinScreen({ onJoin, error }: { onJoin: (room: string, name: string | null) => void; error: string | null }) {
  const { me, setMe } = useContext(MeContext);
  const [name, setName] = useState(localStorage.getItem("marvin.name") ?? "");
  const [agentName, setAgentName] = useState(agent.name);
  useEffect(() => { void loadAgentName().then(setAgentName); }, []);
  if (me.auth === "password" && !me.identity) return <LoginScreen agentName={agentName} onLogin={setMe} notice={error} />;
  return (
    <JoinGate
      onJoin={onJoin}
      error={error}
      needsName={me.auth === "none"}
      name={name}
      setName={setName}
      agentName={agentName}
    />
  );
}

function LoginScreen({ agentName, onLogin, notice }: { agentName: string; onLogin: (m: Me) => void; notice: string | null }) {
  const [email, setEmail] = useState(localStorage.getItem("marvin.name") ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="join"
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
      <h1>Marvin</h1>
      <p>A voice room with a coding agent in it. Say "{agentName}" to talk to it.</p>
      <label>Email <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus autoComplete="username" /></label>
      <label>
        Room password <span className="hint small">(the admin password also works)</span>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
      </label>
      <button type="submit" disabled={busy || !email || !password}>{busy ? "signing in…" : "Sign in"}</button>
      {(error || notice) && <p className="error">{error ?? notice}</p>}
    </form>
  );
}
