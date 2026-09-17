import { useEffect, useState } from "react";
import { useIsAdmin } from "./auth";
import { Actions, Button, Card, Check, Field, Fields, Input, Text } from "./ui";

type Row = { id: string; room: string; started_at: number; ended_at: number | null; participants: string[]; live?: boolean };
type Rec = { ts: number; verb: string; actor: string; turn: number | null; payload: Record<string, unknown>; chain_ok?: boolean };

export function SessionsSection() {
  const admin = useIsAdmin();
  const [rows, setRows] = useState<Row[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ records: Rec[]; signed: boolean | null; live: boolean } | null>(null);
  const [days, setDays] = useState(90);
  const [err, setErr] = useState<string | null>(null);
  const load = () =>
    fetch("/api/sessions").then(async (r) => {
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? r.statusText);
      setRows(j.sessions || []);
      if (j.retention_days) setDays(j.retention_days);
    }).catch((e) => setErr(String(e instanceof Error ? e.message : e)));
  useEffect(() => { void load(); }, []);
  const view = async (id: string) => {
    setOpen(id);
    const r = await fetch(`/api/sessions/${id}`);
    const j = await r.json();
    if (!r.ok) { setErr(j.error ?? r.statusText); return; }
    setDetail(j);
  };
  const saveDays = async () => {
    const r = await fetch("/api/sessions", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ days }) });
    if (!r.ok) setErr((await r.json()).error ?? r.statusText);
  };
  const when = (t: number | null) => t ? new Date(t * 1000).toLocaleString() : "open";
  return (
    <Card>
      <h3>Sessions</h3>
      <Text>Each meeting is a hash-chained log on this machine. Export (S3 / webhook) is on Audit export if you set it.</Text>
      {admin && (
        <Fields>
          <Field label="Keep logs for (days)">
            <Input type="number" min={1} max={3650} value={days} onChange={(e) => setDays(Number(e.target.value))} />
          </Field>
        </Fields>
      )}
      {admin && (
        <Actions>
          <Button onClick={() => void saveDays()}>Save</Button>
        </Actions>
      )}
      {rows.length === 0 && <Text>No meetings yet.</Text>}
      {rows.length > 0 && (
        <ul className="ui-list">
          {rows.map((s) => (
            <li key={s.id}>
              <a href="#" onClick={(e) => { e.preventDefault(); void view(s.id); }}>{s.room}</a>
              <small>{when(s.started_at)}{s.live ? " · live" : ""} · {(s.participants || []).join(", ") || "—"}</small>
            </li>
          ))}
        </ul>
      )}
      {detail && open && (
        <div className="ui-block">
          <Text>{open.slice(0, 8)} · {detail.live ? "live" : detail.signed ? "signed" : "unsigned"}</Text>
          <ol className="ui-steps">
            {detail.records.map((r, i) => (
              <li key={i}>
                <b>{r.verb}</b>
                <span>{r.actor}{r.turn ? ` · turn ${r.turn}` : ""}{r.payload?.question || r.payload?.text || r.payload?.message ? ` — ${String(r.payload.question || r.payload.text || r.payload.message).slice(0, 120)}` : ""}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {err && <Text tone="bad">{err}</Text>}
    </Card>
  );
}

type ExportInfo = { bucket: string | null; region: string; prefix: string; webhook: string | null; object_lock: boolean; has_keys: boolean; source: string | null };

export function ExportSection() {
  const admin = useIsAdmin();
  const [info, setInfo] = useState<ExportInfo | null>(null);
  const [bucket, setBucket] = useState("");
  const [region, setRegion] = useState("eu-central-1");
  const [prefix, setPrefix] = useState("marvin-audit/");
  const [webhook, setWebhook] = useState("");
  const [ak, setAk] = useState("");
  const [sk, setSk] = useState("");
  const [lock, setLock] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!admin) return;
    fetch("/api/export").then((r) => r.json()).then((j) => {
      setInfo(j); setBucket(j.bucket || ""); setRegion(j.region || "eu-central-1"); setPrefix(j.prefix || "marvin-audit/"); setWebhook(j.webhook || ""); setLock(Boolean(j.object_lock));
    }).catch(() => {});
  }, [admin]);
  if (!admin) return null;
  const save = async () => {
    setBusy(true); setErr(null);
    const r = await fetch("/api/export", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ bucket, region, prefix, webhook, access_key: ak, secret_key: sk, object_lock: lock }) });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) { setErr(j.error ?? r.statusText); return; }
    setAk(""); setSk(""); setInfo(j);
  };
  return (
    <Card>
      <h3>Audit export</h3>
      <Text>When a meeting closes, Marvin can PUT the JSONL to your bucket and/or POST it to a webhook. Needs an Enterprise license. Nothing is sent to us.</Text>
      <Fields>
        <Field label="S3 bucket"><Input value={bucket} onChange={(e) => setBucket(e.target.value)} placeholder="company-marvin-audit" /></Field>
        <Field label="Region"><Input value={region} onChange={(e) => setRegion(e.target.value)} /></Field>
        <Field label="Prefix"><Input value={prefix} onChange={(e) => setPrefix(e.target.value)} /></Field>
        <Field label="Access key"><Input value={ak} onChange={(e) => setAk(e.target.value)} autoComplete="off" /></Field>
        <Field label="Secret key"><Input type="password" value={sk} onChange={(e) => setSk(e.target.value)} placeholder={info?.has_keys ? "unchanged" : ""} /></Field>
        <Field label="Webhook URL" wide><Input value={webhook} onChange={(e) => setWebhook(e.target.value)} placeholder="https://siem.example/hooks/marvin" /></Field>
      </Fields>
      <Check label="Object Lock (GOVERNANCE)" checked={lock} onChange={(e) => setLock(e.target.checked)} />
      {info?.source === "env" && <Text>Export is set from the environment.</Text>}
      <Actions>
        <Button disabled={busy} onClick={() => void save()}>{busy ? "Saving…" : "Save export"}</Button>
      </Actions>
      {err && <Text tone="bad">{err}</Text>}
    </Card>
  );
}
