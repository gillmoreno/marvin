# Enterprise Edition

Paid compliance pack. Same layout as GitLab / PostHog: this folder is public;
production use needs a paid subscription and a license key.

Licensed under `LICENSE` in this folder, not MIT. The rest of the repository
is MIT. Write-up: `docs_and_changelog/licensing.md`. What belongs here when
the features are real: `docs_and_changelog/security-and-compliance.md` §7.

The worker already checks the key (Settings → Enterprise). `enabled("sso")` and
`enabled("audit")` are honoured for OIDC save and session export. Code that
lands here should call the same gate. No key, those calls are false and the
free core still runs.
