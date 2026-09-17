import { useEffect, useState, type ReactNode } from "react";
import { useIsAdmin } from "./auth";
import { Actions, Button, Card, Facts, Field, Fields, Text, Textarea } from "./ui";

export type LicenseInfo = {
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
  key_hint?: string | null;
};

function formatDay(ts: number) {
  return new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function LicensePaste({ onValid, extra }: { onValid?: (info: LicenseInfo) => void; extra?: ReactNode }) {
  const [key, setKey] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const response = await fetch("/api/license", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ key }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error ?? response.statusText);
      setKey("");
      onValid?.(body as LicenseInfo);
    } catch (cause) {
      setErr((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="ui-stack">
      <Fields>
        <Field label="License string" wide>
          <Textarea rows={3} placeholder="eyJ… (the license string)" value={key} onChange={(event) => setKey(event.target.value)} autoComplete="off" spellCheck={false} />
        </Field>
      </Fields>
      <Actions>
        <Button disabled={busy || key.trim().length < 20} onClick={() => void save()}>{busy ? "Saving…" : "Save license"}</Button>
        {extra}
      </Actions>
      {err && <Text tone="bad">{err}</Text>}
    </div>
  );
}

/** Whether this machine has a valid Enterprise license. Safe for anyone signed in (GET /api/license). */
export function useEnterprise() {
  const [info, setInfo] = useState<{ ee: boolean; company: string | null } | null>(null);
  useEffect(() => {
    fetch("/api/license")
      .then(async (response) => {
        if (!response.ok) return;
        const body = await response.json() as LicenseInfo;
        setInfo({ ee: Boolean(body.ee || body.valid), company: body.company });
      })
      .catch(() => {});
  }, []);
  return info;
}

export function LicenseSection() {
  const admin = useIsAdmin();
  const [info, setInfo] = useState<LicenseInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [replace, setReplace] = useState(false);
  const load = () =>
    fetch("/api/license")
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error ?? response.statusText);
        setInfo(body);
        setErr(null);
      })
      .catch((cause) => setErr(String(cause instanceof Error ? cause.message : cause)));
  useEffect(() => { if (admin) void load(); }, [admin]);
  if (!admin) return null;
  if (!info && !err) return <Card><h3>Enterprise</h3><Text>Checking…</Text></Card>;
  const clear = async () => {
    if (!confirm("Remove the license key from this machine? Enterprise features turn off. The free core stays.")) return;
    setBusy(true);
    setErr(null);
    const response = await fetch("/api/license", { method: "DELETE" });
    const body = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) { setErr(body.error ?? response.statusText); return; }
    setInfo(body);
    setReplace(false);
  };
  const fromEnv = info?.source === "env";
  const setHere = info?.source === "settings";
  const showPaste = Boolean(info && !fromEnv && (!info.has_key || !info.valid || replace));
  const facts = [
    ...(info?.seats != null ? [{ label: "Seats", value: String(info.seats) }] : []),
    ...(info?.expires_at
      ? [{ label: info.valid ? "Valid until" : "Ended", value: formatDay(info.expires_at) }]
      : []),
  ];
  return (
    <Card>
      <h3>Enterprise</h3>
      {info?.company ? <p className="ui-lead">{info.company}</p> : null}
      <Facts items={facts} />
      {info?.valid ? (
        <Text>
          Enterprise features are on for this machine. The key stays on this box; Marvin does not call home.
          {info.features.length > 0 && info.features[0] !== "*" ? <> On: {info.features.join(", ")}.</> : null}
        </Text>
      ) : (
        <>
          <Text>{info?.has_key ? info.message : "This machine is the free core. Anyone can run it."}</Text>
          {!info?.has_key && (
            <Text>A paid subscription is only for the compliance pack (SSO, audit, isolation). You get a license string from us; paste it here. No restart.</Text>
          )}
        </>
      )}
      {info?.has_key && !showPaste && (
        <Text>
          {info.key_hint
            ? <>License string: <code>{info.key_hint}</code></>
            : <>License string is on this machine.</>}
        </Text>
      )}
      {showPaste && (
        <LicensePaste
          onValid={(next) => { setInfo(next); setReplace(false); }}
          extra={
            <>
              {replace && <Button variant="ghost" onClick={() => setReplace(false)}>Cancel</Button>}
              {setHere && <Button variant="ghost" disabled={busy} onClick={() => void clear()}>Remove</Button>}
            </>
          }
        />
      )}
      {!fromEnv && info?.has_key && !showPaste && (
        <Actions>
          <Button variant="ghost" onClick={() => setReplace(true)}>Replace</Button>
          <Button variant="ghost" disabled={busy} onClick={() => void clear()}>Remove</Button>
        </Actions>
      )}
      {fromEnv && <Text>License is <code>MARVIN_LICENSE_KEY</code> from the environment.</Text>}
      {err && <Text tone="bad">{err}</Text>}
    </Card>
  );
}
