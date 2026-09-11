import { useParticipants, useIsSpeaking } from "@livekit/components-react";
import type { Participant } from "livekit-client";
import { AGENT_IDENTITY } from "./protocol";
import { agent } from "./agent";

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
  return (
    <li className={speaking ? "speaking" : ""}>
      <span className="dot" /> {p.name || p.identity}
      {p.isMicrophoneEnabled === false && <span className="muted"> muted</span>}
    </li>
  );
}
