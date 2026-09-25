---
name: frontend-qc
description: >-
  Quality-checks Marvin web UI for readable contrast, a visible unclipped logo,
  and the split between the dark shell and the light room. Use when adding or
  changing web/src UI, themes, color, type, the sidebar, the brand, or when
  the user mentions contrast, readability, the logo, light mode, or dark mode.
---

# Frontend quality check

Marvin is one dark theme. Projects, Settings, and the inside of a project share it.

| Surface | Where | Canvas | Ink |
| --- | --- | --- | --- |
| App | Rail, Projects, Settings, room, transcript, changes | `#0f1115` | `#e8eaef` |
| Card | Settings cards, room side panel | `#161920` | `#e8eaef` |

Do not paint the room, the transcript, or a settings card white. A white card on the dark shell is a failure. Cream logo word `#f5f3ee` stays on the dark rail only.

Build with the `marvin-ui` skill. This skill is the check after the pixels exist.

## When to run

After any change a person can see in `web/src`, before you say the work is done. Also run it when the user pastes a screenshot of the app.

## Logo

The brand is an image, not a redrawn word.

- Expanded rail and sign-in: `/marvin-lockup.svg` (`.join-brand-lockup-img`). Cream word `#f5f3ee`, teal mark `#2dd4bf`. Dark surfaces only.
- Collapsed rail: `/marvin-mark.svg` (`.join-brand-mark-img`). The square mark stays; the word does not.
- The full word **Marvin** must be visible, including the M and the pip on the i. A clipped lockup that reads “arvin” is a failure.
- Do not put the cream word on white or paper. Do not recolor the SVG with CSS except the existing enterprise glow.
- `alt="Marvin"`. The image must load (not a broken icon, not an empty box).

## Contrast

Readable means WCAG AA, measured, not guessed.

- Text under 18px, and bold text under 14px: **4.5:1** against the real background.
- Large text and UI boundaries (icons, input borders, the focus ring, the logo mark against its canvas): **3:1**.
- Placeholder, disabled, and “dim” copy that a person must read to use the screen: **4.5:1**. Dim decorative metadata that repeats a label already on screen: **3:1**.
- Check the pair that is actually painted: text color against the element’s own background, not against the page behind a card. A white card is a failure, not a second theme.

Ratios:

```bash
python3 .cursor/skills/frontend-qc/scripts/contrast.py '#e8eaef' '#161920'
```

Pass/fail is the script’s exit code. Do not hand-wave a ratio.

In the browser, sample computed colors for the elements you changed (`getComputedStyle` color and backgroundColor, walking up until the background is opaque). Feed those hex values to the script. A screenshot is not a contrast check.

## Checklist

Copy and complete this. A fail blocks “done”.

```
Frontend QC:
- [ ] Logo: correct asset, loaded, unclipped, on a dark surface
- [ ] Projects, Settings, and the room use the same dark canvas
- [ ] Cards are `#161920` with light ink, not white islands
- [ ] Dim / placeholder / disabled text that carries meaning ≥ 4.5:1
- [ ] Icons, borders, and the mark ≥ 3:1
- [ ] Focus ring visible on the surface it sits on
- [ ] No text overflow that hides a word (logo, email, button)
```

## Report

Lead with failures. One line per pair: surface, element, foreground, background, ratio, pass or fail. Then the logo line. Fix failures before finishing. Do not restyle a passing surface to make the report look thorough.

## Known traps

- The lockup’s viewBox is wide. A narrow rail clips the M. Give the image its intrinsic width; do not crop it with `overflow: hidden` on the brand row.
- The room, transcript, and changes use the same tokens as Projects. Do not reintroduce a white work surface.
- Gold `#f0ad3e` and teal `#2dd4bf` are accents. Teal on white often fails for small text. Use teal for large marks and for text on the dark shell; on white, use a darker teal or the ink color.
- Collapsing the rail must still show the square mark, not a slice of the wordmark.
