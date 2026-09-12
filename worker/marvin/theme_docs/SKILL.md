---
name: marvin-theme
description: Create or change a theme for Marvin's web UI (colours, fonts, the voice-presence drawing). Use when someone in the room asks for a new look, a theme, a colour scheme, different fonts, dark/light mode, or to tweak how the Marvin UI looks.
---

# Marvin UI theme

A theme is a folder in the directory named by the environment variable `MARVIN_THEMES_DIR` (fall back to
`$HOME/.marvin/themes` if the variable is unset) containing `theme.json` and an optional `theme.css`. Themes are
**data and CSS only, never JavaScript**, and they do not change the components or the chrome: the app owns the
markup (Settings is a full page, the left footer is four icon buttons in a row, the phone is one pane at a time).
You only recolour, retype, and pick a presence drawing.

## Steps

1. Read `$MARVIN_THEMES_DIR/README.md` first. It is the contract: the JSON schema, every token with its default,
   the presence variants, and the stable class names you may style. Do not guess selectors that are not listed.
2. Decide the direction in one sentence (mood, light or dark, one accent colour, a font pairing, which presence
   drawing). Prefer one strong idea over many small ones. Do not use Inter, Roboto, Arial or system-ui as the
   display font unless asked.
3. Pick an id (`^[a-z0-9][a-z0-9-]{1,39}$`, not `control-room`, `editorial` or `signal`) and write
   `$MARVIN_THEMES_DIR/<id>/theme.json`. Set every colour token the mood needs; keep body text at WCAG AA contrast
   against `--bg` and `--panel`. Set `scheme` to match.
4. Only if tokens are not enough, write `theme.css` using the listed class names. Recolour and retype. Do not
   rearrange the chrome: no centered Settings dialog, no max-width on `.modal`, no wrapping or resizing `.left-foot`
   buttons, do not unhide `.lk-button-group-menu`. Keep `.settings-btn`, `.m-tabs` and approval buttons visible.
   Wrap motion in `@media (prefers-reduced-motion: no-preference)`.
5. Re-read both files once and check: valid JSON, no `url(` except fonts, no `@import`, id matches the folder.
6. Reply in one or two lines: the theme's name and id, the idea, and "it is in Settings → Appearance now; click it
   to try it, an admin can make it the default". The UI picks it up when this turn ends; no restart.

To change an existing custom theme, edit its files in place; the UI reloads it when the turn ends. Never edit
`README.md` or `default.json` in that directory.
