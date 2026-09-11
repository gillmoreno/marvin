import { useEffect, useState } from "react";
import { agent } from "./agent";
import { AccountSection } from "./RoomSettings";

/** Sleep the whole machine (scale to zero). Only meaningful on the cluster, where /power is served by the gate. */
export function PowerSection() {
  const [state, setState] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    fetch("/power/status").then((r) => (r.ok ? r.json() : null)).then((j) => setState(j?.state ?? null)).catch(() => setState(null));
  }, []);
  if (state === null) return null; // no gate here (local dev)
  async function sleep() {
    if (!confirm(`Put ${agent.name} to sleep? Everyone in every room gets disconnected. The machine wakes from the same URL, or on the morning schedule.`)) return;
    const r = await fetch("/power/sleep", { method: "POST" });
    setMsg(r.ok ? "Going to sleep. This page will stop responding in a moment." : "Could not sleep: " + r.statusText);
  }
  return (
    <section>
      <h3>Machine power</h3>
      <p className="dim small">State: <b>{state}</b>. Sleeping scales everything to zero (volumes stay), which drops the GPU node and its cost. The URL then shows a Wake button.</p>
      <div className="btns"><button className="danger" onClick={() => void sleep()}>put {agent.name} to sleep</button></div>
      {msg && <p className="status ok">{msg}</p>}
    </section>
  );
}

export function SettingsPanel({ onClose, extra }: { onClose: () => void; extra?: React.ReactNode }) {
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Settings · this machine</h2>
          <button className="ghost" onClick={onClose}>close</button>
        </header>
        {extra}
        <AccountSection />
        <PowerSection />
      </div>
    </div>
  );
}
