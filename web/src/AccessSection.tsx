import { useEffect, useState } from "react";
import { useIsAdmin } from "./auth";
import { LicenseLockReason, useEnterprise } from "./License";
import { Actions, Button, Card, Chip, Chips, Field, Fields, Input, Steps, Text, Textarea } from "./ui";

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

type ProviderId = "local" | "entra" | "okta" | "google" | "github" | "keycloak";

type Provider = {
  id: ProviderId;
  proxy: "oidc" | "github";
  label: string;
  hint: string;
  issuer?: string;
  clientId?: string;
  groupsClaim?: string;
  steps: { title: string; detail: string; href?: string }[];
};

const PROVIDERS: Provider[] = [
  {
    id: "local",
    proxy: "oidc",
    label: "Local test",
    hint: "A fake company login on this laptop. Two users, no cloud tenant.",
    issuer: "http://127.0.0.1:8088/dex",
    clientId: "marvin",
    steps: [
      { title: "Save these values", detail: "Issuer and client id below are already filled. Secret is marvin-local." },
      { title: "Start the local login", detail: "In the repo: make sso-dev. Keep the token server on MARVIN_AUTH=header." },
      { title: "Open the proxied URL", detail: "http://127.0.0.1:8088 — not port 5174. Vite stays behind Caddy.", href: "http://127.0.0.1:8088" },
      { title: "Sign in", detail: "maria@acme.com / maria is admin. alex@acme.com / alex is a participant." },
    ],
  },
  {
    id: "entra",
    proxy: "oidc",
    label: "Microsoft Entra",
    hint: "Company Microsoft 365 / Azure AD.",
    steps: [
      { title: "Register the app", detail: "Entra → App registrations → New registration. Name Marvin. Platform Web.", href: "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade" },
      { title: "Redirect URL", detail: "Paste the callback below exactly." },
      { title: "Client secret", detail: "Certificates & secrets → New client secret. Copy the Value once." },
      { title: "Groups claim", detail: "Token configuration → Add groups claim → Security groups. Admin groups in Marvin are those object ids." },
      { title: "Issuer", detail: "https://login.microsoftonline.com/<tenant-id>/v2.0 — tenant id is on the app’s Overview." },
    ],
  },
  {
    id: "okta",
    proxy: "oidc",
    label: "Okta",
    hint: "Okta OIDC web app.",
    steps: [
      { title: "Create the app", detail: "Applications → Create App Integration → OIDC → Web Application.", href: "https://login.okta.com/" },
      { title: "Redirect URL", detail: "Sign-in redirect URI is the callback below." },
      { title: "Groups claim", detail: "Add a groups claim on the ID token (directory groups). Admin groups in Marvin are those names." },
      { title: "Issuer", detail: "https://<org>.okta.com or your custom authorization server." },
    ],
  },
  {
    id: "google",
    proxy: "oidc",
    label: "Google",
    hint: "Google Workspace or personal Google accounts.",
    issuer: "https://accounts.google.com",
    steps: [
      { title: "Create an OAuth client", detail: "Google Cloud → APIs & Services → Credentials → Create credentials → OAuth client ID → Web application.", href: "https://console.cloud.google.com/apis/credentials" },
      { title: "Redirect URL", detail: "Authorized redirect URI is the callback below." },
      { title: "Issuer", detail: "https://accounts.google.com — already filled." },
      { title: "Admins", detail: "Google groups need extra setup. Easier: list admin emails under Admin users." },
    ],
  },
  {
    id: "github",
    proxy: "github",
    label: "GitHub",
    hint: "GitHub OAuth App. Teams become groups.",
    steps: [
      { title: "New OAuth App", detail: "GitHub → Settings → Developer settings → OAuth Apps → New OAuth App.", href: "https://github.com/settings/developers" },
      { title: "Callback URL", detail: "Authorization callback URL is the callback below." },
      { title: "Copy id and secret", detail: "Client ID and the generated client secret. No issuer field." },
      { title: "Admins", detail: "Org teams arrive as groups, or list admin GitHub emails under Admin users." },
    ],
  },
  {
    id: "keycloak",
    proxy: "oidc",
    label: "Keycloak",
    hint: "Self-hosted Keycloak, Authentik, or Zitadel.",
    steps: [
      { title: "Create a client", detail: "In the realm: Clients → Create. Client protocol openid-connect, access type confidential." },
      { title: "Redirect URL", detail: "Valid redirect URI is the callback below." },
      { title: "Issuer", detail: "https://<keycloak>/realms/<realm> (Authentik and Zitadel use their OIDC discovery URL)." },
      { title: "Groups", detail: "Map a groups scope/claim so Marvin can promote admins by group." },
    ],
  },
];

