# Company-pilot plan (SSO, GitHub EE, audit, AWS image)

2026-09-14. **Status: 0–5 landed** (SSO settings, audit + export, GitHub App +
hooks, Packer AMI). Helm, gVisor, GPU STT, SCIM, `viewer`/`approver`,
multi-tenant rooms, and Cosign (5b) are still out.

What to build so a company can try Marvin and their security team has
something real to look at. Helm, gVisor, GPU STT, SCIM, `viewer`/`approver`, and
multi-tenant rooms are **out**. Signed container images are optional at the end.

Each phase is a stopping point. Say “stop after N”.

Dependency: **2 before 3**, **2 before 4c**. The rest can follow this order.

---

## 0. Land the license files (already written, not on `main`)

MIT + `ee/` + JWT + Settings → Enterprise. Empty `ee/`. Needed so later phases
can call `enabled("sso")` / `enabled("audit")` instead of inventing a second gate.

**Face:** you mint `make issue-license COMPANY=…`, they paste it, the panel
shows the company and the expiry. The core still runs with no key.

---

## 1. SSO a company can actually use

We already have `MARVIN_AUTH=header` + Caddy + oauth2-proxy (OIDC: Google, Okta,
Entra, Keycloak). That is the company path. Not building SAML unless their IdP
has no OIDC.

Still missing for a real trial:

- Settings (admin) for the issuer, client id/secret, email domain, which groups
  are admin — same rule as GitHub: paste in the browser, env is an override.
- Password mode: only emails on allowed domains (and an allow-list) may join.
  Header mode already has a real email from the IdP.
- A recording / “this room is transcribed and sent to &lt;provider&gt;” notice
  on join (GDPR; cheap; belongs with identity).
- Docs: clicks for Entra and Okta, including the groups claim.

**Out of this phase:** SAML, SCIM, finer roles.

**Face:** Maria opens the Marvin URL, company login, she is `maria@company.com`.
An admin group in Entra/Okta makes her admin. Alex with a gmail address cannot
use the shared password to sneak in.

---

## 2. Audit log and room tracing

Roadmap 8.2, the thing their auditor will ask for. Not Datadog APM. A **session**
is a meeting (room empty → occupied → empty). One append-only JSONL per session
under the state dir; each line hashes the previous; the head is signed when the
session closes.

Each line: who (Marvin identity), when, session id, turn if any, verb, payload.
Verbs at least: `join` / `leave`, `transcript`, `turn`, `tool`, `permission`,
`commit` / `push` / `pr`, `error`. Large blobs stored by hash, not inlined.

Worker logs print the same `session` / `turn` / `actor` ids (that is the
“tracing”). A session page in the app: people who were in it, and admins, can
read it. Retention setting (admin). Redaction can wait if you cut here.

**Face:** after the call, an admin opens the session and sees that Maria asked,
Bob approved `Bash`, and which commit hash went out. The file is still on the
box; nothing has left yet.

---

## 3. Ship the log to their S3 (and a JSON webhook)

Depends on 2. Settings → Enterprise (or a small Audit section): bucket, region,
prefix, optional object-lock. Credentials pasted in the UI, encrypted like
GitHub tokens. Every closed session (and, if they want, every N lines) is put
as JSONL. A webhook URL for “POST each record as JSON” covers most SIEMs
without us speaking Splunk.

**Face:** their security person finds `s3://company-marvin-audit/…/session.jsonl`
and can grep who approved the dangerous tool. Marvin still does not phone us.

---

## 4. GitHub in the Enterprise shape

Machine PAT and optional personal GitHub already work. This phase makes
authorship evidence.

- **4a. GitHub App (machine).** Manifest flow in the browser: create the app,
  install on the org, pick repos. Hourly installation tokens replace the shared
  PAT. Join-gate repo list is what the install can see.
- **4b. Authorship by infrastructure.** `git` wrapper + `commit-msg` hook in the
  sandbox: author = the Marvin identity who asked (name + email), committer =
  `marvin[bot]`, trailers `Requested-by`, `Approved-by`, `Marvin-Session`,
  `Marvin-Turn` written by us, model-written copies stripped. Commits signed
  with Marvin’s key (GitHub “Verified” on the bot).
- **4c. Verified at push.** `pre-push` + a worker check: author and turn must
  exist on the audit log (needs **2**). Mismatch refuses the push and logs it.

Personal GitHub stays optional (Alex still joins).

**Face:** the PR on github.com shows Maria as author, `marvin[bot]` as
committer, a session id, and no transcript. A forged `--author` does not push.

---

## 5. AWS image (not Helm)

Today Terraform boots a blank VM and cloud-init builds for 10–15 minutes. The
company shape is: **an AMI we publish** (Packer or Image Builder) with Docker
and the Marvin images already on disk. Terraform’s only job is VPC/subnet/EIP/
IAM/SSM and launch-from-AMI. First boot is minutes. Settings → Update still
pulls new code.

**5b (optional).** Cosign on the container images (and the AMI id in the
release notes). Skip if you stop after 5.

**Face:** their platform person applies Terraform in the company account, the
box is reachable, they paste the license and the GitHub App, SSO is already
pointed at Entra. No Helm.

---

## Suggested order

`0 → 1 → 2 → 3 → 4 → 5`. Test at the end of whatever prefix you keep.

If the company IdP is SAML-only, say so before 1 — that changes 1 from a
Settings wrap of oauth2-proxy into a real extra week.
