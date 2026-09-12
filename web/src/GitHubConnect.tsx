import { useEffect, useRef, useState } from "react";
import { useIsAdmin, useMe } from "./auth";

/** Settings -> GitHub: connect the signed-in person's GitHub account through the device flow, no terminal involved.
 *  The worker starts the flow (POST /api/github/connect) and polls GitHub; we show the code, open github.com/login/device
 *  and poll the worker until it says "connected". Commits and PRs made in a room during that person's turns then carry
 *  their identity. */

type Connected = { login: string; name: string; email: string; scopes: string; connected_at: number };
type Status = { configured: boolean; connected: Connected | null; machine_identity: boolean; client_id?: string | null; client_id_source?: "env" | "settings" | null };
type Flow = { flow: string; user_code: string; verification_uri: string; expires_in: number; interval: number };

/** Admin-only: the OAuth App client id, set once per machine from here (or MARVIN_GITHUB_CLIENT_ID in the environment). */
function ClientIdSetup({ status, onSaved }: { status: Status; onSaved: (s: Status) => void }) {
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
      <p className="small">
        <b>One-time setup (admin).</b> Register an OAuth App on GitHub and paste its client id here; nobody else needs to do anything.
      </p>
      <ol className="dim small">
        <li><a href="https://github.com/settings/developers" target="_blank" rel="noopener noreferrer">github.com/settings/developers</a> → OAuth Apps → <b>New OAuth App</b> (for a company: under the organization's settings).</li>
        <li>Name <code>Marvin</code>; Homepage and callback URL: this page's address (<code>{location.origin}</code>). Tick <b>Enable Device Flow</b>. Register.</li>
        <li>Copy the <b>Client ID</b>. Do not generate a client secret.</li>
      </ol>
      <div className="row">
        <input type={show ? "text" : "password"} placeholder="Client ID (Ov23li… or Iv1.…)" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" spellCheck={false} />
        <button className="ghost" type="button" onClick={() => setShow((s) => !s)}>{show ? "hide" : "show"}</button>
        <button disabled={busy || value.trim().length < 8} onClick={() => void save(value)}>save</button>
        {status.configured && <button className="ghost" disabled={busy} onClick={() => setOpen(false)}>cancel</button>}
      </div>
      <p className="dim small">The client id is a public identifier (GitHub shows it in every OAuth URL), not a secret; it is masked here out of habit. Stored in the worker's state directory.</p>
      {err && <p className="error small">{err}</p>}
    </div>
  );
}

export function GitHubSection() {
  const me = useMe();
  const admin = useIsAdmin();
  const [status, setStatus] = useState<Status | null>(null);
  const [flow, setFlow] = useState<Flow | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);

  const load = (verify = false) =>
    fetch(`/api/github/me${verify ? "?verify=1" : ""}`).then((r) => r.json()).then((j: Status & { error?: string }) => {
      if (j.error) setErr(j.error); else setStatus(j);
    }).catch(() => {});

  useEffect(() => { void load(true); return () => { if (timer.current) window.clearInterval(timer.current); }; }, []);

  const start = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await fetch("/api/github/connect", { method: "POST" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      const f = j as Flow;
      setFlow(f);
      window.open(f.verification_uri, "_blank", "noopener");
      if (timer.current) window.clearInterval(timer.current);
      timer.current = window.setInterval(async () => {
        try {
          const s = await fetch(`/api/github/connect/${f.flow}`).then((x) => x.json());
          if (s.status === "connected") { stop(); setFlow(null); await load(); }
          else if (s.status === "error") { stop(); setFlow(null); setErr(s.error ?? "connection failed"); }
        } catch { /* worker briefly unreachable: keep polling */ }
      }, Math.max(2, f.interval) * 1000);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const stop = () => { if (timer.current) { window.clearInterval(timer.current); timer.current = null; } };
  const cancel = () => { stop(); setFlow(null); };
  const disconnect = async () => {
    if (!confirm("Disconnect GitHub? Rooms fall back to this machine's identity for your turns.")) return;
    setBusy(true);
    try { const j = await fetch("/api/github/me", { method: "DELETE" }).then((r) => r.json()); if (!j.error) setStatus(j); else setErr(j.error); }
    finally { setBusy(false); }
  };
  const copy = () => { if (flow) void navigator.clipboard?.writeText(flow.user_code).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1500); }); };

  const you = me.identity?.name ?? "you";
  return (
    <section>
      <h3>GitHub</h3>
      {status === null && !err && <p className="dim small">checking…</p>}
      {status && admin && <ClientIdSetup status={status} onSaved={(s) => { setStatus(s); setErr(null); }} />}
      {status && !status.configured && !admin && (
        <p className="dim small">
          Not set up on this machine yet: an admin needs to register the OAuth App in Settings → GitHub (or set <code>MARVIN_GITHUB_CLIENT_ID</code>).
          Until then rooms {status.machine_identity ? "use this machine's GITHUB_TOKEN" : "use whatever git credentials the machine has"}.
        </p>
      )}
      {status?.configured && status.connected && !flow && (
        <>
          <p className="small">
            Connected as <b>@{status.connected.login}</b>{status.connected.name && status.connected.name !== status.connected.login ? ` (${status.connected.name})` : ""} · {status.connected.email}
          </p>
          <p className="dim small">When you ({you}) ask Marvin to commit, push or open a PR, it happens as @{status.connected.login}.</p>
          <div className="btns"><button className="ghost" disabled={busy} onClick={() => void disconnect()}>disconnect</button></div>
        </>
      )}
      {status?.configured && !status.connected && !flow && (
        <>
          <p className="dim small">
            Not connected. Rooms currently commit as {status.machine_identity ? "this machine's shared GitHub identity" : "whatever git identity this machine has"}.
            Connect your account so Marvin's commits and pull requests are yours.
          </p>
          <div className="btns"><button className="primary" disabled={busy} onClick={() => void start()}>Connect GitHub</button></div>
        </>
      )}
      {flow && (
        <div className="github-flow">
          <p className="small">Enter this code on GitHub (a tab should have opened; if not, use the link):</p>
          <div className="github-code" onClick={copy} title="click to copy">{flow.user_code}{copied ? <span className="dim small"> copied</span> : null}</div>
          <p className="small"><a href={flow.verification_uri} target="_blank" rel="noopener noreferrer">{flow.verification_uri}</a></p>
          <p className="dim small">Waiting for you to approve on GitHub… the code is valid for {Math.round(flow.expires_in / 60)} minutes.</p>
          <div className="btns"><button className="ghost" onClick={cancel}>cancel</button></div>
        </div>
      )}
      {err && <p className="error small">{err}</p>}
    </section>
  );
}
