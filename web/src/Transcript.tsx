import { useEffect, useRef } from "react";
import type { TranscriptLine } from "./useMarvin";
import { agent } from "./agent";

export function Transcript({ lines }: { lines: TranscriptLine[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [lines]);
  return (
    <div className="transcript">
      <h2>Transcript</h2>
      {lines.length === 0 && <p className="hint">Live transcript of everyone in the room appears here.</p>}
      {lines.map((l, i) => (
        <p key={i} className={l.final === false ? "interim" : undefined} data-speaker={l.speaker === agent.name ? "agent" : "human"}>
          <span className="t" title={`${l.start.toFixed(1)} s into the session`}>{clock(l)}</span>
          <b className="w">{l.speaker}</b>
          <span className="txt">{l.text}</span>
        </p>
      ))}
      <div ref={endRef} />
    </div>
  );
}

/** Wall-clock time of the utterance (`at`, epoch seconds); older workers only send session-relative `start`. */
function clock(l: TranscriptLine) {
  if (l.at) return new Date(l.at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const m = Math.floor(l.start / 60);
  return `${String(m).padStart(2, "0")}:${String(Math.floor(l.start % 60)).padStart(2, "0")}`;
}
