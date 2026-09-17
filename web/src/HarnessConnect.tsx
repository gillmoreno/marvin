import { useEffect, useRef, useState } from "react";
import { useIsAdmin } from "./auth";
import { Actions, Block, Button, Card, Field, Fields, Input, Select, Steps, Text } from "./ui";

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

const SHORT: Record<string, string> = {
  anthropic: "Claude",
  xai: "Grok",
  openai: "Codex",
  google: "Gemini",
  cursor: "Cursor",
  copilot: "Copilot",
};

function shortLabel(p: Provider) {
  return SHORT[p.id] ?? p.label;
}

function isConnected(p: Provider) {
  return p.key_set || p.subscription_set;
}

export function KeyForm({ p, onSaved, startOpen }: { p: Provider; onSaved: (s: Status) => void; startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen ?? !p.key_set);
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
    return <Text>API key: <code>{p.key_hint}</code> (from the environment)</Text>;
  }
  if (p.key_set && !open) {
    return (
      <Text>
        API key: <code>{p.key_hint}</code> (set here)
        {p.key_source !== "env" && <> · <a href="#" onClick={(e) => { e.preventDefault(); setOpen(true); }}>change</a> · <a href="#" onClick={(e) => { e.preventDefault(); void clear(); }}>forget</a></>}
      </Text>
    );
  }
  return (
    <div className="ui-stack">
      <Steps items={p.steps.map((s) => ({
        detail: s === p.steps[0]
          ? <><a href={p.console_url} target="_blank" rel="noopener noreferrer">{p.console_url.replace(/^https:\/\//, "")}</a> — {s.replace(/^Open [^.]+\. /, "")}</>
          : s,
      }))} />
      <Fields>
        <Field label="API key" wide>
          <Input type={show ? "text" : "password"} placeholder={p.key_prefix ? `${p.key_prefix}…` : "API key"} value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" spellCheck={false} />
        </Field>
      </Fields>
      <Actions>
        <Button variant="ghost" onClick={() => setShow((s) => !s)}>{show ? "Hide" : "Show"}</Button>
        <Button disabled={busy || value.trim().length < 12} onClick={() => void save()}>{busy ? "Saving…" : "Save"}</Button>
        {p.key_set && <Button variant="ghost" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button>}
      </Actions>
      {err && <Text tone="bad">{err}</Text>}
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
      <div className="ui-stack">
        <Text>Enter this code on Grok (a tab should have opened; if not, use the link):</Text>
        <button type="button" className="ui-code" onClick={copy} title="click to copy">{flow.user_code || "…"}{copied ? " · copied" : ""}</button>
        <Text><a href={flow.verification_uri} target="_blank" rel="noopener noreferrer">{flow.verification_uri}</a></Text>
        <Text>Waiting for you to approve… the code is valid for {Math.max(1, Math.round(flow.expires_in / 60))} minutes.</Text>
        <Actions><Button variant="ghost" onClick={() => { stop(); setFlow(null); }}>Cancel</Button></Actions>
      </div>
    );
  }
  return (
    <>
      <Actions><Button disabled={busy} onClick={() => void start()}>{busy ? "Starting…" : "Sign in with Grok"}</Button></Actions>
      {err && <Text tone="bad">{err}</Text>}
    </>
  );
}

function GrokBlock({ grok, onSaved, onDisconnect }: { grok: Provider; onSaved: (s: Status) => void; onDisconnect: () => void }) {
  const [paste, setPaste] = useState(false);
  return (
    <Block title="Grok">
      {grok.subscription_set ? (
        <>
          <Text tone="ok">Signed in with grok.com.</Text>
          <Actions><Button variant="ghost" onClick={onDisconnect}>Disconnect</Button></Actions>
        </>
      ) : (
        <>
          <Text>Use your grok.com subscription. An API key is billed at xAI rates instead.</Text>
          <GrokLogin onSaved={onSaved} />
        </>
      )}
      {grok.key_set ? (
        <KeyForm p={grok} onSaved={onSaved} />
      ) : paste ? (
        <KeyForm p={grok} startOpen onSaved={(s) => { setPaste(false); onSaved(s); }} />
      ) : (
        <Actions><Button variant="ghost" onClick={() => setPaste(true)}>Paste an API key</Button></Actions>
      )}
    </Block>
  );
}

export function HarnessSection() {
  const admin = useIsAdmin();
  const [status, setStatus] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const load = () => fetch("/api/harness-creds").then((r) => r.json()).then((j) => { if (j.error) setErr(j.error); else { setStatus(j); setErr(null); } }).catch(() => {});
  useEffect(() => { if (admin) void load(); }, [admin]);
  if (!admin) {
    return (
      <Card>
        <h3>Coding agents</h3>
        <Text>An admin connects Claude, Grok, Codex and the others from this panel. Nothing goes in a <code>.env</code> file.</Text>
      </Card>
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
  const grok = status?.providers.find((p) => p.subscription === "grok");
  const others = status?.providers.filter((p) => p.id !== grok?.id) ?? [];
  const otherConnected = others.filter(isConnected);
  const unused = others.filter((p) => !isConnected(p));
  const addingP = unused.find((p) => p.id === adding);
  return (
    <Card>
      <h3>Coding agents</h3>
      <Text>Who Marvin talks to. Rooms use this unless a room picks another.</Text>
      {status === null && !err && <Text>Checking…</Text>}
      {status && grok && <GrokBlock grok={grok} onSaved={setStatus} onDisconnect={() => void disconnectGrok()} />}
      {status && (
        <>
          <Fields>
            <Field label="Default for rooms" wide>
              <Select value={status.default_harness} onChange={(e) => void setDefault(e.target.value)}>
                {status.harnesses.map((h) => <option key={h.id} value={h.id}>{h.label}</option>)}
              </Select>
            </Field>
          </Fields>
          {status.default_source === "env" && <Text>From the environment. Change it here to store it on this machine.</Text>}
          {status.default_harness === "opencode" && <Text>OpenCode uses whichever key you have connected. There is no separate OpenCode secret.</Text>}
          {otherConnected.map((p) => (
            <Block key={p.id} title={shortLabel(p)}>
              {p.note && <Text>{p.note}</Text>}
              <KeyForm p={p} onSaved={setStatus} />
            </Block>
          ))}
          {unused.length > 0 && (
            <>
              <Text>Add another</Text>
              <Actions>
                {unused.map((p) => (
                  <Button key={p.id} variant="ghost" onClick={() => setAdding(p.id)}>{shortLabel(p)}</Button>
                ))}
              </Actions>
            </>
          )}
          {addingP && (
            <Block title={shortLabel(addingP)}>
              {addingP.note && <Text>{addingP.note}</Text>}
              <KeyForm p={addingP} startOpen onSaved={(s) => { setAdding(null); setStatus(s); }} />
              <Actions><Button variant="ghost" onClick={() => setAdding(null)}>Cancel</Button></Actions>
            </Block>
          )}
        </>
      )}
      {err && <Text tone="bad">{err}</Text>}
    </Card>
  );
}
