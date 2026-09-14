// Who is signed in and how (GET /api/me), mirrored by worker/marvin/auth.py. Modes:
//   header   - an identity-aware proxy (oauth2-proxy + Caddy, an OIDC ingress) signed the user in; no login screen here
//   password - Marvin's own login (POST /api/login) kept in an HttpOnly cookie
//   none     - localhost dev: the name typed on the join screen, everyone is admin
import { createContext, useContext } from "react";

export type AuthMode = "header" | "password" | "none";
export type Identity = { id: string; name: string; email: string | null; roles: string[] };
export type Me = { auth: AuthMode; identity: Identity | null; notice?: string | null };

export const FALLBACK_ME: Me = { auth: "none", identity: null }; // an older token server without /api/me

export async function fetchMe(): Promise<Me> {
  try {
    const r = await fetch("/api/me");
    if (!r.ok) return FALLBACK_ME;
    const j = await r.json();
    return j && typeof j.auth === "string" ? (j as Me) : FALLBACK_ME;
  } catch {
    return FALLBACK_ME;
  }
}

export async function login(email: string, password: string): Promise<Me> {
  const r = await fetch("/api/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email, password }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error ?? r.statusText);
  return j as Me;
}

export async function logout(): Promise<void> {
  await fetch("/api/logout", { method: "POST" }).catch(() => {});
}

export function isAdmin(me: Me | null): boolean {
  if (!me) return false;
  return me.auth === "none" || Boolean(me.identity?.roles.includes("admin"));
}

/** Roles the token server embedded in a LiveKit participant's metadata ({"roles": [...]}); [] when absent or malformed. */
export function rolesOf(metadata: string | undefined): string[] {
  if (!metadata) return [];
  try {
    const j = JSON.parse(metadata);
    return Array.isArray(j?.roles) ? j.roles.map(String) : [];
  } catch {
    return [];
  }
}

export const MeContext = createContext<{ me: Me; setMe: (m: Me) => void }>({ me: FALLBACK_ME, setMe: () => {} });
export const useMe = () => useContext(MeContext).me;
export const useIsAdmin = () => isAdmin(useMe());
