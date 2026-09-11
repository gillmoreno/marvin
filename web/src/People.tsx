import { useParticipants, useIsSpeaking } from "@livekit/components-react";
import type { Participant } from "livekit-client";
import { AGENT_IDENTITY } from "./protocol";
import { agent } from "./agent";
import { rolesOf } from "./auth";

export function People({ agentState }: { agentState: string }) {
  const participants = useParticipants();
  const humans = participants.filter((p) => p.identity !== AGENT_IDENTITY);
  const agentPresent = participants.some((p) => p.identity === AGENT_IDENTITY);
  return (
    <ul className="people">
      <li className={`agent ${agentPresent ? "" : "away"}`}>
        <span className={`dot ${agentPresent ? agentState : "offline"}`} /> {agent.name} {agentPresent ? "" : "(worker not connected)"}
      </li>
      {humans.map((p) => (
        <Person key={p.identity} p={p} />
      ))}
    </ul>
  );
}

function Person({ p }: { p: Participant }) {
  const speaking = useIsSpeaking(p);
  const admin = rolesOf(p.metadata).includes("admin"); // roles come from the token server, signed into the LiveKit token
  return (
    <li className={speaking ? "speaking" : ""}>
      <span className="dot" /> {p.name || p.identity}
      {admin && <span className="badge" title="admin: may turn on “always allow”, create rooms, change models and edit machine notes">admin</span>}
      {p.isMicrophoneEnabled === false && <span className="muted"> muted</span>}
    </li>
  );
}
