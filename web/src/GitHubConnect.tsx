import { useEffect, useRef, useState } from "react";
import { useMe } from "./auth";

/** Settings -> GitHub: connect the signed-in person's GitHub account through the device flow, no terminal involved.
 *  The worker starts the flow (POST /api/github/connect) and polls GitHub; we show the code, open github.com/login/device
 *  and poll the worker until it says "connected". Commits and PRs made in a room during that person's turns then carry
 *  their identity. */

type Connected = { login: string; name: string; email: string; scopes: string; connected_at: number };
type Status = { configured: boolean; connected: Connected | null; machine_identity: boolean };
type Flow = { flow: string; user_code: string; verification_uri: string; expires_in: number; interval: number };

export function GitHubSection() {
  const me = useMe();
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
      {status && !status.configured && (
        <p className="dim small">
          Not set up on this machine yet: the operator needs to set <code>MARVIN_GITHUB_CLIENT_ID</code> (an OAuth App with device flow enabled, see{" "}
          <code>docs_and_changelog/github.md</code>). Until then rooms {status.machine_identity ? "use this machine's GITHUB_TOKEN" : "use whatever git credentials the machine has"}.
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
