import { useEffect, useRef, useState } from "react";
import { useIsAdmin, useMe } from "./auth";

/** Machine GitHub (required, admin) plus optional personal GitHub. Device flow or a pasted PAT. */

export type Connected = { login: string; name: string; email: string; scopes: string; connected_at: number };
export type Machine = Connected & { source: "env" | "settings" | "app"; login: string | null };
export type Status = {
  configured: boolean; connected: Connected | null; machine_identity: boolean; machine?: Machine | null;
  client_id?: string | null; client_id_source?: "env" | "settings" | null;
  app?: { id: string | null; slug: string | null; installed: boolean; configured: boolean };
  signing_key?: string | null;
};

/** Manifest POST to github.com/settings/apps/new. Needs an Enterprise license. */
export async function startGitHubApp(): Promise<string | null> {
  const r = await fetch(`/api/github/app?origin=${encodeURIComponent(location.origin)}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) return (j as { error?: string }).error ?? r.statusText;
  const f = document.createElement("form");
  f.method = "POST";
  f.action = "https://github.com/settings/apps/new";
  const i = document.createElement("input");
  i.type = "hidden";
  i.name = "manifest";
  i.value = JSON.stringify((j as { manifest: unknown }).manifest);
  f.appendChild(i);
  document.body.appendChild(f);
  f.submit();
  return null;
}
type Flow = { flow: string; user_code: string; verification_uri: string; expires_in: number; interval: number };

export function ClientIdSetup({ status, onSaved }: { status: Status; onSaved: (s: Status) => void }) {
  const [open, setOpen] = useState(!status.configured);
  const [value, setValue] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const save = async (cid: string) => {
    setBusy(true); setErr(null);
    try {
      const r = await fetch("/api/github/config", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ client_id: cid }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      onSaved(j); setValue(""); setOpen(false);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const masked = status.client_id ? status.client_id.slice(0, 4) + "•".repeat(Math.max(4, status.client_id.length - 8)) + status.client_id.slice(-4) : "";
  if (!open) {
    return (
      <p className="dim small">
        OAuth App client id: <code title={status.client_id ?? ""}>{masked}</code> ({status.client_id_source === "env" ? "from the environment" : "set here"})
        {status.client_id_source !== "env" && <> · <a href="#" onClick={(e) => { e.preventDefault(); setOpen(true); }}>change</a></>}
      </p>
    );
  }
  return (
    <div className="github-setup">
      <p className="small">Needed only for the device-code button. A pasted token does not need this.</p>
      <ol className="dim small">
        <li><a href="https://github.com/settings/developers" target="_blank" rel="noopener noreferrer">github.com/settings/developers</a> → OAuth Apps → <b>New OAuth App</b>.</li>
        <li>Name <code>Marvin</code>; Homepage and callback: <code>{location.origin}</code>. Tick <b>Enable Device Flow</b>.</li>
        <li>Copy the <b>Client ID</b>. Do not generate a client secret.</li>
      </ol>
      <div className="row">
        <input type={show ? "text" : "password"} placeholder="Client ID (Ov23li… or Iv1.…)" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" spellCheck={false} />
        <button className="ghost" type="button" onClick={() => setShow((s) => !s)}>{show ? "hide" : "show"}</button>
        <button type="button" disabled={busy || value.trim().length < 8} onClick={() => void save(value)}>save</button>
        {status.configured && <button type="button" className="ghost" disabled={busy} onClick={() => setOpen(false)}>cancel</button>}
      </div>
      {err && <p className="error small">{err}</p>}
    </div>
  );
}

/** Device flow or PAT paste. dest=machine stores the shared account (admin). */
export function GitHubAuth({ dest, configured, onDone }: { dest: "user" | "machine"; configured: boolean; onDone: () => void }) {
  const [flow, setFlow] = useState<Flow | null>(null);
  const [pat, setPat] = useState(false);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);
  const stop = () => { if (timer.current) { window.clearInterval(timer.current); timer.current = null; } };
  useEffect(() => () => stop(), []);

  const start = async () => {
    setErr(null); setBusy(true);
    try {
      const q = dest === "machine" ? "?dest=machine" : "";
      const r = await fetch(`/api/github/connect${q}`, { method: "POST" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      const f = j as Flow;
      setFlow(f);
      window.open(f.verification_uri, "_blank", "noopener");
      stop();
      timer.current = window.setInterval(async () => {
        try {
          const s = await fetch(`/api/github/connect/${f.flow}`).then((x) => x.json());
          if (s.status === "connected") { stop(); setFlow(null); onDone(); }
          else if (s.status === "error") { stop(); setFlow(null); setErr(s.error ?? "connection failed"); }
        } catch { /* keep polling */ }
      }, Math.max(2, f.interval) * 1000);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const savePat = async () => {
    setBusy(true); setErr(null);
    try {
      const url = dest === "machine" ? "/api/github/machine" : "/api/github/me";
      const r = await fetch(url, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ token }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      setToken(""); setPat(false); onDone();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  if (flow) {
    return (
      <div className="github-flow">
        <p className="small">GitHub must show <b>this exact code</b>. The link already has it — do not type a different one.</p>
        <div className="github-code" onClick={() => { void navigator.clipboard?.writeText(flow.user_code).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1500); }); }}>{flow.user_code}{copied ? <span className="dim small"> copied</span> : null}</div>
        <p className="small"><a href={flow.verification_uri} target="_blank" rel="noopener noreferrer">{flow.verification_uri}</a></p>
        <p className="dim small">Waiting for approval · valid {Math.round(flow.expires_in / 60)} minutes.</p>
        <div className="btns">
          <button type="button" className="ghost" onClick={() => { stop(); setFlow(null); setPat(true); }}>GitHub went blank</button>
          <button type="button" className="ghost" onClick={() => { stop(); setFlow(null); }}>cancel</button>
        </div>
      </div>
    );
  }
  if (pat) {
    return (
      <div className="github-setup">
        <p className="small">Fine-grained PAT. {dest === "machine" ? "The repos this machine will touch." : "Your repos, if you want your name on commits."} Contents read/write, pull requests.</p>
        <div className="row">
          <input type="password" placeholder="github_pat_… or ghp_…" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" spellCheck={false} />
          <button type="button" disabled={busy || token.trim().length < 20} onClick={() => void savePat()}>save token</button>
          <button type="button" className="ghost" onClick={() => setPat(false)}>cancel</button>
        </div>
        {err && <p className="error small">{err}</p>}
      </div>
    );
  }
  return (
    <div className="btns">
      {configured && <button type="button" className="primary" disabled={busy} onClick={() => void start()}>{dest === "machine" ? "Connect this machine" : "Use my GitHub"}</button>}
      <button type="button" className="ghost" disabled={busy} onClick={() => setPat(true)}>paste a token</button>
      {err && <p className="error small">{err}</p>}
    </div>
  );
}

export function GitHubSection() {
  const me = useMe();
  const admin = useIsAdmin();
  const [status, setStatus] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = (verify = false) =>
    fetch(`/api/github/me${verify ? "?verify=1" : ""}`).then((r) => r.json()).then((j: Status & { error?: string }) => {
      if (j.error) setErr(j.error); else setStatus(j);
    }).catch(() => {});
  useEffect(() => { void load(true); }, []);

  const forgetPersonal = async () => {
    if (!confirm("Stop using your GitHub? Your turns will use the machine account.")) return;
    const j = await fetch("/api/github/me", { method: "DELETE" }).then((r) => r.json());
    if (!j.error) setStatus(j); else setErr(j.error);
  };
  const forgetMachine = async () => {
    if (!confirm("Remove the machine GitHub account? Join will lock until an admin connects one again.")) return;
    const j = await fetch("/api/github/machine", { method: "DELETE" }).then((r) => r.json());
    if (!j.error) setStatus(j); else setErr(j.error);
  };

  const startApp = async () => {
    const error = await startGitHubApp();
    if (error) setErr(error);
  };
  const you = me.identity?.email ?? me.identity?.name ?? "you";
  const machine = status?.machine;
  return (
    <section>
      <h3>GitHub</h3>
      {status === null && !err && <p className="dim small">checking…</p>}
      {status && admin && <ClientIdSetup status={status} onSaved={(s) => { setStatus(s); setErr(null); }} />}
      {status && (
        <>
          <p className="small"><b>This machine</b> {machine ? <>· {machine.login ? <>@{machine.login} </> : null}({machine.source === "env" ? "from the environment" : machine.source === "app" ? "GitHub App" : "set here"})</> : <span className="dim">· not set</span>}</p>
          {admin && (
            <p className="dim small">
              <a href="#" onClick={(e) => { e.preventDefault(); void startApp(); }}>Create a GitHub App for this machine</a>
              {status.app?.configured ? <> · app {status.app.slug || "ready"}{status.app.installed ? ", installed" : " — install it on the org after GitHub redirects"}</> : null}
              . A pasted PAT still works.
            </p>
          )}
          {admin && status.signing_key && (
            <p className="dim small">Commit signing key (upload to the GitHub App for Verified): <code style={{ wordBreak: "break-all" }}>{status.signing_key}</code></p>
          )}
          {admin && !machine?.login && machine?.source !== "env" && (
            <GitHubAuth dest="machine" configured={status.configured} onDone={() => void load()} />
          )}
          {admin && machine && machine.source !== "env" && <p className="dim small"><a href="#" onClick={(e) => { e.preventDefault(); void forgetMachine(); }}>clear machine account</a></p>}
          <p className="small" style={{ marginTop: 10 }}>
            <b>Your GitHub</b> <span className="dim">optional</span>
            {status.connected ? <> · @{status.connected.login}</> : <> · turns use the machine account. Logged in as {you}.</>}
          </p>
          {status.connected
            ? <div className="btns"><button type="button" className="ghost" onClick={() => void forgetPersonal()}>use the machine account</button></div>
            : <GitHubAuth dest="user" configured={status.configured} onDone={() => void load()} />}
        </>
      )}
      {err && <p className="error small">{err}</p>}
    </section>
  );
}
