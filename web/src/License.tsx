import { useEffect, useState } from "react";
import { useIsAdmin } from "./auth";

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
};

export function LicensePaste({ onValid }: { onValid?: (info: LicenseInfo) => void }) {
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
    <div className="github-setup">
      <textarea rows={3} placeholder="eyJ… (the license string)" value={key} onChange={(event) => setKey(event.target.value)} autoComplete="off" spellCheck={false} />
      <div className="row">
        <button type="button" disabled={busy || key.trim().length < 20} onClick={() => void save()}>{busy ? "Saving…" : "Save license"}</button>
      </div>
      {err && <p className="error small">{err}</p>}
    </div>
  );
}

export function LicenseSection() {
  const admin = useIsAdmin();
  const [info, setInfo] = useState<LicenseInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
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
  const clear = async () => {
    if (!confirm("Remove the license key from this machine? Enterprise features turn off. The free core stays.")) return;
    setBusy(true);
    setErr(null);
    const response = await fetch("/api/license", { method: "DELETE" });
    const body = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) { setErr(body.error ?? response.statusText); return; }
    setInfo(body);
  };
  const fromEnv = info?.source === "env";
  return (
    <section>
      <h3>Enterprise</h3>
      {info?.valid ? (
        <>
          <p className="small">{info.message}{info.source === "env" ? " · from the environment" : " · set here"}.</p>
          <p className="dim small">Enterprise features are on for this machine. The key stays on this box; Marvin does not call home.
            {info.features.length > 0 && info.features[0] !== "*" ? <> On: {info.features.join(", ")}.</> : null}
          </p>
        </>
      ) : (
        <>
          <p className="small">{info?.has_key ? info.message : "This machine is the free core. Anyone can run it."}</p>
          <p className="dim small">A paid subscription is only for the compliance pack (SSO, audit, isolation). You get a license string from us; paste it here. No restart.</p>
        </>
      )}
      {!fromEnv && (
        <>
          <LicensePaste onValid={setInfo} />
          {info?.source === "settings" && (
            <div className="row">
              <button type="button" className="ghost" disabled={busy} onClick={() => void clear()}>remove</button>
            </div>
          )}
        </>
      )}
      {fromEnv && <p className="dim small">License is <code>MARVIN_LICENSE_KEY</code> from the environment.</p>}
      {err && <p className="error small">{err}</p>}
    </section>
  );
}
