import { useEffect, useRef } from "react";
import type { TranscriptLine } from "./useMarvin";

export function Transcript({ lines }: { lines: TranscriptLine[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [lines]);
  return (
    <div className="transcript">
      <h2>Transcript</h2>
      {lines.length === 0 && <p className="hint">Live transcript of everyone in the room appears here.</p>}
      {lines.map((l, i) => (
        <p key={i} className={l.final === false ? "interim" : undefined}>
          <span className="t">{mmss(l.start)}</span> <b>{l.speaker}</b> {l.text}
        </p>
      ))}
      <div ref={endRef} />
    </div>
  );
}

function mmss(s: number) {
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
