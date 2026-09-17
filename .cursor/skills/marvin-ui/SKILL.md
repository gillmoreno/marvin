---
name: marvin-ui
description: >-
  Builds Marvin web UI from the reusable kit in web/src/ui (Field, Input, Button, Card)
  plus Tailwind layout utilities. Use when adding or changing Settings, forms, inputs,
  buttons, cards, or any web/src React UI so controls are not restyled from scratch.
---

# Marvin UI

Settings, setup, and forms are a solved problem. Do not invent a new input, button, or card.

## Before you draw anything

1. Import from `web/src/ui`.
2. If the control does not exist yet, add it to `web/src/ui` and use it. Do not add a one-off `<input>` in a page.
3. Use Tailwind only for **layout** (`flex`, `grid`, `gap-*`, `min-w-0`, `w-full`). Appearance lives on `.ui-*` in `web/src/ui/ui.css`.
4. Keep Marvin's look: paper `#eef0f1`, cards white, ink `#1d2227`, gold `#f0ad3e` on the rail. Do not switch to Material, shadcn defaults, or a new palette.

## Controls

| Need | Use |
| --- | --- |
| White settings block | `Card` (`<h3>` first); `locked` for Enterprise-only cards |
| Group inside a card | `Block` with a title |
| Label above a control | `Field` + `Input` or `Textarea`; wrap several in `Fields` |
| Primary / quiet / destructive action | `Button` `primary` / `ghost` / `danger` |
| A row of buttons | `Actions` |
| Muted sentence | `Text` (`tone="ok"` / `"bad"` for status) |
| Numbered guide | `Steps` |
| Choice chips | `Chips` + `Chip` |
| Long secret or URL | `<code className="ui-code">` |
| A few labeled facts | `Facts` (`{ label, value }[]`) |
| Enterprise-only body | `Lock` (`on={!ee}`), or `Card locked` |

```tsx
import { Actions, Button, Card, Field, Fields, Input, Text } from "./ui";

<Card>
  <h3>GitHub</h3>
  <Text>Needed only for the device-code button.</Text>
  <Fields>
    <Field label="Client ID" wide>
      <Input value={id} onChange={(event) => setId(event.target.value)} />
    </Field>
  </Fields>
  <Actions>
    <Button disabled={busy} onClick={() => void save()}>Save</Button>
    <Button variant="ghost" onClick={cancel}>Cancel</Button>
  </Actions>
</Card>
```

## Do not

- Put a label and an input on one wrapping line.
- Style a raw `<button>` / `<input>` with a new class on the page.
- Add Tailwind preflight, Material, Chakra, or shadcn. They fight the rail.
- Use Claude's generic frontend-design skill to restyle Settings. That skill is for throwaway look explorations, not product chrome.

## New control

Add the React wrapper in `web/src/ui`, the chrome in `ui.css` as `.ui-*`, export it from `index.ts`, and use it in the page. One source of spacing: 16px inside a card, 7px between a label and its field, 40px-tall controls.
