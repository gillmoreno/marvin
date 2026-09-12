---
name: marvin-theme
description: Create or change a theme for Marvin's web UI (colours, fonts, the voice-presence drawing, layout tweaks). Use when someone in the room asks for a new look, a theme, a colour scheme, different fonts, dark/light mode, or to tweak how the Marvin UI looks.
---

# Marvin UI theme

A theme is a folder in the directory named by the environment variable `MARVIN_THEMES_DIR` (fall back to
`$HOME/.marvin/themes` if the variable is unset) containing `theme.json` and an optional `theme.css`. Themes are
data and CSS only, never JavaScript; the app scopes the CSS and validates the JSON, so a theme cannot break the UI.

## Steps

1. Read `$MARVIN_THEMES_DIR/README.md` first. It is the contract: the JSON schema, every token with its default,
   the presence variants, and the stable class names you may style. Do not guess selectors that are not listed.
2. Decide the direction in one sentence (mood, light or dark, one accent colour, a font pairing, which presence
   drawing). Prefer one strong idea over many small ones. Do not use Inter, Roboto, Arial or system-ui as the
   display font unless asked.
3. Pick an id (`^[a-z0-9][a-z0-9-]{1,39}$`, not `control-room`, `editorial` or `signal`) and write
   `$MARVIN_THEMES_DIR/<id>/theme.json`. Set every colour token the mood needs; keep body text at WCAG AA contrast
   against `--bg` and `--panel`. Set `scheme` to match.
4. Only if tokens are not enough, write `theme.css` using the listed class names. Keep `.settings-btn`, `.m-tabs`,
   `.lk-control-bar` and approval buttons visible. Wrap motion in `@media (prefers-reduced-motion: no-preference)`.
5. Re-read both files once and check: valid JSON, no `url(` except fonts, no `@import`, id matches the folder.
6. Reply in one or two lines: the theme's name and id, the idea, and "it is in Settings → Appearance now; click it
   to try it, an admin can make it the default". The UI picks it up when this turn ends; no restart.

To change an existing custom theme, edit its files in place; the UI reloads it when the turn ends. Never edit
`README.md` or `default.json` in that directory.
