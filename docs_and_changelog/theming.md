# Theming

Marvin's web UI is themable. Three themes ship with the app; any number more can be added on a machine, by a person
or by Marvin itself from inside a room ("Marvin, make me a theme: light, warm, serif, green accent"). This file is
the design of that system. The contract a theme is written against is `worker/marvin/theme_docs/README.md`; the
agent's skill is `worker/marvin/theme_docs/SKILL.md`. The three built-in themes were designed as clickable
prototypes first: `design-explorations/`.

## What a theme is

A theme is **data and CSS, never code**:

- `theme.json`: name, description, `scheme` (dark | light), Google Fonts families, which **presence variant** draws
  Marvin's state and who is speaking, and a map of **tokens** (CSS custom properties: colours, fonts, radii, sizes).
- `theme.css` (optional): plain CSS against a documented set of stable class names. The loader scopes every rule to
  `html[data-theme="<id>"]` through the CSSOM (`:root`/`html`/`body` are rewritten to the prefix; `@media`,
  `@keyframes`, `@supports`, `@container` are walked), so a theme cannot leak into another and is written as if it were
  the only stylesheet.

The app owns the markup and the behaviour. The base stylesheet (`web/src/styles.css`) is structure plus neutral
defaults, everything through tokens; a theme only sets what it changes. The presence drawings (`web/src/theme/Presence.tsx`)
are React components fed by the agent state and the real audio level: `dot`, `scope` (oscilloscope), `bars` (VU),
`ink` (an underline that thickens), `orb` (radial ticks), `ring`. The theme picks one and colours it; `--level`
(0..1) is kept live on the element so theme CSS can react to it too.

Why this shape: it is what makes themes "vibe codable" *and* safe. An agent can write JSON and CSS reliably; it
cannot break the app with them, because there is no JavaScript, the DOM contract is fixed, the worker validates the
files, and the loader falls back to the default theme if the active one fails to load.

## Built-in themes

| id | scheme | idea | presence |
|---|---|---|---|
| `control-room` (default) | dark | an instrument panel: hairlines, tabular mono, indicator lamps, one amber accent, a status rail with an oscilloscope | scope / bars |
| `editorial` | light | the room as a live, well-typeset document: paper, serif names, timestamps in the margin, voice as ink | ink / ink |
| `signal` | dark | graphite glass with one luminous mint signal element that breathes, tightens and turns amber | orb / ring |

They live in `web/src/theme/builtin/<id>.{json,css}` and are bundled. Their ids are reserved.

## Where custom themes live, and how they get there

`<state_dir>/themes/<id>/theme.json` (+ `theme.css`). The worker (`worker/marvin/themes.py`, `ThemeStore`):

- writes the contract into `<state_dir>/themes/README.md` at every start,
- mounts the directory into every room sandbox at the same path and names it in the agent's environment as
  `MARVIN_THEMES_DIR` (also forwarded through `docker exec`),
- installs the Claude Code skill `marvin-theme` into each room's HOME (`~/.claude/skills/marvin-theme/SKILL.md`);
  for the other harnesses the room prompt says to read the README in `MARVIN_THEMES_DIR` first,
- validates every theme on read: id shape, reserved ids, JSON schema, token names and values (no `url(`, `;`, braces),
  Google Fonts query shape, CSS size cap, no `@import`, `url()` only for `data:` and Google Fonts, no `expression(`,
  `javascript:`, `<`. Invalid themes are still listed, with their errors, and their CSS is never served,
- serves `GET /themes`, `GET /themes/{id}/theme.css`, `PUT /themes/default` (admin), `DELETE /themes/{id}` (admin),
  proxied by the token server at `/api/themes...` (reads for anyone signed in, writes for admins).

The web app re-reads the list when someone signs in, whenever Settings is open, and **every time one of Marvin's
turns ends**, so a theme the agent just wrote shows up without a reload; a one-line "New theme X · try it" appears
under the people list.

## Choosing

Per the "configuration lives in the UI" rule:

- **Your pick** (Settings → Appearance) is per browser (`localStorage["marvin.theme"]`); "follow it" goes back to
  the machine default. The last applied custom theme is cached in `localStorage` so it renders on the login screen
  before `/api/themes` is reachable.
- **Machine default** is set by an admin in the same section (`<state_dir>/themes/default.json`). `MARVIN_THEME`
  in the environment overrides it (shown as "from the environment" in Settings), and without either the default is
  Control Room.
- A theme that fails to load or turns invalid falls back to the machine default, then to Control Room.

## The phone layout

Under 720px the room is one pane at a time (`web/src/Mobile.tsx`): Marvin, Transcript, Changes, one tab per running
app and per shared screen; a bottom bar with your own level, a large talk/mute button and leave. It is theme-neutral
structure (`.m-top`, `.m-pane[data-pane]`, `.m-tabs`, `.m-bar`) that themes re-skin like everything else.

## Adding a hook

If a theme needs to style something not in the contract, add the class or attribute in the app, document it in
`theme_docs/README.md` (the "Markup the theme can rely on" block) and keep it stable from then on. Do not rename
listed classes.

## Limits

- Control Room is a close port of `design-explorations/a-control-room.html` (full-page Settings, the status rail,
  the left-column footer, the transcript grid). Editorial and Signal keep their own layouts on the same hooks.
- Only one theme is active at a time; `@keyframes` names are not namespaced (the loader replaces the whole sheet).
- Google Fonts are fetched from the browser; an air-gapped deployment should leave `fonts.google` out and rely on
  system fonts (the tokens still apply).
- Themes do not ship with rooms/projects; they are per machine.
