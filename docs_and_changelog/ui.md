# Marvin UI

Settings and forms use the same card, field, and button (`web/src/ui`). Sign-in, GitHub, coding agents, sessions, audit export, Enterprise, and this machine are one map. Tailwind is for **layout** (`flex`, `grid`, `gap`). We do not use Material, shadcn, or Tailwind preflight — they fight the dark rail.

Enterprise-only cards (who may join, company sign-in, audit export, and creating a GitHub App) use `Card locked` / `Lock`: a 🔒 on the title, a gold “paste a license” line, and an inert dimmed body. The free core (account, sessions on this machine, a pasted GitHub token, coding agents) stays editable.

Agents: `.cursor/skills/marvin-ui/SKILL.md`.
