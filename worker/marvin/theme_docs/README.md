# Marvin UI themes: the contract

This directory holds custom themes for Marvin's web UI. Each theme is one folder:

```
<this directory>/
  README.md                 this file (rewritten by the worker at start; do not edit)
  default.json              {"id": "..."} the machine default an admin picked in Settings (do not edit by hand)
  <theme-id>/
    theme.json              required: name, colour scheme, fonts, presence variants, tokens
    theme.css               optional: extra CSS, automatically scoped to this theme
```

A theme is **data and CSS, never JavaScript**. The app owns the markup and the behaviour; a theme recolours,
re-types and re-arranges it. Themes cannot break the app: a theme that fails validation is listed in Settings
with the reason and cannot be activated, and the app falls back to the default theme if the active one fails to load.

Three themes are built into the app and are not in this directory: `control-room` (dark, monospace, an oscilloscope
as the room's heartbeat; the default), `editorial` (light, warm paper, serif, voice rendered as ink), `signal`
(graphite glass, one luminous radial signal element). Their ids are reserved. Their CSS is a good reference: it is
served at `/assets/` of the web app and is also summarised at the end of this file.

## Workflow for the agent

1. Pick an id: `^[a-z0-9][a-z0-9-]{1,39}$`, not one of the built-in ids. Create `<id>/` here.
2. Write `theme.json` (schema below). Start from the example at the end of this file.
3. Optionally write `theme.css` for anything tokens cannot express (layout tweaks, animations, textures).
4. Tell the person: the theme appears in **Settings → Appearance** as soon as your turn ends (the UI re-reads this
   directory after every turn). They click it to try it; an admin can make it the machine default there. Nothing
   needs a restart.
5. To change an existing custom theme, edit its files in place. The UI reloads the active theme after every turn.

Do not edit the built-in themes (they are not here). Do not touch `default.json` or this README.

## theme.json

```json
{
  "name": "Night Shift",
  "description": "Deep navy, warm amber accent, rounded and quiet.",
  "author": "gil",
  "scheme": "dark",
  "fonts": {
    "ui": "Manrope",
    "display": "Manrope",
    "mono": "DM Mono",
    "google": "family=Manrope:wght@400;500;600;700&family=DM+Mono:wght@400;500"
  },
  "presence": { "agent": "orb", "speaker": "bars" },
  "tokens": {
    "--bg": "#0e1420",
    "--panel": "#131a28",
    "--accent": "#f0b35c"
  }
}
```

| field | required | rules |
|---|---|---|
| `name` | yes | 1–60 characters, shown in Settings |
| `description` | no | ≤ 300 characters |
| `author` | no | ≤ 60 characters |
| `scheme` | yes | `"dark"` or `"light"`; sets `color-scheme` for form controls and scrollbars |
| `fonts.ui` / `fonts.display` / `fonts.mono` | no | font-family names; the app appends its own fallbacks. Fill `--font-*` tokens |
| `fonts.google` | no | the query part of a Google Fonts CSS2 URL (`family=...&family=...`), letters, digits, `+ : ; @ , & = . -` only. The app loads `https://fonts.googleapis.com/css2?<google>&display=swap`. Leave out to use system fonts |
| `presence.agent` | no | how Marvin's state is drawn: `dot` (default), `scope`, `ink`, `orb`, `bars` |
| `presence.speaker` | no | how a speaking person is drawn: `dot` (default), `bars`, `ink`, `ring` |
| `tokens` | no | map of CSS custom properties from the table below to values. Values: ≤ 200 characters, no `url(`, `;`, `{`, `}`, `<` |

Unknown fields are ignored. Unknown token names are ignored with a warning.

## Tokens

Every token has a default from the base stylesheet, so a theme only sets what it changes. Set them in `tokens`
(preferred) or in `theme.css` under `:root`.

| token | what it colours | base default |
|---|---|---|
| `--bg` | page background | `#0f1115` |
| `--panel` | sidebars, cards, modal | `#161a21` |
| `--panel-2` | inset surfaces: inputs, code, tool output | `#0b0d11` |
| `--line` | hairlines and borders | `#262c36` |
| `--fg` | text | `#e6e8eb` |
| `--fg-2` | secondary text (questions, captions) | `#b0b8c1` |
| `--dim` | muted text, labels | `#8b949e` |
| `--accent` | primary buttons, selection outline, Marvin working | `#7aa2f7` |
| `--accent-fg` | text on `--accent` | `#0b0d11` |
| `--sel` | hover / selected row background | `#1c2a3a` |
| `--ok` | live, added, "listening" | `#3fb950` |
| `--warn` | attention, waiting for approval, "always allow" | `#d29922` |
| `--warn-bg` | background behind approval banners | `#1f1a10` |
| `--bad` | errors, deny, deleted | `#f85149` |
| `--exec` / `--read` / `--write` | tool families: run, look, change | `#f0883e` / `#79c0ff` / `#d2a8ff` |
| `--ins-bg` / `--del-bg` | diff line backgrounds | `rgba(63,185,80,.12)` / `rgba(248,81,73,.12)` |
| `--glow` | soft glow colour used by presence variants and busy tabs | `rgba(122,162,247,.55)` |
| `--font-ui` | body and controls | `system-ui, sans-serif` |
| `--font-display` | titles (`h1`, room name, speaker names) | inherits `--font-ui` |
| `--font-mono` | code, paths, diff, timestamps | `ui-monospace, Menlo, monospace` |
| `--text` | base font size | `14px` |
| `--radius` | small controls | `6px` |
| `--radius-lg` | panels, modal | `10px` |
| `--shadow` | panel shadow | `none` |
| `--left-w` / `--right-w` | default column widths (people can still drag them) | `240px` / `360px` |

## Presence variants

Marvin's state and who is speaking are drawn by the app; the theme chooses the drawing and colours it.
The element is `.presence` with `data-kind="agent"|"speaker"`, `data-variant="<variant>"`, and for the agent
`data-state="offline"|"idle"|"thinking"|"waiting_approval"`. It carries a live `--level` custom property (0–1) with
the audio level of the speaker (or Marvin's synthetic activity). Colours come from `--presence` (defaults to
`--accent`, `--warn` while waiting for approval, `--dim` when offline) and `--glow`.

- `dot`: a 9px dot (the plain look)
- `scope`: an oscilloscope line, flat when quiet
- `bars`: five VU bars
- `ink`: a hand-drawn underline that thickens with the level
- `orb`: a ring of radial ticks around a core; tightens while working, stills while waiting
- `ring`: a pulsing ring around the speaker's avatar (speaker only)

## Markup the theme can rely on

Stable class names and attributes. Anything not listed here may change without notice.

```
html[data-theme="<id>"][data-scheme="dark|light"]
  .join                         sign-in / project picker card    h1  p  label  input  button  .signedin  .badge
    .rooms  .rooms-head  .room-list li(.sel) .dot b .repo   .newroom
  .layout[data-state="offline|idle|thinking|waiting_approval"]   the room, desktop
    .rail                       top status rail: .rail-cell  .rail-room  .rail-state  .rail-scope .rail-presence(.presence)  .rail-k  .rail-clock  .rail-live  .rail-hide-m
    .left                       .left-head h1 .room  |  .left-body  .left-sect  .people li[data-agent][data-speaking][data-away] .dot .nm .role .who-st .who-st-txt .presence  |  .applinks h2.left-sect a .url  |  .left-foot .settings-btn .sp  |  .lk-control-bar
    .gutter
    .center .workspace          .ws-tabs button(.on)(.live) .dot.rec  .ws-actions .url .btn  |  .ws-body
      .changes                  header .branch .stat .ins .del .btns  |  .repo-tabs button(.on)  |  .changes-body  .files li(.sel) .st(.st-M|.st-A|.st-D|.st-R) .path .nums  |  .diff .dl(.ins|.del|.hunk|.meta)
      .preview (iframe)  .screenshare video .screenshare-cap  .ws-foot
    .right                      .side-tabs button(.on)(.busy)(.attention) .dot
      .marvin                   .marvin-head .marvin-r1 .marvin-r2 .status(.idle|.thinking|.waiting_approval|.offline) .status-name .status-text  .modelpick(.pinned) .pick-k  .iconbtn(.on)(.stop)(.always-btn) .btn-label
                                .notice  |  .turns .turn .q .a .meta  .tools li(.running)(.err) code(.exec|.read|.write|.other) .arg pre
                                .approvals .approval pre .btns button(.ghost)(.danger)  |  .attachments .chip  |  .typed input button
      .transcript               h2  p(.interim)[data-speaker="agent|human"] .t b.w .txt
  .layout[data-mobile]          the room on a phone: one pane at a time
    .m-top                      .m-title .room  .presence  .m-state  .settings-btn
    .m-pane[data-pane="marvin|transcript|changes|app|screen"]     contains the same .marvin / .transcript / .changes / .preview / .screenshare as above
    .m-tabs button(.on)(.live)
    .m-bar                      .m-speaker .presence .who small  .m-talk(.muted)  .m-leave
  .lk-control-bar .lk-button    LiveKit's mic / share / leave buttons in the left column (light touch only)
  body.resizing                 set while someone drags a .gutter
  .modal-back.settings-screen .modal   header .lbl h2 .room .sp button  |  .sgrid > section(.appearance) h3 p(.dim)(.small) code textarea .btns .status(.ok|.bad)
  .theme-cards .theme-card(.on)(.invalid) .swatches                 the Appearance section of Settings
  button  button.ghost  button.danger  .iconbtn   input  select  textarea   .dot(.idle|.thinking|.waiting_approval|.offline|.rec)   .badge  .tag  .hint  .dim  .error
```

## theme.css

Plain CSS. The app scopes every rule to `html[data-theme="<id>"]` when it loads the file, so write selectors as
if the theme were the only stylesheet (`.left { ... }`, `:root { --bg: ... }`). `@media`, `@keyframes`,
`@supports`, `@container` and `@font-face` work. Rules:

- Because of that prefix your rules outrank the base stylesheet's, even a bare `button { padding: ... }` beats the
  base's `.iconbtn`. When you restyle an element type (`button`, `input`, `p`), re-state the small variants you did
  not mean to change: `.iconbtn { padding: 0; width: 28px; height: 28px; }`, `.m-tabs button`, `.dot`.
- No `@import`. `url(...)` only with `data:` or `https://fonts.googleapis.com/` / `https://fonts.gstatic.com/`.
- No `expression(`, `javascript:`, `behavior:`, `-moz-binding`, or `<` anywhere. Maximum 200 KB.
- Keep `.settings-btn`, `.m-tabs`, `.lk-control-bar` and the approval buttons visible and reachable: people must
  always be able to switch theme, mute, leave and answer an approval. Keep body text at WCAG AA contrast.
- Prefer tokens over selectors; prefer motion that carries meaning (speaking, working, waiting) over decoration,
  and wrap it in `@media (prefers-reduced-motion: no-preference)`.
- Do not change what elements mean: the `.ins` colour stays "added", `.warn` stays "needs attention".

## Example: a complete small theme

`night-shift/theme.json`

```json
{
  "name": "Night Shift",
  "description": "Deep navy with an amber accent; rounded, quiet, no monospace outside code.",
  "scheme": "dark",
  "fonts": { "ui": "Manrope", "display": "Manrope", "mono": "DM Mono", "google": "family=Manrope:wght@400;500;600;700&family=DM+Mono:wght@400;500" },
  "presence": { "agent": "orb", "speaker": "bars" },
  "tokens": {
    "--bg": "#0d1220", "--panel": "#121a2b", "--panel-2": "#0a0f1a", "--line": "#1f2a40", "--sel": "#18233a",
    "--fg": "#e9edf5", "--fg-2": "#b8c1d3", "--dim": "#7f8ba3",
    "--accent": "#f0b35c", "--accent-fg": "#1a1206", "--glow": "rgba(240,179,92,.45)",
    "--ok": "#6fd39a", "--warn": "#f0b35c", "--warn-bg": "#1f1a10", "--bad": "#f07a7a",
    "--radius": "10px", "--radius-lg": "16px", "--shadow": "0 12px 40px rgba(0,0,0,.35)"
  }
}
```

`night-shift/theme.css`

```css
.left, .right { box-shadow: var(--shadow); }
.rail { display: none; }                       /* this theme has no status rail */
.turn { border-left-width: 2px; }
@media (prefers-reduced-motion: no-preference) {
  .side-tabs button.busy { animation: nightshift-pulse 1.6s ease-in-out infinite; }
}
@keyframes nightshift-pulse { 50% { box-shadow: 0 0 0 6px transparent; } }
```

## The built-in themes, in short

- `control-room`: `--bg #0B0C0E`, panels `#101215`/`#15181C`, hairlines `#22272D`, text `#E8EBEF`, accent
  electric amber `#FFB224`, diff `#5CD387`/`#F2716B`; fonts JetBrains Mono (ui, mono) + IBM Plex Sans Condensed
  (display); presence agent `scope`, speaker `bars`; the rail is visible; radii 3px; tabular numerals.
- `editorial`: light; paper `#F5F0E6`, ink `#1B1712`, rules `#D6CDBD`, accent oxblood `#7A1E2B`, live green
  `#3F7A4C`; fonts Fraunces (display) + Source Sans 3 (ui) + IBM Plex Mono; presence agent `ink`, speaker `ink`;
  rail hidden; timestamps in a margin column; diffs framed like figures.
- `signal`: graphite `#1F2429`/`#262C32`, warm text `#ECE7DE`, accent mint `#8FF0D2`, approvals amber `#F0B35C`;
  fonts Manrope + DM Mono; presence agent `orb`, speaker `ring`; rail hidden; glass panels with large radii.
