import { useEffect, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer, ControlBar, StartAudio } from "@livekit/components-react";
import { People } from "./People";
import { MarvinPane } from "./MarvinPane";
import { Transcript } from "./Transcript";
import { useMarvin } from "./useMarvin";
import { RoomPicker } from "./RoomPicker";
import { Workspace } from "./Workspace";
import { SettingsPanel } from "./Settings";
import { agent, loadAgentName } from "./agent";
import { RoomAndMachine, useRoomInfo } from "./RoomSettings";
import { Gutter, useColumns } from "./Columns";

type Join = { serverUrl: string; token: string; room: string; name: string; relayOnly: boolean };

async function fetchToken(room: string, name: string): Promise<Join> {
  const r = await fetch(`/api/token?room=${encodeURIComponent(room)}&name=${encodeURIComponent(name)}`);
  if (!r.ok) throw new Error(await r.text());
  const j = await r.json();
  // "self": LiveKit signaling is proxied by this same dev server, so derive ws(s):// from the page's own origin.
  const serverUrl = j.serverUrl === "self" ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}` : j.serverUrl;
  return { serverUrl, token: j.token, room, name, relayOnly: Boolean(j.relayOnly) };
}

export default function App() {
  const [join, setJoin] = useState<Join | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  if (!join) return <JoinScreen onJoin={(r, n) => fetchToken(r, n).then(setJoin).catch((e) => setError(String(e)))} error={error} />;
  return (
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
  return (
    <div className="layout" style={columns.style}>
      <aside className="left">
        <h1>{agent.name} <span className="room">#{roomName}</span></h1>
        <People agentState={marvin.state} />
        <AppLinks links={marvin.appLinks} onOpen={setWanted} />
        <div className="grow" />
        <button type="button" className="ghost settings-btn" onClick={() => setShowSettings(true)}>⚙ settings</button>
        <StartAudio label="Click to hear the room" />
        {deviceError && <p className="error devhint">{deviceError}</p>}
        <ControlBar
          variation="minimal"
          controls={{ microphone: true, camera: false, screenShare: true, leave: true, chat: false }}
          onDeviceError={({ source, error }) => setDeviceError(deviceHint(source, `${error.name} ${error.message}`))}
        />
      </aside>
      <Gutter side="left" resize={columns.resize} reset={columns.reset} />
      <main className="center">
        <Workspace room={roomName} appLinks={marvin.appLinks} refreshKey={refreshKey} send={marvin.send} wanted={wanted} onShown={() => setWanted(null)} />
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
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} extra={<RoomAndMachine room={roomName} info={roomInfoForSettings.info} reload={roomInfoForSettings.reload} />} />}
    </div>
  );
}

function AppLinks({ links, onOpen }: { links: { label: string; url: string }[]; onOpen: (url: string) => void }) {
  if (links.length === 0) return null;
  return (
    <div className="applinks">
      <h2>App</h2>
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

function JoinScreen({ onJoin, error }: { onJoin: (room: string, name: string) => void; error: string | null }) {
  const [room, setRoom] = useState(localStorage.getItem("marvin.room") ?? "");
  const [name, setName] = useState(localStorage.getItem("marvin.name") ?? "");
  const [agentName, setAgentName] = useState(agent.name);
  useEffect(() => { void loadAgentName().then(setAgentName); }, []);
  return (
    <form
      className="join"
      onSubmit={(e) => {
        e.preventDefault();
        if (!room) return;
        localStorage.setItem("marvin.room", room);
        localStorage.setItem("marvin.name", name);
        onJoin(room, name);
      }}
    >
      <h1>Marvin</h1>
      <p>A voice room with a coding agent in it. Say "{agentName}" to talk to it.</p>
      <label>Your name <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></label>
      <RoomPicker value={room} onPick={setRoom} />
      <button type="submit" disabled={!room || !name}>Join {room || "a room"}</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
