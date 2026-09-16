import { useEffect, useState } from "react";
import { agent } from "./agent";
import { useIsAdmin } from "./auth";
import { AccountSection } from "./RoomSettings";
import { GitHubSection } from "./GitHubConnect";
import { HarnessSection } from "./HarnessConnect";
import { AccessSection } from "./AccessSection";
import { ExportSection, SessionsSection } from "./Sessions";
import { MachineUpdate } from "./MachineUpdate";

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

type LicenseInfo = {
  valid: boolean;
  reason: string | null;
  message: string;
  company: string | null;
  seats: number | null;
  expires_at: number | null;
  features: string[];
  source: "env" | "settings" | null;
  has_key: boolean;
  ee: boolean;
};

function LicenseSection() {
  const admin = useIsAdmin();
  const [info, setInfo] = useState<LicenseInfo | null>(null);
  const [key, setKey] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () =>
    fetch("/api/license")
      .then(async (r) => {
        const j = await r.json();
        if (!r.ok) throw new Error(j.error ?? r.statusText);
        setInfo(j);
        setErr(null);
      })
      .catch((e) => setErr(String(e instanceof Error ? e.message : e)));
  useEffect(() => { if (admin) void load(); }, [admin]);
  if (!admin) return null;
  const save = async () => {
    setBusy(true); setErr(null);
    const r = await fetch("/api/license", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ key }) });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) { setErr(j.error ?? r.statusText); return; }
    setKey("");
    setInfo(j);
  };
  const clear = async () => {
    if (!confirm("Remove the license key from this machine? Enterprise features turn off. The free core stays.")) return;
    setBusy(true); setErr(null);
    const r = await fetch("/api/license", { method: "DELETE" });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) { setErr(j.error ?? r.statusText); return; }
    setInfo(j);
  };
  const fromEnv = info?.source === "env";
  return (
    <section>
      <h3>Enterprise</h3>
      {info?.valid ? (
        <>
          <p className="small">{info.message}{info.source === "env" ? " · from the environment" : " · set here"}.</p>
          <p className="dim small">Enterprise features are on for this machine. The key stays on this box; Marvin does not call home.
            {info.features.length > 0 && info.features[0] !== "*" ? <> On: {info.features.join(", ")}.</> : null}
          </p>
        </>
      ) : (
        <>
          <p className="small">{info?.has_key ? info.message : "This machine is the free core. Anyone can run it."}</p>
          <p className="dim small">A paid subscription is only for the compliance pack (SSO, audit, isolation). You get a license string from us; paste it here. No restart.</p>
        </>
      )}
      {!fromEnv && (
        <div className="github-setup">
          <textarea rows={3} placeholder="eyJ… (the license string)" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" spellCheck={false} />
          <div className="row">
            <button type="button" disabled={busy || key.trim().length < 20} onClick={() => void save()}>{busy ? "saving…" : "save license"}</button>
            {info?.source === "settings" && <button type="button" className="ghost" disabled={busy} onClick={() => void clear()}>remove</button>}
          </div>
        </div>
      )}
      {fromEnv && <p className="dim small">License is <code>MARVIN_LICENSE_KEY</code> from the environment.</p>}
      {err && <p className="error small">{err}</p>}
    </section>
  );
}

function AppPreviewsSection() {
  const admin = useIsAdmin();
  const [pattern, setPattern] = useState<string | null>(null);
  const [host, setHost] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/agent").then((r) => r.json()).then((j) => {
      setHost(typeof j.public_host === "string" ? j.public_host : null);
      setPattern(typeof j.preview_pattern === "string" ? j.preview_pattern : null);
    }).catch(() => {});
  }, []);
  if (!admin) return null;
  return (
    <section>
      <h3>App previews</h3>
      {pattern && host ? (
        <>
          <p className="small">This machine is <code>{host}</code>. A port the agent opens is <code>{pattern}</code> — so port 3000 is <code>{pattern.replace("{port}", "3000")}</code>.</p>
          <p className="dim small">
            DNS: an A record for <code>{host}</code> and for <code>*.{host}</code>, both pointing at this VM, DNS-only (not proxied).
            The name is this install&apos;s hostname (<code>MARVIN_DOMAIN</code>), not a Marvin-wide domain.
          </p>
        </>
      ) : (
        <p className="dim small">No public hostname on this machine, so previews are <code>http://localhost:&lt;port&gt;</code>. Set <code>MARVIN_DOMAIN</code> (and a <code>*.that-name</code> DNS record) for HTTPS links other people can open.</p>
      )}
    </section>
  );
}

export function SettingsPanel({ onClose, extra, room, focus }: { onClose: () => void; extra?: React.ReactNode; room?: string; focus?: string }) {
  const admin = useIsAdmin();
  useEffect(() => {
    if (!focus) return;
    const frame = requestAnimationFrame(() => document.getElementById(focus)?.scrollIntoView({ block: "start" }));
    return () => cancelAnimationFrame(frame);
  }, [focus]);
  return (
    <div className="modal-back settings-screen" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <span className="lbl">settings</span>
          <h2>{agent.name}{room ? <> <span className="room">#{room}</span></> : <> · this machine</>}</h2>
          <span className="sp" />
          <button className="ghost" onClick={onClose}>close</button>
        </header>
        <div className="sgrid">
          {extra}
          <AccountSection />
          <AccessSection />
          <HarnessSection />
          <GitHubSection />
          <SessionsSection />
          <ExportSection />
          <AppPreviewsSection />
          <LicenseSection />
          {admin && <section className="settings-update"><h3>This machine</h3><MachineUpdate /></section>}
          <PowerSection />
        </div>
      </div>
    </div>
  );
}
