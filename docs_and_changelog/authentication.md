# Authentication and roles

Status: shipped on `feat/edge-auth` (2026-09-12). Code: `worker/marvin/auth.py`, `worker/marvin/token_server.py`,
`worker/marvin/room/session.py` (`roles_of`), `worker/marvin/room/conductor.py`; edge: `deploy/edge/`,
`docker-compose.edge.yml`. Threat model and the wider plan: `security-and-compliance.md`.

## What this fixes

Before this change anyone who could reach the URL could mint a LiveKit token under any name, call every admin endpoint
(create rooms, clone repositories with the server's GitHub token, rewrite the machine notes that are injected into every
session), and flip "always allow", which runs any tool without asking. Now:

- every request to `/api/*` needs a verified identity;
- identity and roles are decided server-side and signed into the LiveKit token, so the worker trusts them without a
  second lookup;
- anything that changes state on the machine (rooms, repos, harness/model switches, machine notes) needs the `admin`
  role; "always allow" needs `admin` and a refusal is shown to the room.

## Roles

- `participant`: join rooms, talk, type questions, drop images, approve or deny individual tool calls, interrupt.
- `admin`: everything above, plus "always allow", creating/deleting rooms, cloning repos, switching harness/model,
  linking repos, reading and writing the machine notes.

Finer roles (`viewer`, `approver`) and per-repo policies are Enterprise Edition work; see `security-and-compliance.md` §7.

## Modes (`MARVIN_AUTH`)

### `password` (default when `MARVIN_ROOM_PASSWORD` is set)

Marvin's own login. No extra service. Suitable for a team behind Caddy on a VM.

```
browser ── POST /api/login {email, password} ──▶ token server ── compare (constant time) ──▶ Set-Cookie marvin_session
browser ── GET /api/token?room=dev  (cookie) ──▶ token server ── read+verify cookie ──▶ LiveKit JWT {identity, name, metadata.roles}
browser ── wss /rtc (JWT) ─────────────────────▶ Caddy ──▶ LiveKit ──▶ worker sees participant.metadata.roles
```

- `MARVIN_ROOM_PASSWORD` → `participant`; `MARVIN_ADMIN_PASSWORD` (optional) → `participant` + `admin`. Both compared
  with `hmac.compare_digest`; both are checked on every attempt so timing does not reveal which one matched.
- The login form asks for **email**. `POST /api/login` accepts `{email, password}` (`name` is still accepted).
  If the identifier contains `@`, it is stored on `Identity.email` and shown on the join page as
  “You’re logged in as …”.
- An admin can limit who joins: Settings → **Sign-in and notice** (or
  `MARVIN_ALLOWED_EMAIL_DOMAINS` / `MARVIN_ALLOW_LIST`). Wrong-domain logins are
  **403** with a sentence naming the domains, not 401. Header mode drops the
  identity the same way. Empty lists mean “anyone with the password / a valid
  IdP session”.
- The same panel holds the recording notice (default: this room is transcribed).
  `GET /api/me` includes `notice`; the join page shows it.
- Cookie `marvin_session`: `<base64url(payload)>.<base64url(HMAC-SHA256)>`, payload `{id, name, email, roles, exp}`;
  `HttpOnly`, `SameSite=Lax`, `Secure` whenever the browser is on https (directly or via `X-Forwarded-Proto`),
  `Max-Age` = `MARVIN_SESSION_HOURS` (12). Signed with `MARVIN_SESSION_SECRET`, falling back to `LIVEKIT_API_SECRET`
  (a warning is logged if that is still the LiveKit dev secret).
- Brute force: a wrong password costs 0.5 s; after 10 failures in a minute from one IP, `/api/login` answers 429.
- The identity id is a slug of the typed email (or name), so two people typing the same value are the same LiveKit
  identity. That is a known limitation of password mode; use `header` mode when names must be authoritative.

### `header` (single sign-on)

An identity-aware proxy authenticates the user and sets `X-Forwarded-User` (stable id), `X-Forwarded-Email`,
`X-Forwarded-Preferred-Username` (display name) and `X-Forwarded-Groups` (comma-separated). The token server trusts
these only when the request comes from `MARVIN_TRUSTED_PROXIES` (default: loopback and the RFC 1918 ranges, which covers
Docker and most cluster networks). Admin if a group is in `MARVIN_ADMIN_GROUPS` or the user/email is in
`MARVIN_ADMIN_USERS`.

```
browser ──▶ Caddy ── forward_auth /oauth2/auth ──▶ oauth2-proxy ── (OIDC) ──▶ Google / Okta / Entra / GitHub / Keycloak
                 ◀── 202 + X-Auth-Request-* ──────┘
            Caddy copies them as X-Forwarded-* ──▶ token server ── Identity(id, name, email, roles) ──▶ LiveKit JWT
```

Two rules make this safe, and both are enforced by the shipped config:

1. **The token server must not be reachable except through the proxy.** In `docker-compose.edge.yml` the `web` service
   has no published ports. On Kubernetes, add a NetworkPolicy so only the ingress controller reaches `marvin-web`.
2. **Client-supplied identity headers are dropped at the edge.** Both Caddyfiles start with
   `request_header -X-Forwarded-User` (and the other three) before any handler runs, so a browser cannot smuggle a
   name even if `MARVIN_AUTH=header` is set without an identity proxy in front.

`/rtc*` (LiveKit signaling) is deliberately outside `forward_auth`: the browser can only obtain a LiveKit JWT from
`/api/token` after signing in, and that JWT is the credential LiveKit verifies.

### `none` (local development)

