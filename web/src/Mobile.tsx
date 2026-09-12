import { useEffect, useState } from "react";
import { useLocalParticipant, useRoomContext } from "@livekit/components-react";
import { MarvinPane } from "./MarvinPane";
import { Transcript } from "./Transcript";
import { ChangesPane } from "./ChangesPane";
import { ScreenShareView, screenShareKey, screenShareLabel, useScreenShares } from "./ScreenShare";
import { stateLabel } from "./People";
import { agent } from "./agent";
import { AgentPresence, SpeakerPresence } from "./theme/Presence";
import { LeaveIcon, MicIcon, MicOffIcon, GearIcon } from "./icons";
import type { useMarvin } from "./useMarvin";
import type { ProjectRepoInfo } from "./ProjectRepos";

/** Under ~720px the room is one pane at a time: on a phone you talk and look. No columns, no gutters, no machine
 *  notes; a big talk/mute control and the approval buttons stay within a thumb's reach whatever pane is open. */
export function useIsMobile(): boolean {
  const q = "(max-width: 720px)";
  const [m, setM] = useState(() => typeof matchMedia === "function" && matchMedia(q).matches);
  useEffect(() => {
    const mq = matchMedia(q);
    const on = () => setM(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return m;
}

type Pane = "marvin" | "transcript" | "changes" | `app:${string}` | `screen:${string}`;

export function MobileRoom({ roomName, marvin, repos, refreshKey, onSettings }: {
  roomName: string; marvin: ReturnType<typeof useMarvin>; repos: ProjectRepoInfo[]; refreshKey: number; onSettings: () => void;
}) {
  const [pane, setPane] = useState<Pane>("marvin");
  const apps = marvin.appLinks.filter((l) => l.url);
  const screens = useScreenShares();
  const room = useRoomContext();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const open = marvin.permissions.filter((p) => !p.resolved).length;
  // A pane that disappears (app closed, share stopped) hands back to Marvin.
  useEffect(() => {
    if (pane.startsWith("app:") && !apps.some((a) => `app:${a.url}` === pane)) setPane("marvin");
    if (pane.startsWith("screen:") && !screens.some((s) => `screen:${screenShareKey(s)}` === pane)) setPane("marvin");
  }, [pane, apps, screens]);
  const app = apps.find((a) => `app:${a.url}` === pane);
  const screen = screens.find((s) => `screen:${screenShareKey(s)}` === pane);
  return (
    <>
      <div className="m-top">
        <span className="m-title">{agent.name} <span className="room">#{roomName}</span></span>
        <AgentPresence state={marvin.state} label={`${agent.name} is ${stateLabel(marvin.state)}`} />
        <span className="m-state">{stateLabel(marvin.state)}</span>
        <button type="button" className="iconbtn settings-btn" onClick={onSettings} aria-label="settings" title="settings"><GearIcon /></button>
      </div>
      <div className="m-pane" data-pane={pane.split(":")[0]}>
        {pane === "marvin" && <MarvinPane marvin={marvin} room={roomName} />}
        {pane === "transcript" && <Transcript lines={marvin.transcript} />}
        {pane === "changes" && <ChangesPane room={roomName} repos={repos} refreshKey={refreshKey} send={marvin.send} />}
        {app && <iframe className="preview" src={app.url} title={app.label} sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals" />}
        {screen && <ScreenShareView track={screen} />}
      </div>
      <nav className="m-tabs">
        <button className={`${pane === "marvin" ? "on" : ""} ${open ? "attention" : ""}`.trim()} onClick={() => setPane("marvin")}>
          <span className={`dot ${marvin.state}`} /> {agent.name}{open ? ` (${open})` : ""}
        </button>
        <button className={pane === "transcript" ? "on" : ""} onClick={() => setPane("transcript")}>Transcript</button>
        <button className={pane === "changes" ? "on" : ""} onClick={() => setPane("changes")}>Changes</button>
        {apps.map((a) => (
          <button key={a.url} className={pane === `app:${a.url}` ? "on" : ""} onClick={() => setPane(`app:${a.url}`)}>▶ {a.label}</button>
        ))}
        {screens.map((s) => {
          const key: Pane = `screen:${screenShareKey(s)}`;
          return <button key={key} className={`${pane === key ? "on" : ""} live`.trim()} onClick={() => setPane(key)}><span className="dot rec" /> {screenShareLabel(s)}</button>;
        })}
      </nav>
      <div className="m-bar">
        <span className="m-speaker">
          <SpeakerPresence participant={localParticipant} />
          <span className="who">{localParticipant.name || localParticipant.identity}<small>{isMicrophoneEnabled ? "you're live · tap to mute" : "muted · tap to talk"}</small></span>
        </span>
        <button type="button" className={`m-talk${isMicrophoneEnabled ? "" : " muted"}`} onClick={() => void localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)} aria-pressed={isMicrophoneEnabled} aria-label={isMicrophoneEnabled ? "mute" : "unmute"}>
          {isMicrophoneEnabled ? <MicIcon /> : <MicOffIcon />}
        </button>
        <button type="button" className="m-leave" onClick={() => void room.disconnect()} aria-label="leave the room" title="leave"><LeaveIcon /></button>
      </div>
    </>
  );
}
