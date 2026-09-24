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
      {lines.map((l, i) => {
        const continued = i > 0 && lines[i - 1].speaker === l.speaker && lines[i - 1].final !== false;
        const who = speakerLabel(l.speaker);
        return (
          <div
            key={i}
            className={`line${continued ? " cont" : ""}${l.final === false ? " interim" : ""}`}
            data-speaker={l.speaker === agent.name ? "agent" : "human"}
          >
            <span className="t" title={`${l.start.toFixed(1)} s into the session`}>{clock(l)}</span>
            {!continued && <b className="who" title={who.title}>{who.label}</b>}
            <span className="txt">{l.text}</span>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}

/** Emails are how people sign in. The transcript shows a name; the address stays on hover. */
export function speakerLabel(speaker: string): { label: string; title?: string } {
  const at = speaker.indexOf("@");
  if (at <= 0) return { label: speaker };
  const words = speaker.slice(0, at).split(/[._+-]+/).filter(Boolean);
  const label = words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  return { label: label || speaker, title: speaker };
}

/** Wall-clock time of the utterance (`at`, epoch seconds); older workers only send session-relative `start`. */
function clock(l: TranscriptLine) {
  if (l.at) return new Date(l.at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const m = Math.floor(l.start / 60);
  return `${String(m).padStart(2, "0")}:${String(Math.floor(l.start % 60)).padStart(2, "0")}`;
}