The name typed on the join screen is the identity and everyone is admin. The token server refuses to start in this mode
unless bound to `127.0.0.1` (`MARVIN_TOKEN_HOST`), or `MARVIN_AUTH_INSECURE_OK=1` is set explicitly. A warning is
logged at startup. This is what the four-terminal `make` loop uses.

If `MARVIN_AUTH` is unset and no room password is set, the token server exits with a message listing the options.

## Endpoint and role matrix

| endpoint / action | unauthenticated | participant | admin |
|---|---|---|---|
| `GET /api/me` | 200, `identity: null` | 200 | 200 |
| `POST /api/login`, `POST /api/logout` (password mode) | allowed | allowed | allowed |
| `GET /api/token?room=` | 401 | JWT with `metadata.roles` | JWT with `metadata.roles` |
| `GET /api/rooms`, `/repos`, `/ports`, `/changes*`, `/models`, `/harnesses` | 401 | allowed | allowed |
| `POST/PATCH/PUT/DELETE /api/*` | 401 | 403 | allowed |
| `GET`/`PUT /api/notes` (machine notes) | 401 | 403 | allowed |
| control message `approve`/`deny`/`ask`/`image`/`interrupt` | n/a (needs a JWT) | allowed | allowed |
| control message `auto_approve` | n/a | refused, room sees `denied` | allowed |
| `wss /rtc` | LiveKit rejects without JWT | allowed | allowed |
| `GET /healthz`, `GET /api/agent` | allowed | allowed | allowed |

Proxied admin calls carry `X-Marvin-User` and `X-Marvin-Roles` to the worker's admin API so it can log who did what.

## Where identity lives

`Identity(id, name, email, roles)` is resolved per request by `Auth.identity_from_request`. `/api/token` writes
`identity=id`, `name=name`, `metadata={"roles": [...]}` into the LiveKit access token, which LiveKit signs. In the room,
`RoomSession.roles_of(participant)` reads `participant.metadata` (empty or malformed → no roles) and passes the set to
`Conductor.on_control`. Nothing in the room trusts a client-sent name or role.

## Deploying

### Compose edge stack (`make edge-up`)

Caddy (80/443, TLS), `web` (token server + built UI), `worker`, `livekit` (7881/tcp, 7882/udp published for media).
Required in `.env`: `NODE_IP`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (32+ chars), `MARVIN_ROOM_PASSWORD`; recommended:
`MARVIN_ADMIN_PASSWORD`, `MARVIN_SESSION_SECRET`, `MARVIN_DOMAIN` + `MARVIN_TLS=<your e-mail>` for a real certificate.
Without `MARVIN_DOMAIN`, Caddy serves `:443` with an internal CA (browser warning; fine on a LAN or behind a VPN).

### Single sign-on (`make edge-oidc-up`)

Adds `oauth2-proxy` (profile `oidc`) and switches to `deploy/edge/Caddyfile.oidc` and `MARVIN_AUTH=header`.
Usual place for the issuer, client id/secret and cookie secret: Settings → **Sign-in and notice**
(Enterprise). That writes `.oauth2-proxy.env` (mode 0600, gitignored) next to the checkout.
`make edge-oidc-up` seeds the file from `.env` only if it does not exist yet. Register the
redirect URL `https://<MARVIN_DOMAIN>/oauth2/callback` at the provider.

Provider notes (details in the [oauth2-proxy provider docs](https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/)):

- **Google**: issuer `https://accounts.google.com`; groups need the Google provider with a service account, otherwise
  promote admins with `MARVIN_ADMIN_USERS=<emails>`.
- **Okta**: Applications → **Create App Integration** → OIDC → Web. Sign-in redirect
  `https://<host>/oauth2/callback`. Add a `groups` claim on the ID token (directory
  groups). Issuer `https://<org>.okta.com` (or a custom auth server). Paste issuer,
  client id and secret in Settings. Admin groups in Marvin are those group names.
- **Microsoft Entra ID**: App registration → **New registration** → name `Marvin`, redirect
  `https://<host>/oauth2/callback` (Web). Certificates & secrets → new client secret. Token
  configuration → add **groups** claim (security groups; object ids). Issuer
  `https://login.microsoftonline.com/<tenant-id>/v2.0`. Paste issuer, client id and secret
  in Settings. Admin groups in Marvin are those object ids (or `MARVIN_ADMIN_GROUPS`).
- **GitHub**: `OAUTH2_PROXY_PROVIDER=github` with `OAUTH2_PROXY_GITHUB_ORG`/`_TEAM`; teams arrive as groups.
- **Keycloak / Authentik / Zitadel**: standard OIDC; make sure the `groups` scope/claim is mapped.

### Kubernetes

`deploy/k8s/statefulset.yaml` sets `MARVIN_AUTH=header`; `deploy/k8s/ingress.yaml` has the nginx `auth-url` /
`auth-signin` / `auth-response-headers` annotations for oauth2-proxy and the `proxy_set_header` lines that rename
`X-Auth-Request-*` to `X-Forwarded-*`. Set `MARVIN_TRUSTED_PROXIES` to the ingress controller's pod CIDR and add a
NetworkPolicy. Without SSO, use `MARVIN_AUTH=password` with the passwords in the `marvin-secrets` Secret.

## Local development

Four terminals, `MARVIN_AUTH=none` (the default in `.env.example`), everything on localhost. To exercise roles
locally, set `MARVIN_AUTH=password`, `MARVIN_ROOM_PASSWORD`, `MARVIN_ADMIN_PASSWORD` in `.env`, restart the token
server only (`make token`), and log in twice from two browser profiles.

## Still open

- `viewer` / `approver` roles and per-repo approval policies.
- Password mode: names are not unique identities; two people can share one.
- SAML if an IdP has no OIDC; SCIM.