function guessProvider(info: AccessInfo | null): ProviderId {
  const issuer = (info?.sso.issuer || "").toLowerCase();
  if (info?.sso.provider === "github") return "github";
  if (issuer.includes("127.0.0.1:8088/dex") || (issuer.includes("localhost") && issuer.includes("/dex"))) return "local";
  if (issuer.includes("microsoftonline.com")) return "entra";
  if (issuer.includes("okta.com")) return "okta";
  if (issuer.includes("accounts.google.com")) return "google";
  if (issuer.includes("realms/")) return "keycloak";
  return "entra";
}

export function AccessSection() {
  const admin = useIsAdmin();
  const ent = useEnterprise();
  const locked = !ent.ee;
  const [info, setInfo] = useState<AccessInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [domains, setDomains] = useState("");
  const [allow, setAllow] = useState("");
  const [groups, setGroups] = useState("");
  const [users, setUsers] = useState("");
  const [notice, setNotice] = useState("");
  const [issuer, setIssuer] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [emailDomains, setEmailDomains] = useState("");
  const [groupsClaim, setGroupsClaim] = useState("groups");
  const [pick, setPick] = useState<ProviderId>("entra");

  const callback = pick === "local"
    ? "http://127.0.0.1:8088/oauth2/callback"
    : `${typeof location !== "undefined" ? location.origin : ""}/oauth2/callback`;
  const provider = PROVIDERS.find((p) => p.id === pick) ?? PROVIDERS[1];

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
      setGroupsClaim(j.sso?.groups_claim || "groups");
      setPick(guessProvider(j));
    }).catch((e) => setErr(String(e instanceof Error ? e.message : e)));
  useEffect(() => { if (admin) void load(); }, [admin]);

  const applyProvider = (id: ProviderId) => {
    const next = PROVIDERS.find((p) => p.id === id);
    if (!next) return;
    setPick(id);
    if (next.issuer) setIssuer(next.issuer);
    if (next.clientId) setClientId(next.clientId);
    if (next.groupsClaim) setGroupsClaim(next.groupsClaim);
    if (id === "github") setIssuer("");
    if (id === "local") setClientSecret("marvin-local");
  };

  if (!admin) return null;

  const saveWho = async () => {
    setBusy(true); setErr(null);
    const r = await fetch("/api/access", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({
      allowed_domains: domains, allow_list: allow, admin_groups: groups, admin_users: users, notice,
    }) });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) { setErr(j.error ?? r.statusText); return; }
    setInfo(j);
  };

  const saveSso = async () => {
    setBusy(true); setErr(null);
    const r = await fetch("/api/access", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({
      issuer, client_id: clientId, client_secret: clientSecret, email_domains: emailDomains,
      groups_claim: groupsClaim, provider: provider.proxy,
    }) });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) { setErr(j.error ?? r.statusText); return; }
    setClientSecret("");
    setInfo(j);
  };

  const copyCallback = () => {
    void navigator.clipboard?.writeText(callback).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <>
      <Card locked={locked} lockReason={<LicenseLockReason />}>
        <h3>Who may join</h3>
        <Text>Password login and SSO both honour this list. Empty means anyone who can authenticate.</Text>
        <Fields>
          <Field label="Allowed email domains"><Input value={domains} onChange={(e) => setDomains(e.target.value)} placeholder="company.com" /></Field>
          <Field label="Extra allowed addresses"><Input value={allow} onChange={(e) => setAllow(e.target.value)} placeholder="maria@contractor.dev" /></Field>
          <Field label="Admin users"><Input value={users} onChange={(e) => setUsers(e.target.value)} placeholder="maria@company.com" /></Field>
          <Field label="Admin groups (SSO)"><Input value={groups} onChange={(e) => setGroups(e.target.value)} placeholder="Entra object ids, or Okta group names" /></Field>
          <Field label="Recording notice" wide><Textarea rows={3} value={notice} onChange={(e) => setNotice(e.target.value)} /></Field>
        </Fields>
        <Actions><Button disabled={busy} onClick={() => void saveWho()}>{busy ? "Saving…" : "Save who may join"}</Button></Actions>
      </Card>

      <Card locked={locked || !ent.allows("sso")} lockReason={<LicenseLockReason />}>
        <h3>Company sign-in</h3>
        <Text>
          People sign in at your identity provider. Marvin never sees their password.
          {info?.sso.source === "env" ? " Issuer is from the environment." : null}
        </Text>
        {info?.sso.configured && (
          <Text tone="ok">{info.sso.client_id ? `Client ${info.sso.client_id}` : "Client saved"} · {info.sso.source === "env" ? "from the environment" : "set here"}</Text>
        )}

        <Chips label="Identity provider">
          {PROVIDERS.map((p) => (
            <Chip key={p.id} selected={pick === p.id} onClick={() => applyProvider(p.id)}>{p.label}</Chip>
          ))}
        </Chips>
        <Text>{provider.hint}</Text>

        <Field label="Redirect URL — paste this at the provider" wide>
          <div className="ui-row">
            <code className="ui-code">{callback}</code>
            <Button variant="ghost" onClick={copyCallback}>{copied ? "Copied" : "Copy"}</Button>
          </div>
        </Field>

        <Steps
          items={provider.steps.map((step) => ({
            title: step.title,
            detail: step.href
              ? <><a href={step.href} target="_blank" rel="noopener noreferrer">{step.href.replace(/^https:\/\//, "").split("/")[0]}</a> — {step.detail}</>
              : step.detail,
          }))}
        />

        <Fields>
          {provider.proxy === "oidc" && (
            <Field label="Issuer URL" wide><Input value={issuer} onChange={(e) => setIssuer(e.target.value)} placeholder="https://login.microsoftonline.com/…/v2.0" /></Field>
          )}
          <Field label="Client id"><Input value={clientId} onChange={(e) => setClientId(e.target.value)} /></Field>
          <Field label="Client secret"><Input type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder={info?.sso.has_secret ? "unchanged" : pick === "local" ? "marvin-local" : ""} /></Field>
          <Field label="SSO email domains"><Input value={emailDomains} onChange={(e) => setEmailDomains(e.target.value)} placeholder="company.com or *" /></Field>
          {provider.proxy === "oidc" && provider.id !== "local" && (
            <Field label="Groups claim"><Input value={groupsClaim} onChange={(e) => setGroupsClaim(e.target.value)} placeholder="groups" /></Field>
          )}
        </Fields>
        <Actions>
          <Button disabled={busy || info?.sso.source === "env"} onClick={() => void saveSso()}>{busy ? "Saving…" : "Save company sign-in"}</Button>
        </Actions>
        {pick === "local" ? (
          <Text>After save, run <code>make sso-dev</code> and open <a href="http://127.0.0.1:8088">http://127.0.0.1:8088</a>. The four-terminal loop on :5174 stays unsigned-in.</Text>
        ) : (
          <Text>On an appliance, after the first save an admin runs <code>make edge-oidc-up</code> once so Caddy starts asking the provider.</Text>
        )}
      </Card>
      {err && <Text tone="bad">{err}</Text>}
    </>
  );
}
