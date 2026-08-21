# Frontend Analytics UX — Audit (V1)

**Repo:** epoppe/Treningsanalyse  
**Base:** `main` @ coaching V9 freeze  
**Goal:** Replace disconnected metric pages with a coherent **ANALYSIS WORKSPACE** at `/analyse`.

Coaching/model algorithms remain frozen. New HTTP routes only **wrap/compose** existing services.

---

## Classification legend

| Tag | Meaning |
|-----|---------|
| **KEEP** | Remains as-is (or as drill-down) |
| **REUSE** | Component/API reused inside `/analyse` |
| **MERGE** | Fold into workspace tabs |
| **REPLACE** | Data path or chart stack replaced |
| **MOVE_TO_ADVANCED** | Power-user UI nested under Advanced |
| **DEPRECATE_LATER** | Remove after workspace covers use cases |

---

## Current pages

| Route | Purpose | Classification | Notes |
|-------|---------|----------------|-------|
| `/statistikk` | Volume + monthly YoY | **MERGE** → Historikk | Bulk loads ≤1000 activities client-side |
| `/sammenhenger` | Raw X/Y Pearson scatter | **MOVE_TO_ADVANCED** | Keep scatter; default becomes question cards |
| `/analytics` | EF, decoupling, CS, curves | **KEEP** drill-down | Monolith; dual chart libs |
| `/ukesanalyse` | Running economy charts | **REPLACE** fetch; **REUSE** charts | Loads activities since 2010 |
| `/hrv` | HRV trend | **MERGE** → Recovery history | Dual endpoint lore |
| `/sovn` | Sleep | **MERGE** → Recovery | |
| `/stress` | Stress | **MERGE** → Recovery | Unused health hook |
| `/body-battery` | Body Battery | **MERGE** → Recovery | Dual APIs |
| `/vo2max` | VO2 history | **MERGE** → Utvikling/Performance | Orphan `VO2MaxChart` |
| `/training-stress` | CTL/ATL/TSB | **MERGE** → Load history | Only Chart.js page |
| `/training-status` | Period overview cards | **MERGE** → Utvikling landing | |
| `/daglig-readiness` | Daily ops | **KEEP** outside Analyse | Not longitudinal analysis |

---

## Chart components

| Component | Lib | Classification |
|-----------|-----|----------------|
| `PlotlyChart` | Plotly | **REUSE** (scatter / FIT) |
| `ActivityChart` | Recharts | **REUSE** Historikk volume |
| `MonthlyComparisonChart` | Recharts | **REUSE** → YearComparison |
| `HrvChart` / `SleepScoreChart` / `BodyBatteryChart` | Recharts | **REUSE** RecoveryHistory |
| Running-economy chart family | Recharts | **REUSE** |
| `VO2MaxChart` | Recharts | **DEPRECATE_LATER** (orphan) or wire |
| Inline Chart.js in training-stress | Chart.js | **REPLACE** with Recharts/Plotly |
| Page-inline Recharts copies | — | **DEPRECATE_LATER** |

**Canonical new wrappers (planned):** `MetricTrendChart`, `DevelopmentTimeline`, `LagProfile`, `RelationshipMatrix`.

---

## Backend capability → workspace mapping

| Capability | Module | HTTP today | Workspace use |
|------------|--------|------------|---------------|
| Longitudinal trends | `TrendAnalysisService` | **None** (MCP only) | **Utvikling** via `GET /api/analysis/development` |
| Metric timeseries | `McpDerivedMetricsService` / PPAP | Fragmented | `GET /api/analysis/timeseries` |
| Training→response + lag | `TrainingResponseService` | **None** | **Sammenhenger** via `/relationships` |
| Factor scatter | `factor_relationships.py` | `/api/analysis/factor-relationships` | Advanced scatter |
| Monthly/weekly summaries | `analysis.py` + Summary models | Existing | **Historikk** / period compare |
| Monthly YoY | `/monthly-comparison` | Yes | YearComparison |
| CTL/ATL/TSB | `training_stress` + PPAP | `/api/training-stress/*` | LoadHistory |
| HRV/sleep/BB | `/api/analysis/*` + `/api/health/*` | Yes | RecoveryHistory |
| VO2 / CS | analysis + analytics routers | Yes | PerformanceHistory |
| Session quality / comparable / race outcome | coaching services | **None** HTTP | Later sprints (wrap) |
| Concept drift / prospective | coaching services | **None** HTTP | Evidence semantics later |
| Freshness / confidence | `freshness_policy`, `metric_evidence` | Embedded | Badges on cards |

---

## New summary endpoints (Sprint 1)

| Endpoint | Source | Gap |
|----------|--------|-----|
| `GET /api/analysis/development` | `TrendAnalysisService.analyze_all` | Thin wrap + domain cards |
| `GET /api/analysis/timeseries` | `TrendAnalysisService` series | Public series accessor |
| `GET /api/analysis/relationships` | `TrainingResponseService` | Thin wrap + presentation fields |
| `GET /api/analysis/history` | MonthlySummary (+ weekly) | Compose existing queries |
| `GET /api/analysis/period-comparison` | Trends A vs B windows | Light aggregation |
| `GET /api/analysis/week/{date}` | WeeklySummary + activity stubs | Compose |
| `GET /api/analysis/highlights` | Change points + overview | Selection logic only |

No duplicate analytics math in the frontend.

---

## Information architecture

```
/analyse?tab=utvikling&period=90d&sport=running&session=all
├── Global filters (URL-persisted)
├── UTVIKLING     — development summary + timeline + period compare
├── SAMMENHENGER  — relationship cards + lag + link to advanced scatter
└── HISTORIKK     — year → month → week hierarchy
```

Specialist pages remain linked as drill-downs.

---

## Pain points to eliminate

1. Client-side load of multi-year raw activities for charts  
2. Navbar metric gallery (14 hard-reload links) as primary IA  
3. Raw Pearson as default relationship UX  
4. Three chart libraries for the same job  
5. Dead-end graphs with no session drill-down  
6. Causal language risk — enforce observational wording  

---

## Sprint status (this PR)

| Sprint | Scope | Status |
|--------|-------|--------|
| 1 | Audit, `/analyse` shell, filters, URL state, API/types | **In PR** |
| 2 | Utvikling summary + timeline + period compare shells | **In PR** |
| 3–6 | Full lag matrix, week explorer, presets, etc. | Later |

---

## Definition of done (workspace)

User can answer from `/analyse` without hopping metric pages:

1. Am I improving?  
2. What is changing?  
3. How do periods compare?  
4. What associations appear (with lag + evidence)?  
5. Can I open Historikk and drill toward sessions?  
6. Is evidence / sample / freshness visible but quiet?
