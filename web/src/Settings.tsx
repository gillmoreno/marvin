import { useEffect, useState } from "react";
import { agent } from "./agent";
import { useIsAdmin } from "./auth";
import { AccountSection } from "./RoomSettings";
import { GitHubSection } from "./GitHubConnect";
import { HarnessSection } from "./HarnessConnect";
import { ThemeSection } from "./theme/ThemeSection";

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

type UpdateInfo = {
  short: string | null;
  latest_short: string | null;
  latest_message: string | null;
  ref: string;
  repo: string;
  behind: boolean;
  commits: { sha: string; message: string }[];
  can_apply: boolean;
  applying: boolean;
  last_error: string | null;
};

function UpdateSection() {
  const admin = useIsAdmin();
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () =>
    fetch("/api/update")
      .then(async (r) => {
        const j = await r.json();
        if (!r.ok) throw new Error(j.error ?? r.statusText);
        setInfo(j);
        setErr(null);
      })
      .catch((e) => setErr(String(e instanceof Error ? e.message : e)));
  useEffect(() => {
    if (!admin) return;
    void load();
    const t = window.setInterval(() => void load(), info?.applying ? 2000 : 30000);
    return () => window.clearInterval(t);
  }, [admin, info?.applying]);
  if (!admin) return null;
  const apply = async () => {
    if (!confirm("Update this machine? Everyone in every room is disconnected for a few minutes while images rebuild. Login passwords stay.")) return;
    setBusy(true);
    const r = await fetch("/api/update", { method: "POST" });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) { setErr(j.error ?? r.statusText); return; }
    void load();
  };
  return (
    <section>
      <h3>This machine</h3>
      {!info && !err && <p className="dim small">checking for updates…</p>}
      {info && (
        <>
          <p className="small">
            Running <code>{info.short ?? "unknown"}</code>
            {info.latest_short ? <> · {info.ref} is <code>{info.latest_short}</code></> : null}
            {info.latest_message ? <> — {info.latest_message}</> : null}
          </p>
          {info.behind && info.commits.length > 0 && (
            <ul className="small">
              {info.commits.map((c) => (
                <li key={c.sha}><code>{c.sha}</code> {c.message}</li>
              ))}
            </ul>
          )}
          {info.behind && info.can_apply && !info.applying && (
            <p className="dim small">Those commits are on GitHub and not on this VM yet. Update pulls them and rebuilds. Rooms drop until it is back.</p>
          )}
          {!info.behind && <p className="dim small">This machine is on the latest <code>{info.ref}</code>.</p>}
          {info.behind && !info.can_apply && (
            <p className="dim small">This copy cannot self-update (no appliance checkout). On a VM, Settings shows the button. From a shell: <code>make update</code>.</p>
          )}
          {info.applying && <p className="status ok">Updating… the page may stop responding; reload in a few minutes.</p>}
          <div className="btns">
            <button type="button" disabled={!info.behind || !info.can_apply || info.applying || busy} onClick={() => void apply()}>
              {busy || info.applying ? "updating…" : "update this machine"}
            </button>
          </div>
        </>
      )}
      {info?.last_error && <p className="status bad">{info.last_error}</p>}
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

export function SettingsPanel({ onClose, extra, room }: { onClose: () => void; extra?: React.ReactNode; room?: string }) {
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
          <HarnessSection />
          <GitHubSection />
          <AppPreviewsSection />
          <UpdateSection />
          <ThemeSection />
          <PowerSection />
        </div>
      </div>
    </div>
  );
}
