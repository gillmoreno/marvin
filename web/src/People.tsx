import { useParticipants, useIsSpeaking } from "@livekit/components-react";
import type { Participant } from "livekit-client";
import { AGENT_IDENTITY } from "./protocol";
import { agent } from "./agent";
import { rolesOf } from "./auth";
import { AgentPresence, SpeakerPresence, type AgentState } from "./theme/Presence";

export function People({ agentState }: { agentState: AgentState }) {
  const participants = useParticipants();
  const humans = participants.filter((p) => p.identity !== AGENT_IDENTITY);
  const agentPresent = participants.some((p) => p.identity === AGENT_IDENTITY);
  const state: AgentState = agentPresent ? agentState : "offline";
  const n = humans.length + 1; // Marvin is always listed
  return (
    <>
      <p className="left-sect">in the room · {n}</p>
      <ul className="people">
        <li className={`agent ${agentPresent ? "" : "away"}`} data-agent data-away={agentPresent ? undefined : ""}>
          <span className={`dot ${state}`} />
          <span className="nm"><b>{agent.name}</b> <span className="role">agent</span></span>
          <span className="who-st"><span className="who-st-txt">{agentPresent ? stateLabel(state) : "away"}</span></span>
          <AgentPresence state={state} label={`${agent.name} is ${stateLabel(state)}`} />
        </li>
        {humans.map((p) => (
          <Person key={p.identity} p={p} />
        ))}
      </ul>
    </>
  );
}

export function stateLabel(s: string): string {
  return { offline: "offline", idle: "listening", thinking: "working", waiting_approval: "waiting" }[s] ?? s;
}

function Person({ p }: { p: Participant }) {
  const speaking = useIsSpeaking(p);
  const admin = rolesOf(p.metadata).includes("admin"); // roles come from the token server, signed into the LiveKit token
  const muted = p.isMicrophoneEnabled === false;
  return (
    <li data-speaking={speaking || undefined} data-away={muted || undefined}>
      <span className={`dot${muted ? " offline" : speaking ? " idle" : ""}`} />
      <span className="nm">
        <b>{p.name || p.identity}</b>
        {admin && <span className="role" title="admin: may turn on “always allow”, create rooms, change models and edit machine notes">admin</span>}
      </span>
      <span className="who-st">
        <SpeakerPresence participant={p} />
        <span className="who-st-txt">{muted ? "muted" : speaking ? "live" : "quiet"}</span>
      </span>
    </li>
  );
}
