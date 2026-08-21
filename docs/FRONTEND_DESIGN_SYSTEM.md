# Frontend Design System (V1)

## Decision

**New coaching UX uses Tailwind CSS + existing shadcn `ui/*` components + CSS custom properties.**

Legacy metric pages keep styled-components until migrated. Do not dual-style new components with ad-hoc hex in styled-components.

## Why

- `ui/button`, `ui/card`, `ui/badge`, CSS variables, and Tailwind already exist  
- React Query + App Router fit token-based utility classes  
- Avoid rewriting 14 styled-components pages in one PR  

## Tokens

Defined in `frontend/src/app/globals.css` and mirrored in `tailwind.config.ts`:

| Category | Examples |
|----------|----------|
| Surface | `--surface`, `--surface-elevated`, `--surface-muted` |
| Text | `--foreground`, `--muted-foreground` |
| Status | `--status-positive`, `--status-warning`, `--status-critical`, `--status-info`, `--status-neutral` |
| Session | `--session-easy`, `--session-long`, `--session-threshold`, `--session-vo2`, `--session-race`, `--session-strength`, `--session-rest` |
| Spacing / radius | Tailwind scale + `--radius` |

## Status semantics (not color-only)

Always pair color with text/icon:

- ↑ improving · → stable · ↓ declining · ? uncertain  
- freshness: fresh / aging / stale / missing  
- confidence: high / medium / low  

## Density (compact cockpit)

Coaching surfaces prefer **dense information** over airy marketing layout:

- Section gaps: `space-y-3` / `gap-3` (not 6)
- Card padding: `px-3 py-2.5` (not `p-5`/`p-6`)
- Page titles: `text-xl`–`text-2xl` (not `text-3xl`/`text-4xl`)
- Chips / meta: `text-xs`–`text-[10px]`
- Sidebar: `w-44`, tighter nav `py-1.5`
- Keep touch targets ≥ ~32px for primary controls; do not crush mobile bottom nav

## Typography

Root layout keeps Inter for continuity with legacy pages. Coaching surfaces use clear hierarchy (title → decision → meta) without competing display fonts.

## Charts (later)

Canonical wrappers planned: `MetricTrendChart`, `LoadChart`, `RecoveryChart`. New pages should prefer them when added; legacy charts stay until Sprint 7.

## Progressive disclosure

1. Decision  
2. Why (reason chips)  
3. Evidence / diagnostics (expand)

Never put ValidationRun / Alembic / model registry on Today.
