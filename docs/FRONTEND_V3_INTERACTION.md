# Frontend V3 — Interaction, Interpretation & Daily-Usage Polish

**Base:** `main` (merged PR #62–#64)  
**Constraint:** Coaching engine feature-frozen. No large redesign.

## Status — waves complete

| Priority | Status |
|----------|--------|
| 1 Cross-filter brush | Done — Brush + URL `from`/`to` + CLEAR |
| 2 Period Inspector | Done |
| 3 WeekExplorer | Done — previous / similar / following 4 weeks |
| 4 Year-over-year | Done — one-metric chart (duration/distance/sessions/TSS) |
| 5 Best period backtrace | Done — clickable 4/8/12w opens URL range |
| 6 Relationship detail | Done — lag + aligned timeline + scatter link |
| 7–8 Coaching ↔ analytics | Done — drill-downs + historical support link |
| 9–10 Post-sync / new session | Done — `SinceLastUpdate` |
| 11 Activity detail V2 | Done — interpretation-first |
| 12–14 Plan / ledger / annotations | Done — recommendation history filters (followed/modified/skipped) |
| 15 PWA | Done — manifest + SW offline shell |
| 16 Connection status | Done — polls `/health/live` |
| 17 Analysis performance | Done — staggered + selected-window |
| 18 Legacy consolidation | Done — labeled Mer-nav (no deletes) |
| 19 Tests | Done — range / inspector / backtrace / PWA / SW / history |
| Local-runtime hardening | Done — Compose, Dockerfiles, `/health/ready` 503, deploy docs |

## Definition of done flows

TODAY → WHY → HISTORICAL SUPPORT → ANALYSIS → PERIOD → WEEK → SESSION  
NEW SYNC → WHAT CHANGED → SESSION IMPACT → PLAN IMPACT → NEXT RECOMMENDATION

**Roadmap status:** Planned Frontend V3 and local-runtime hardening waves are complete. Optional later work (public PaaS, API auth, Postgres, full offline sync) is explicitly out of scope for these waves.
