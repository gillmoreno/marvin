import { useEffect, useRef, useState } from "react";
import { useIsAdmin } from "./auth";

/** Settings → Coding agents: which model provider this machine talks to, set here, not in .env.
 *  API key paste for every vendor; Grok also has "Sign in with Grok" (device flow, your grok.com subscription). */

export type Provider = {
  id: string; label: string; env: string; harnesses: string[]; console_url: string; steps: string[];
  key_prefix: string; note: string; subscription: string | null;
  key_set: boolean; key_source: "env" | "settings" | null; key_hint: string | null;
  subscription_set: boolean;
};
export type Harness = { id: string; label: string };
export type Status = { providers: Provider[]; default_harness: string; default_source: "env" | "settings" | "builtin"; harnesses: Harness[] };
type Flow = { flow: string; user_code: string; verification_uri: string; expires_in: number; status: string; error?: string | null };

export function KeyForm({ p, onSaved }: { p: Provider; onSaved: (s: Status) => void }) {
  const [open, setOpen] = useState(!p.key_set);
  const [value, setValue] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await fetch(`/api/harness-creds/${p.id}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: value }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      onSaved(j); setValue(""); setOpen(false);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const clear = async () => {
    if (!confirm(`Forget the ${p.label} key stored here?`)) return;
    setBusy(true);
    try {
      const r = await fetch(`/api/harness-creds/${p.id}`, { method: "DELETE" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      onSaved(j); setOpen(true);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  if (p.key_source === "env" && !open) {
    return <p className="dim small">API key: <code>{p.key_hint}</code> (from the environment)</p>;
  }
  if (p.key_set && !open) {
    return (
      <p className="dim small">
        API key: <code>{p.key_hint}</code> (set here)
        {p.key_source !== "env" && <> · <a href="#" onClick={(e) => { e.preventDefault(); setOpen(true); }}>change</a> · <a href="#" onClick={(e) => { e.preventDefault(); void clear(); }}>forget</a></>}
      </p>
    );
  }
  return (
    <div className="github-setup">
      <ol className="dim small">
        {p.steps.map((s) => (
          <li key={s}>{s === p.steps[0] ? <><a href={p.console_url} target="_blank" rel="noopener noreferrer">{p.console_url.replace(/^https:\/\//, "")}</a> — {s.replace(/^Open [^.]+\. /, "")}</> : s}</li>
        ))}
      </ol>
      <div className="row">
        <input type={show ? "text" : "password"} placeholder={p.key_prefix ? `${p.key_prefix}…` : "API key"} value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" spellCheck={false} />
        <button className="ghost" type="button" onClick={() => setShow((s) => !s)}>{show ? "hide" : "show"}</button>
        <button disabled={busy || value.trim().length < 12} onClick={() => void save()}>save</button>
        {p.key_set && <button className="ghost" disabled={busy} onClick={() => setOpen(false)}>cancel</button>}
      </div>
      {err && <p className="error small">{err}</p>}
    </div>
  );
}

export function GrokLogin({ onSaved }: { onSaved: (s: Status) => void }) {
  const [flow, setFlow] = useState<Flow | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);
  const stop = () => { if (timer.current) { window.clearInterval(timer.current); timer.current = null; } };
  useEffect(() => () => stop(), []);
  const start = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await fetch("/api/harness-creds/grok/login", { method: "POST" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      const f = j as Flow;
      setFlow(f);
      window.open(f.verification_uri, "_blank", "noopener");
      stop();
      timer.current = window.setInterval(async () => {
        try {
          const s = await fetch(`/api/harness-creds/grok/login/${f.flow}`).then((x) => x.json()) as Flow;
          if (s.status === "connected") {
            stop(); setFlow(null);
            const st = await fetch("/api/harness-creds").then((x) => x.json());
            onSaved(st);
          } else if (s.status === "error") { stop(); setFlow(null); setErr(s.error ?? "login failed"); }
        } catch { /* worker briefly unreachable */ }
      }, 2500);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const copy = () => { if (flow) void navigator.clipboard?.writeText(flow.user_code).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1500); }); };
  if (flow) {
    return (
      <div className="github-flow">
        <p className="small">Enter this code on Grok (a tab should have opened; if not, use the link):</p>
        <div className="github-code" onClick={copy} title="click to copy">{flow.user_code || "…"}{copied ? <span className="dim small"> copied</span> : null}</div>
        <p className="small"><a href={flow.verification_uri} target="_blank" rel="noopener noreferrer">{flow.verification_uri}</a></p>
        <p className="dim small">Waiting for you to approve… the code is valid for {Math.max(1, Math.round(flow.expires_in / 60))} minutes.</p>
        <div className="btns"><button type="button" className="ghost" onClick={() => { stop(); setFlow(null); }}>cancel</button></div>
      </div>
    );
  }
  return (
    <>
      <div className="btns"><button type="button" className="primary" disabled={busy} onClick={() => void start()}>{busy ? "starting…" : "Sign in with Grok"}</button></div>
      {err && <p className="error small">{err}</p>}
    </>
  );
}

export function HarnessSection() {
  const admin = useIsAdmin();
  const [status, setStatus] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => fetch("/api/harness-creds").then((r) => r.json()).then((j) => { if (j.error) setErr(j.error); else { setStatus(j); setErr(null); } }).catch(() => {});
  useEffect(() => { if (admin) void load(); }, [admin]);
  if (!admin) {
    return (
      <section className="coding-agents">
        <h3>Coding agents</h3>
        <p className="dim small">An admin connects Claude, Grok, Codex and the others from this panel. Nothing goes in a <code>.env</code> file.</p>
      </section>
    );
  }
  const setDefault = async (id: string) => {
    const r = await fetch("/api/harness-creds/default", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ harness: id }) });
    const j = await r.json();
    if (r.ok) setStatus(j); else setErr(j.error ?? r.statusText);
  };
  const disconnectGrok = async () => {
    if (!confirm("Disconnect the Grok subscription on this machine?")) return;
    const r = await fetch("/api/harness-creds/grok/login", { method: "DELETE" });
    const j = await r.json();
    if (r.ok) setStatus(j); else setErr(j.error ?? r.statusText);
  };
  return (
    <section className="coding-agents">
      <h3>Coding agents</h3>
      <p className="dim small">Who Marvin talks to. Set it here — a key or a subscription — not in an environment file. Rooms without a pinned harness use the default.</p>
      {status === null && !err && <p className="dim small">checking…</p>}
      {status && (
        <>
          <label className="small">
            Default agent
            <select value={status.default_harness === "claude-code" ? "" : status.default_harness} disabled={status.default_source === "env"} onChange={(e) => void setDefault(e.target.value)}>
              <option value="">Claude Code (built-in default)</option>
              {status.harnesses.filter((h) => h.id !== "claude-code").map((h) => <option key={h.id} value={h.id}>{h.label}</option>)}
            </select>
          </label>
          {status.default_source === "env" && <p className="dim small">Default is <code>MARVIN_HARNESS</code> from the environment.</p>}
          <p className="dim small">OpenCode uses whichever of the keys above it is configured for; there is no separate OpenCode secret.</p>
          <div className="providers">
            {status.providers.map((p) => (
              <div className="provider" key={p.id}>
                <p className="small"><b>{p.label}</b> <span className="dim">· {p.harnesses.join(", ")}</span></p>
                {p.note && <p className="dim small">{p.note}</p>}
                {p.subscription === "grok" && (
                  p.subscription_set
                    ? <p className="small">Grok subscription: <b>signed in</b> · <a href="#" onClick={(e) => { e.preventDefault(); void disconnectGrok(); }}>disconnect</a></p>
                    : <GrokLogin onSaved={setStatus} />
                )}
                <KeyForm p={p} onSaved={setStatus} />
              </div>
            ))}
          </div>
        </>
      )}
      {err && <p className="error small">{err}</p>}
    </section>
  );
}
