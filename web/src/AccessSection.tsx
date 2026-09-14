import { useEffect, useState } from "react";
import { useIsAdmin } from "./auth";

type AccessInfo = {
  notice: string;
  allowed_domains: string[];
  allow_list: string[];
  restricted: boolean;
  allowed_domains_source: string | null;
  admin_groups?: string[];
  admin_users?: string[];
  sso: {
    issuer: string | null;
    client_id: string | null;
    email_domains: string | null;
    groups_claim: string;
    provider: string;
    configured: boolean;
    source: string | null;
    has_secret: boolean;
  };
};

export function AccessSection() {
  const admin = useIsAdmin();
  const [info, setInfo] = useState<AccessInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [domains, setDomains] = useState("");
  const [allow, setAllow] = useState("");
  const [groups, setGroups] = useState("");
  const [users, setUsers] = useState("");
  const [notice, setNotice] = useState("");
  const [issuer, setIssuer] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [emailDomains, setEmailDomains] = useState("");
  const load = () =>
    fetch("/api/access").then(async (r) => {
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? r.statusText);
      setInfo(j);
      setDomains((j.allowed_domains || []).join(", "));
      setAllow((j.allow_list || []).join(", "));
      setGroups((j.admin_groups || []).join(", "));
      setUsers((j.admin_users || []).join(", "));
      setNotice(j.notice || "");
      setIssuer(j.sso?.issuer || "");
      setClientId(j.sso?.client_id || "");
      setEmailDomains(j.sso?.email_domains || "");
    }).catch((e) => setErr(String(e instanceof Error ? e.message : e)));
  useEffect(() => { if (admin) void load(); }, [admin]);
  if (!admin) return null;
  const save = async () => {
    setBusy(true); setErr(null);
    const r = await fetch("/api/access", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({
      allowed_domains: domains, allow_list: allow, admin_groups: groups, admin_users: users, notice,
      issuer, client_id: clientId, client_secret: clientSecret, email_domains: emailDomains,
    }) });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) { setErr(j.error ?? r.statusText); return; }
    setClientSecret("");
    setInfo(j);
  };
  return (
    <section>
      <h3>Sign-in and notice</h3>
      <p className="dim small">Password login can be limited to company emails (free). SSO is OIDC (Okta, Entra, Google, Keycloak) through oauth2-proxy and needs an Enterprise license. Env wins over what you save here.</p>
      <label className="dim small">Allowed email domains <input value={domains} onChange={(e) => setDomains(e.target.value)} placeholder="company.com" /></label>
      <label className="dim small">Extra allowed addresses <input value={allow} onChange={(e) => setAllow(e.target.value)} placeholder="maria@contractor.dev" /></label>
      <label className="dim small">Admin groups (SSO) <input value={groups} onChange={(e) => setGroups(e.target.value)} placeholder="marvin-admins" /></label>
      <label className="dim small">Admin users <input value={users} onChange={(e) => setUsers(e.target.value)} placeholder="maria@company.com" /></label>
      <label className="dim small">Recording notice <textarea rows={2} value={notice} onChange={(e) => setNotice(e.target.value)} /></label>
      <h4 className="small" style={{ margin: "8px 0 0" }}>OIDC (oauth2-proxy)</h4>
      <p className="dim small">
        Entra: issuer <code>https://login.microsoftonline.com/&lt;tenant&gt;/v2.0</code>, enable the groups claim (object ids).
        Okta: issuer <code>https://&lt;org&gt;.okta.com</code>, add a <code>groups</code> claim.
        Redirect URL: <code>{typeof location !== "undefined" ? location.origin : ""}/oauth2/callback</code>.
        After the first save, an admin runs <code>make edge-oidc-up</code> once.
      </p>
      <label className="dim small">Issuer URL <input value={issuer} onChange={(e) => setIssuer(e.target.value)} placeholder="https://login.microsoftonline.com/…/v2.0" /></label>
      <label className="dim small">Client id <input value={clientId} onChange={(e) => setClientId(e.target.value)} /></label>
      <label className="dim small">Client secret <input type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder={info?.sso.has_secret ? "unchanged" : ""} /></label>
      <label className="dim small">SSO email domains <input value={emailDomains} onChange={(e) => setEmailDomains(e.target.value)} placeholder="company.com or *" /></label>
      {info?.sso.source === "env" && <p className="dim small">OIDC issuer is from the environment.</p>}
      <div className="btns"><button type="button" disabled={busy} onClick={() => void save()}>{busy ? "saving…" : "save"}</button></div>
      {err && <p className="error small">{err}</p>}
    </section>
  );
}
