# Frontend V3 — Interaction, Interpretation & Daily-Usage Polish

**Base:** `main` @ chart-shell merge  
**Status:** In progress on `cursor/frontend-v3-interaction-polish-7cfd`  
**Constraint:** Coaching engine feature-frozen. No large redesign.

## Review of current main (pre-V3)

| Priority | Pre-status | V3 action |
|----------|------------|-----------|
| 1 Cross-filter brush | Missing | Brush + URL `from`/`to` + CLEAR |
| 2 Period Inspector | Partial | New `PeriodInspector` |
| 3 WeekExplorer | Done | Extended actions (following 4 weeks) |
| 4 Year-over-year | Done | Already in Historikk |
| 5 Best period backtrace | Partial | Kept; clickable periods deferred |
| 6 Relationship detail | Done (basic) | Kept |
| 7–8 Coaching ↔ analytics | Partial | AthleteState drill-downs with URL presets |
| 9 Merged post-sync | Partial | `SinceLastUpdate` replaces dual cards |
| 10 New activity experience | Partial | Merged into SinceLastUpdate |
| 11 Activity detail V2 | Partial | Interpretation-first reorder |
| 12 Plan vs actual | Done | `/plan` |
| 13 Recommendation history | Done | `/plan` |
| 14 Annotations | Done | Historikk |
| 15 PWA | Missing | Manifest + icons + metadata |
| 16 Connection status | Missing | Subtle Connected / unavailable |
| 17 Analysis performance | Partial | Staggered fetches + selected-window context |
| 18 Legacy consolidation | Partial | Mer-nav labeled drill-down/legacy |
| 19 Tests | Partial | Range helpers, SinceLastUpdate, inspector, PWA |

## Definition of done (target flow)

TODAY → WHY → HISTORICAL SUPPORT → ANALYSIS → PERIOD → WEEK → SESSION  
NEW SYNC → WHAT CHANGED → SESSION IMPACT → PLAN IMPACT → NEXT RECOMMENDATION

Next major work after V3: deployment/local-runtime hardening — not another analytics feature wave.
