# Sessions and audit export

A **session** is a meeting: the room goes occupied, then empty for three minutes.
Each session is one append-only JSONL under `<state_dir>/audit/<room>/<id>.jsonl`.
Every line hashes the previous; the head is HMAC-signed when the session closes
(`.sig`). Worker logs carry the same `session` / `turn` / `actor` ids.

Verbs: `session_start` / `session_end`, `join` / `leave`, `transcript`, `turn`,
`permission`, `tool`, `error`. Long strings are truncated and hashed.

Settings → **Sessions** lists meetings you were in (admins see all) and the
retention (admin). Settings → **Audit export** (Enterprise) PUTs the JSONL to
your S3 bucket and/or POSTs it to a webhook when the meeting closes. Nothing is
sent to us. Env overrides: `MARVIN_AUDIT_S3_BUCKET`, `MARVIN_AUDIT_WEBHOOK`.

The sandbox `pre-push` hook refuses a push whose turn is not on this log
(`github.md`).
