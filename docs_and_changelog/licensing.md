# Licensing

Same split as GitLab and PostHog. One public repo, two license files.

- Everything except `ee/` is MIT (`/LICENSE`). Anyone runs the free core without a
  key and without talking to us.
- `ee/` is the Marvin Enterprise license (`ee/LICENSE`). Read it, patch it, run
  it in production only with a paid subscription. Dev and test do not need a
  key.

A company pays when they need the compliance pack (SSO, audit, isolation).
Everyone else just uses the core. That is the whole product split.

## The key

We mint a JWT on our machine. They paste it in Settings → **Enterprise** (admin)
when the machine has no key. After that the page shows the company, seats, and
expiry — not an empty paste box. The string itself is shown masked (first and
last letters), the same way API keys are. Replace opens the box again. Remove
clears it.

The worker checks the signature with the public key in `worker/marvin/license.pub`,
offline, at start and again when someone saves. No phone-home. Anyone signed in
can see whether the machine is licensed (`GET /api/license`); a gold company
badge appears on the rail, in the room, and in Settings. Only an admin can
paste, replace, or remove the key. The masked hint is admin-only.

`MARVIN_LICENSE_KEY` is an override for automation. When it is set, it wins and
the panel says so — Settings cannot replace or remove it. A key pasted on the
page is just the masked string, with no origin label. Otherwise the key is
stored encrypted in the worker state dir (`license.json`), same as GitHub tokens.

The string carries company, expiry, seats, and which EE flags are on. Seats are
recorded. Flags that the worker honours today: `sso` (OIDC save +
`.oauth2-proxy.env`), `audit` (S3 / webhook export). A valid key is also
required to create the machine GitHub App. Domain allow-lists, the local session
JSONL, and the free core do not need a key. `ee.enabled("sso")` is the gate
modules under `ee/` should call.

## Issuing a key (us, not them)

The private key is **not** in this repo. It lives at
`~/.marvin-pilot/license-private.pem` on the machine that issues licenses.
Back it up. If it is lost, we mint a new pair and ship a new public key; old
tokens stop verifying.

```
make issue-license COMPANY=example.com EXPIRES=2027-11-01 SEATS=50
```

Or: `cd worker && uv run python ../tools/issue-license.py --company example.com --expires 2027-11-01 --seats 50`

`--features` defaults to `*` (everything in `ee/` for that year). Send them the
printed string. They paste it. No restart.

Customers never run the issuer. The script without the private key cannot mint
a valid token.
