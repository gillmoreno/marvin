# Design explorations (2026-09-12)

Three alternative looks for Marvin, as clickable HTML prototypes. Nothing here is wired to the app; the goal is to
pick a direction (or a mix) before touching `web/src`. Open `index.html` in a browser, no server needed.

## Why

The current UI (`web/src/styles.css`) is a plain dark three-column layout: functional, but it has no point of view.
The brief: smart, agile, professional; "the future, but a usable future". Intended for startups and agile teams
rather than large enterprises, so it may have character. Mainly desktop; a trimmed mobile version where you mostly
talk and look (one pane at a time: Marvin, Transcript, Changes, Preview, Screen). A live voice-presence treatment
(the dictation-app waveform was the reference for "futuristic but functional") was asked for explicitly.

## What every prototype covers

- Sign in / room picker, with the admin-only "new room" form.
- The room on desktop: people + call controls | workspace tabs (Changes with file list and diff, ▶ web preview,
  ● shared screen) | Marvin / Transcript. Marvin's three states (listening, working, waiting for approval), the
  harness/model chips, tool calls coloured by family (exec / read / write), an approval banner with Allow / Always /
  Deny, attachments, the typed composer.
- Settings: this room, machine notes, account, GitHub.
- Mobile: real responsive layout under ~720px and a "Phone" toggle that shows the same layout in a phone frame on a
  laptop. All three drop the left column, the gutters and machine-notes editing; the approval banner sits above the
  talk/mute control regardless of which pane is open.
- A small prototype toolbar (screen switcher, Phone/Desktop, state cycler) that is not part of the product.

## The three directions

| | A · Control Room | B · Editorial | C · Signal |
|---|---|---|---|
| File | `a-control-room.html` | `b-editorial.html` | `c-signal.html` |
| Theme | near-black graphite | warm paper, light | soft graphite, glass |
| Idea | the room is an instrument that listens | the room is a live, well-typeset document | the voice is the interface |
| Voice presence | oscilloscope line in a top status rail; 5-bar VU next to the speaker | a living ink underline under the speaker; a hairline that writes itself while Marvin works | one radial signal element that breathes / tightens / turns amber, and passes its light to the speaker's avatar ring |
| Agent state | indicator lamps and small-caps readouts; approval inverts the readout to amber | the rule under the room title: still, writing, or dashed oxblood | the signal element itself, plus the ambient light of the room |
| Fonts | JetBrains Mono + IBM Plex Sans Condensed | Fraunces + Source Sans 3 + IBM Plex Mono | Manrope + DM Mono |
| Accent | electric amber `#FFB224` | oxblood `#7A1E2B` | mint `#8FF0D2`, amber `#F0B35C` for approvals |
| Base | `#0B0C0E` / `#1B1F24`, text `#E8EBEF` | paper `#F5F0E6`, ink `#1B1712` | `#1F2429` / `#262C32`, text `#ECE7DE` |
| Feels like | cockpit / terminal redesigned by a typographer | quality newspaper's digital product | a walkie-talkie with a screen |

Distinctive details worth keeping whichever way we go:

- **A**: the tool-call *ledger* (family label, argument, right-aligned tabular result like `exit 0 · 3.4s`, `+152`);
  the top status rail (room, state, branch, harness/model, who is live, session clock); tabular numerals everywhere.
- **B**: timestamps in a margin column; speaker names as run-in small caps; diffs as numbered figures with a caption
  line; the transcript reads as minutes, which matters for the audit-trail work (roadmap item 8).
- **C**: one focal animation and everything else quiet; the room opens on its most interesting moment (an approval
  pending); on mobile the bottom dock (signal · speaker · talk/mute · leave) is the whole control surface.

## Known limits of the prototypes

Gutters are drawn but not draggable. Share screen, commit, open PR, save notes, disconnect are visual only. Waveforms
are synthesised, not microphone input. Fonts come from Google Fonts and fall back to generic stacks offline. All
three honour `prefers-reduced-motion`.

## Next step

Pick one direction (or a base plus borrowed details), then port it into `web/src/styles.css` and the components
incrementally: tokens first (colours, fonts, radii), then the room layout, then the mobile breakpoint.
