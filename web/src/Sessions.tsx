import { useEffect, useState } from "react";
import { useIsAdmin } from "./auth";

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
    <section id="settings-sessions">
      <h3>Sessions</h3>
      <p className="dim small">Each meeting is a hash-chained log on this machine. Export (S3 / webhook) is below in Enterprise if you set it.</p>
      {admin && (
        <div className="github-setup">
          <div className="row">
            <label className="dim small">Keep logs <input type="number" min={1} max={3650} value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ width: 72 }} /> days</label>
            <button type="button" className="ghost" onClick={() => void saveDays()}>save</button>
          </div>
        </div>
      )}
      {rows.length === 0 && <p className="dim small">No meetings yet.</p>}
      <ul className="small">
        {rows.map((s) => (
          <li key={s.id}>
            <a href="#" onClick={(e) => { e.preventDefault(); void view(s.id); }}>{s.room}</a>
            {" "}{when(s.started_at)}{s.live ? " · live" : ""} · {(s.participants || []).join(", ") || "—"}
          </li>
        ))}
      </ul>
      {detail && open && (
        <div className="session-log">
          <p className="dim small">{open.slice(0, 8)} · {detail.live ? "live" : detail.signed ? "signed" : "unsigned"}</p>
          <ol className="small">
            {detail.records.map((r, i) => (
              <li key={i}><code>{r.verb}</code> {r.actor}{r.turn ? ` · turn ${r.turn}` : ""} {r.payload?.question || r.payload?.text || r.payload?.message ? <span className="dim"> — {String(r.payload.question || r.payload.text || r.payload.message).slice(0, 120)}</span> : null}</li>
            ))}
          </ol>
        </div>
      )}
      {err && <p className="error small">{err}</p>}
    </section>
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
    <section>
      <h3>Audit export</h3>
      <p className="dim small">When a meeting closes, Marvin can PUT the JSONL to your bucket and/or POST it to a webhook. Needs an Enterprise license. Nothing is sent to us.</p>
      <label className="dim small">S3 bucket <input value={bucket} onChange={(e) => setBucket(e.target.value)} placeholder="company-marvin-audit" /></label>
      <label className="dim small">Region <input value={region} onChange={(e) => setRegion(e.target.value)} /></label>
      <label className="dim small">Prefix <input value={prefix} onChange={(e) => setPrefix(e.target.value)} /></label>
      <label className="dim small">Access key <input value={ak} onChange={(e) => setAk(e.target.value)} autoComplete="off" /></label>
      <label className="dim small">Secret key <input type="password" value={sk} onChange={(e) => setSk(e.target.value)} placeholder={info?.has_keys ? "unchanged" : ""} /></label>
      <label className="dim small"><input type="checkbox" checked={lock} onChange={(e) => setLock(e.target.checked)} /> Object Lock (GOVERNANCE)</label>
      <label className="dim small">Webhook URL <input value={webhook} onChange={(e) => setWebhook(e.target.value)} placeholder="https://siem.example/hooks/marvin" /></label>
      {info?.source === "env" && <p className="dim small">Export is set from the environment.</p>}
      <div className="btns"><button type="button" disabled={busy} onClick={() => void save()}>{busy ? "saving…" : "save export"}</button></div>
      {err && <p className="error small">{err}</p>}
    </section>
  );
}
