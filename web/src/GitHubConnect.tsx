import { useEffect, useRef, useState } from "react";
import { useIsAdmin, useMe } from "./auth";
import { LicenseLockReason, useEnterprise } from "./License";
import { Actions, Block, Button, Card, Field, Fields, Input, Lock, Steps, Text } from "./ui";

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
      <Text>
        OAuth App client id: <code title={status.client_id ?? ""}>{masked}</code> ({status.client_id_source === "env" ? "from the environment" : "set here"})
        {status.client_id_source !== "env" && <> · <a href="#" onClick={(e) => { e.preventDefault(); setOpen(true); }}>change</a></>}
      </Text>
    );
  }
  return (
    <Block title="OAuth App">
      <Text>Needed only for the device-code button. A pasted token does not need this.</Text>
      <Steps items={[
        { detail: <><a href="https://github.com/settings/developers" target="_blank" rel="noopener noreferrer">github.com/settings/developers</a> → OAuth Apps → <b>New OAuth App</b>.</> },
        { detail: <>Name <code>Marvin</code>; Homepage and callback: <code>{location.origin}</code>. Tick <b>Enable Device Flow</b>.</> },
        { detail: <>Copy the <b>Client ID</b>. Do not generate a client secret.</> },
      ]} />
      <Fields>
        <Field label="Client ID" wide>
          <Input type={show ? "text" : "password"} placeholder="Ov23li… or Iv1.…" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" spellCheck={false} />
        </Field>
      </Fields>
      <Actions>
        <Button variant="ghost" onClick={() => setShow((s) => !s)}>{show ? "Hide" : "Show"}</Button>
        <Button disabled={busy || value.trim().length < 8} onClick={() => void save(value)}>{busy ? "Saving…" : "Save"}</Button>
        {status.configured && <Button variant="ghost" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button>}
      </Actions>
      {err && <Text tone="bad">{err}</Text>}
    </Block>
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
      <div className="ui-stack">
        <Text>GitHub must show <b>this exact code</b>. The link already has it — do not type a different one.</Text>
        <button type="button" className="ui-code" onClick={() => { void navigator.clipboard?.writeText(flow.user_code).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1500); }); }}>{flow.user_code}{copied ? " · copied" : ""}</button>
        <Text><a href={flow.verification_uri} target="_blank" rel="noopener noreferrer">{flow.verification_uri}</a></Text>
        <Text>Waiting for approval · valid {Math.round(flow.expires_in / 60)} minutes.</Text>
        <Actions>
          <Button variant="ghost" onClick={() => { stop(); setFlow(null); setPat(true); }}>GitHub went blank</Button>
          <Button variant="ghost" onClick={() => { stop(); setFlow(null); }}>Cancel</Button>
        </Actions>
      </div>
    );
  }
  if (pat) {
    const machine = dest === "machine";
    return (
      <div className="ui-stack">
        <Text>
          A fine-grained personal access token. {machine
            ? "This is the shared account the machine uses to clone, push, and open pull requests."
            : "Only if you want your name on the git author line. Skip this otherwise."}
        </Text>
        <Steps items={[
          { detail: <><a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener noreferrer">github.com/settings/personal-access-tokens/new</a> — or GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → <b>Generate new token</b>.</> },
          { detail: <>Name it <code>Marvin</code>. Resource owner: you, or the organization that owns the repos.</> },
          { detail: <>Repository access: <b>Only select repositories</b>, then pick {machine ? "the repos this machine will touch" : "the repos you want your name on"}.</> },
          { detail: <>Permissions → Repository: <b>Contents</b> Read and write, <b>Pull requests</b> Read and write. Generate.</> },
          { detail: <>Copy the <code>github_pat_…</code> string and paste it here. GitHub shows it once.</> },
        ]} />
        <Text>A classic token from <a href="https://github.com/settings/tokens/new" target="_blank" rel="noopener noreferrer">github.com/settings/tokens/new</a> with the <code>repo</code> scope also works.</Text>
        <Fields>
          <Field label="Token" wide>
            <Input type="password" placeholder="github_pat_… or ghp_…" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" spellCheck={false} />
          </Field>
        </Fields>
        <Actions>
          <Button disabled={busy || token.trim().length < 20} onClick={() => void savePat()}>{busy ? "Saving…" : "Save token"}</Button>
          <Button variant="ghost" onClick={() => setPat(false)}>Cancel</Button>
        </Actions>
        {err && <Text tone="bad">{err}</Text>}
      </div>
    );
  }
  return (
    <Actions>
      {configured && <Button disabled={busy} onClick={() => void start()}>{dest === "machine" ? "Connect this machine" : "Use my GitHub"}</Button>}
      <Button variant="ghost" disabled={busy} onClick={() => setPat(true)}>Paste a token</Button>
      {err && <Text tone="bad">{err}</Text>}
    </Actions>
  );
}

export function GitHubSection() {
  const me = useMe();
  const admin = useIsAdmin();
  const ent = useEnterprise();
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
    <Card>
      <h3>GitHub</h3>
      {status === null && !err && <Text>Checking…</Text>}
      {status && admin && <ClientIdSetup status={status} onSaved={(s) => { setStatus(s); setErr(null); }} />}
      {status && (
        <>
          <Block title="This machine">
            <Text>
              {machine
                ? <>{machine.login ? <>@{machine.login} · </> : null}{machine.source === "env" ? "from the environment" : machine.source === "app" ? "GitHub App" : "set here"}</>
                : "Not set."}
            </Text>
            {admin && (
              <Lock on={!ent.ee} reason={<LicenseLockReason />}>
                <Text>
                  <a href="#" onClick={(e) => { e.preventDefault(); void startApp(); }}>Create a GitHub App for this machine</a>
                  {status.app?.configured ? <> · app {status.app.slug || "ready"}{status.app.installed ? ", installed" : " — install it on the org after GitHub redirects"}</> : null}
                  . A pasted PAT still works.
                </Text>
              </Lock>
            )}
            {admin && status.signing_key && (
              <>
                <Text>Commit signing key — upload to the GitHub App for Verified commits.</Text>
                <code className="ui-code">{status.signing_key}</code>
              </>
            )}
            {admin && !machine?.login && machine?.source !== "env" && (
              <GitHubAuth dest="machine" configured={status.configured} onDone={() => void load()} />
            )}
            {admin && machine && machine.source !== "env" && (
              <Actions>
                <Button variant="ghost" onClick={() => void forgetMachine()}>Clear machine account</Button>
              </Actions>
            )}
          </Block>
          <Block title="Your GitHub">
            <Text>
              Optional. {status.connected ? <>Connected as @{status.connected.login}.</> : <>Turns use the machine account. Logged in as {you}.</>}
            </Text>
            {status.connected
              ? <Actions><Button variant="ghost" onClick={() => void forgetPersonal()}>Use the machine account</Button></Actions>
              : <GitHubAuth dest="user" configured={status.configured} onDone={() => void load()} />}
          </Block>
        </>
      )}
      {err && <Text tone="bad">{err}</Text>}
    </Card>
  );
}
