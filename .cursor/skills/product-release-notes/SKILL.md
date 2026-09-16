---
name: product-release-notes
description: Keeps Marvin's detailed changelog and in-product release notes current. Use automatically when implementing a user-visible feature, fix, setup change, or workflow change, and before committing or pushing such changes.
---

# Product release notes

Before staging a user-visible change:

1. Read the diff and identify what a person using Marvin can now do, understand, or recover from.
2. Add the engineering record to `docs_and_changelog/CHANGELOG.md`.
3. Add or update the newest release in `docs_and_changelog/product-updates.json`.
4. Validate the JSON with `python -m json.tool docs_and_changelog/product-updates.json`.

## In-product copy

Write for someone running Marvin, not someone reading its source:

- Lead with the outcome: “Follow an update while Marvin restarts.”
- Use one short title and one plain sentence per change.
- Do not mention file paths, classes, containers, exit codes, or internal architecture unless the operator must act on them.
- Do not market routine maintenance as a feature.
- Group related changes into one release; keep newest releases first.

Use the current date and a stable lowercase `id` (`YYYY-MM-DD-short-name`). Do not invent a commit SHA before the commit exists.

Internal refactors, tests, and documentation-only edits do not need an in-product entry. They may still belong in the engineering changelog when noteworthy.

If the diff is not user-visible, explicitly say that no product release note is needed before committing.
