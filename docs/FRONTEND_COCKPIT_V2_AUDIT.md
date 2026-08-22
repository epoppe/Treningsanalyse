# Frontend Cockpit V2 — Audit

**Repo:** epoppe/Treningsanalyse  
**Base:** `main` @ `3fbe3c8` (merged PR #50 — `/analyse` analytics workspace)  
**Dato:** 2026-08-22  
**Mål:** Kartlegge dagens frontend og definere veien fra fragmentert metric-navigasjon til en **personlig treningscockpit**.

Coaching-motoren er feature-frozen (V9). Denne fasen skal **ikke** legge til ny prediktiv modell eller duplisere coaching-logikk i React. Backend eksponeres via tynne HTTP-wrappers; frontend viser, forklarer og navigerer.

---

## Klassifiseringslegende

| Tag | Betydning |
|-----|-----------|
| **PRIMARY** | Hovedflate i ny informasjonsarkitektur (I dag / Plan / Analyse / Aktiviteter) |
| **DRILL_DOWN** | Beholdes som spesialist- eller dypdykk-rute; tilgjengelig fra cockpit, ikke primærnav |
| **MERGE** | Funksjonalitet flyttes inn i PRIMARY eller DRILL_DOWN; URL kan beholdes midlertidig |
| **LEGACY** | Eksisterende implementasjon som bryter cockpit-mønster (datahenting, IA, styling) |
| **DEPRECATE_LATER** | Fjernes som frittstående primærside når erstatning er komplett; URL beholdes inntil da |

---

## Executive summary

| Område | Status i dag | Cockpit-gap |
|--------|--------------|-------------|
| Informasjonsarkitektur | 14 metric-lenker i horisontal navbar med tvungen full reload | Ingen «I dag → Plan → Analyse → Aktiviteter»-flyt |
| `/` | Aktivitetsutforsker (50 + opptil 5000 aktiviteter i Redux) | Skal bli Today-cockpit med én summary-API |
| Coaching i UI | Ikke eksponert via HTTP; kun MCP + eldre readiness-endepunkter | Krever `GET /api/dashboard/today`, plan-endepunkter, WhatChanged |
| `/analyse` | Sterk V1 (React Query, URL-state, Tailwind) | Mangler multi-horizon, ukeutforsker, spørsmåls-first relationships m.m. |
| Datahenting | Redux + useEffect side om side med React Query | Dobbel cache for aktiviteter; sync invaliderer ikke analyse/today |
| Design | Tailwind i `/analyse`, styled-components ellers | Tre chart-bibliotek; ingen felles semantiske tokens |

**Anbefalt første leveranse (Sprint A):** ny navigasjon, flytt aktivitetsutforsker til `/aktiviteter`, `GET /api/dashboard/today`, Today-side, `NextWorkoutCard`, `WhyThisWorkout`.

---

## Dagens ruter — side-for-side

### `/` — Aktivitetsutforsker (Home)

| | |
|---|---|
| **Klassifisering (i dag)** | **LEGACY** (feil rolle som root) |
| **Klassifisering (mål)** | **PRIMARY** → Today cockpit |
| **Tech** | Redux (`activitiesSlice`), styled-components, `useSyncListener` |
| **Data** | Progressive load: 50 aktiviteter → 5000 i bakgrunnen; visibility/focus trigger re-fetch |
| **Komponenter** | `ActivityList`, `ActivityChart`, `ActivityViewControls`, typefiltre |
| **Sync** | `refreshActivitiesAfterSync` — kun Redux aktiviteter |

**Gap mot cockpit:**

- Svarer ikke på «Hvordan er jeg i dag?», «Hva skal jeg trene?», «Hvorfor?», «Hva endret seg?», «Hva ser uken ut?»
- Laster full aktivitetshistorie — antipattern for Today
- `window.location.reload()` på feil/retry (ikke Next.js navigasjon)

**Mål:** Erstatt innhold; flytt eksisterende explorer til `/aktiviteter` eller `/activities`.

---

### `/analyse` — Analytics workspace

| | |
|---|---|
| **Klassifisering** | **PRIMARY** (Analyse) |
| **Tech** | Tailwind, React Query, URL-persistert state (`AnalysisShell`) |
| **Faner** | Utvikling · Sammenhenger · Historikk |
| **Backend** | `GET /api/analysis/*` via `analysis/analysisApi.ts` |

**Implementert (sterk grunn):**

| Komponent | Backend | Status |
|-----------|---------|--------|
| `TrendSummaryCard` + domene-kort | `/development` | ✅ Grunnleggende utviklingssammendrag |
| `DevelopmentTimeline` | `/timeseries` | ✅ Tidsserie (en periode om gangen) |
| `PeriodComparison` | `/period-comparison` | ✅ Shell |
| `RelationshipCard` + matrix | `/relationships`, `/relationship-matrix` | ✅ Observasjonell UX med disclaimer |
| `TrainingResponsePanel` | `/training-response` | ✅ Outcome-fokus |
| `HistoryTimeline` | `/history` | ⚠️ År → måned (ikke uke/session) |
| `BestPeriodBacktracePanel` | `/best-period-backtrace` | ⚠️ Grunnpanel, ikke full explorer |
| `DurationCurvePanel`, `IntensityDistributionPanel` | `/duration-curve-history`, `/intensity-distribution` | ✅ Delvis performance/load |

**Gap mot cockpit V2:**

- Ingen 28d / 90d / 365d side om side (multi-horizon)
- Ingen tidslinje med zoom, hendelsesmarkører, kryssfiltrering
- Ingen `WeekExplorer` (backend har `/week/{week_date}` — ubrukt i UI)
- Relationship detail, lag-visualisering og spørsmåls-first IA mangler
- Historikk stopper på måned — ikke uke/session
- Ingen «WHAT CHANGED / MAY BE RELATED / EVIDENCE»-blokker per view
- Drill-down-lenker peker fortsatt til legacy (`/vo2max`, `/training-stress`, `/analytics`)

---

### `/statistikk`

| | |
|---|---|
| **Klassifisering** | **MERGE** → `/analyse` Historikk + Year-over-year · **DEPRECATE_LATER** som primærside |
| **Tech** | Redux `fetchAllActivities({ count: 1000 })`, styled-components |
| **Innhold** | Volumgrafer, månedlig sammenligning, summary-tabeller, YoY via `/monthly-comparison` |

**Problem:** Client-side aggregering av opptil 1000 råaktiviteter. Overlapper `/analyse/history` og planlagt YoY-view.

---

### `/sammenhenger`

| | |
|---|---|
| **Klassifisering** | **DRILL_DOWN** (avansert manuell X/Y) · **MERGE** konsept inn i `/analyse` Sammenhenger · **DEPRECATE_LATER** som default relationship UX |
| **Tech** | `useEffect` + `analysisApi.getFactorRelationships`, Plotly scatter |
| **Backend** | `/api/analysis/factor-relationships` (Pearson) |

**Problem:** Raw korrelasjon som primær opplevelse; erstattes av spørsmålskort + evidence i `/analyse`. Behold som power-user scatter.

---

### `/analytics` — Løpeanalyse

| | |
|---|---|
| **Klassifisering** | **DRILL_DOWN** (spesialist) · delvis **MERGE** inn i `/analyse` Utvikling |
| **Tech** | styled-components, Recharts + Plotly, direkte `analyticsApi` |
| **Innhold** | EF-trend, decoupling, critical speed, fatigue resistance, duration curve, year comparison |

**Problem:** Monolitt (~1000+ linjer); dupliserer duration curve mot `/analyse`. `/analytics/coaching` backend finnes men brukes ikke i denne siden.

---

### `/ukesanalyse` — Løpsøkonomi

| | |
|---|---|
| **Klassifisering** | **DRILL_DOWN** · **MERGE** økonomi-grafer inn i aktivitets-/analyse-dypdykk |
| **Tech** | Redux `fetchActivitiesByDateRange` fra 2010, styled-components |
| **Komponenter** | `RunningEconomyChart`, `CadenceChart`, `StrideLengthChart`, `PowerPerHeartRateChart` |

**Problem:** Laster multi-år råaktiviteter client-side.

---

### `/hrv`

| | |
|---|---|
| **Klassifisering** | **DRILL_DOWN** under MER/DATA · **MERGE** inn i Recovery history i `/analyse` |
| **Tech** | Blandet: `useHrvData` (React Query) + direkte `api`/`BASE_URL`-kall, Recharts |
| **Backend** | `/api/health/hrv/range` + `/api/analysis/hrv/*` (dual lore) |

---

### `/sovn`, `/stress`, `/body-battery`

| | |
|---|---|
| **Klassifisering** | **DRILL_DOWN** under MER/DATA · **MERGE** → Recovery history |
| **Tech** | styled-components, Recharts; `useStressData` finnes men `/stress` bruker ikke hook konsekvent |
| **Backend** | `/api/health/*` |

---

### `/vo2max`

| | |
|---|---|
| **Klassifisering** | **DRILL_DOWN** under MER/DATA · **MERGE** → `/analyse` Utvikling / Performance history |
| **Tech** | `useEffect` + `analysisApi.getVo2MaxHistory`, Recharts |
| **Note** | `VO2MaxChart`-komponent er orphan (ubrukt) |

---

### `/training-stress`

| | |
|---|---|
| **Klassifisering** | **DRILL_DOWN** under MER/DATA · **MERGE** → Load history i `/analyse` |
| **Tech** | **Chart.js** (eneste side), direkte fetch |
| **Backend** | `/api/training-stress/*` |

---

### `/training-status`

| | |
|---|---|
| **Klassifisering** | **MERGE** → Today athlete state + `/analyse` Utvikling · **DEPRECATE_LATER** |
| **Tech** | `analysisApi.getTrainingOverview`, styled-components kort-grid |
| **Overlap** | Delvis duplikat av `/analyse/development` domene-kort |

---

### `/daglig-readiness`

| | |
|---|---|
| **Klassifisering** | **MERGE** → Today «Hvordan er jeg?» + morgenoppdatering · **DRILL_DOWN** for chat |
| **Tech** | `useEffect`, `activitiesApi.getTrainingReadiness`, Tailwind-layout |
| **Backend** | `/api/training-readiness` — **legacy readiness**, ikke coaching orchestrator |
| **Risiko** | Kan gi annen anbefaling enn coaching engine; må ikke være primær beslutningskilde |

---

### `/synkronisering`

| | |
|---|---|
| **Klassifisering** | **DRILL_DOWN** under MER/DATA (Sync + system) |
| **Tech** | styled-components, `syncApi`, dispatcher `syncCompleted` CustomEvent |
| **Sync-flyt i dag** | `syncCompleted` → `useSyncListener` → Redux aktiviteter refresh **kun** på sider som lytter |

**Gap:** Ingen invalidation av React Query (`analysis`, `today`, `plan`); ingen WhatChanged; ingen toast for anbefalingsendring.

---

### `/activities/[id]` — Aktivitetsdetalj

| | |
|---|---|
| **Klassifisering** | **PRIMARY** (Sessions drill-down endpoint) |
| **Tech** | Blandet Tremor + fetch; `ActivityAnalytics` med `useEffect` (ikke React Query) |
| **Innhold** | Negative split, decoupling, FIT-detaljgrafer |
| **Backend tilgjengelig (MCP, ikke HTTP)** | `session_quality`, `comparable_sessions` |

**Gap:** Chart-first, ikke interpretation-first. Mangler session quality, comparable sessions, plan/recovery-effekt, post-sync «NEW SESSION ANALYSED».

---

### `/plan` — Finnes ikke

| | |
|---|---|
| **Klassifisering (mål)** | **PRIMARY** (Plan) |
| **Backend** | `WeeklyPlanService`, `PlanAdaptationService`, `plan_stability` — via `CoachingOrchestrator.training_decision_brief`, **ingen dedikert HTTP-rute** |

---

## Navbar

**Fil:** `frontend/src/components/Navbar.tsx`

| Aspekt | Status |
|--------|--------|
| Klassifisering | **LEGACY** |
| Primær IA | Metric-first: 14 horisontale lenker |
| Navigasjon | `window.location.href` på alle lenker + `prefetch={false}` — **tvinger full reload** |
| Mobil | Horisontal scroll; ingen bottom nav |
| Plan / I dag | Finnes ikke |

**Mål (P0):**

```
PRIMARY:     I dag | Plan | Analyse | Aktiviteter
SECONDARY:   Mer / Data  →  HRV, Søvn, Body Battery, VO2max, Training stress,
                             Statistikk, Synkronisering, System health
```

Desktop: kompakt sidebar eller ren top-nav. Mobil: bottom nav (I dag · Plan · Analyse · Aktiviteter · Mer).

---

## React Query — bruk og gap

### Etablert mønster (bra)

| Hook-fil | Query keys | Brukes av |
|----------|------------|-----------|
| `useAnalysisWorkspace.ts` | `["analysis", ...]` (11 hooks) | `/analyse` |
| `useHealthData.ts` | `["health", ...]` | Delvis `/hrv` |
| `useAnalysis.ts` | `["analysis", activityId, ...]` | **Lite brukt** — `ActivityAnalytics` bruker `useEffect` |
| `useActivities.ts` | `["activities", ...]` | **Ikke brukt** av `/`, `/statistikk`, `/ukesanalyse` |

### Legacy / parallell cache

| Kilde | Mekanisme | Sider |
|-------|-----------|-------|
| Redux `activitiesSlice` | `fetchActivities`, `fetchMoreActivities`, `fetchAllActivities` | `/`, `/statistikk`, `/ukesanalyse`, sync |
| Direkte `useEffect` + axios/fetch | Ingen cache-deling | `/sammenhenger`, `/analytics`, `/vo2max`, `/training-status`, `/daglig-readiness`, m.fl. |
| `window.location.reload` | Full app reset | `/` feilstate |

### Migrasjonsplan (P0 — ikke full rewrite)

1. **Today / Plan:** nye hooks `useTodayDashboard`, `useWeeklyPlan`, `useWhatChanged` — React Query only
2. **Aktiviteter:** flytt `/` explorer til `/aktiviteter`; bruk `useInfiniteActivities` + server-side paginering
3. **Aktivitetsdetalj:** migrer `ActivityAnalytics` til `useAnalysis` hooks
4. **Redux:** behold midlertidig for sync-merge av aktivitetsliste; deprecate når aktivitetsrute er migrert
5. **Sync:** sentral `invalidateQueries` i `syncRefresh.ts` for `today`, `plan`, `analysis`, `activities`

---

## Frontend API-wrappers

### To parallelle lag

| Modul | Transport | Scope |
|-------|-----------|-------|
| `utils/api.ts` | axios (`/api` proxy) | Aktiviteter, health, legacy analysis, analytics, sync — **~690 linjer** |
| `analysis/analysisApi.ts` | `fetch` | Kun analysis workspace — **~75 linjer** |

**Problem:** Inkonsistent base URL (`useActivities` hardkoder `localhost:8000`, workspace bruker relative `/api`).

### Backend coaching — tilgjengelighet

| Capability | Service / MCP | HTTP i dag | Cockpit-behov |
|------------|---------------|------------|---------------|
| Full decision brief | `CoachingOrchestrator.training_decision_brief` | ❌ MCP only | `GET /api/dashboard/today` |
| Athlete state | `AthleteStateService` | ❌ | Inkluderes i today payload |
| Workout prescription | `NextBestWorkoutService` | ❌ | `NextWorkoutCard` |
| Decision explanation | `DecisionExplanationService` | ❌ | `WhyThisWorkout` |
| Weekly plan | `WeeklyPlanService` | ❌ | `GET /api/plan` eller del av today |
| Plan adaptation | `PlanAdaptationService` | ❌ | Plan change UX |
| Recommendation ledger | `RecommendationLedgerService` | ❌ | WhatChanged, history |
| Session quality | `SessionQualityService` | ❌ MCP | Post-sync summary |
| Comparable sessions | `ComparableSessionService` | ❌ MCP | Activity detail |
| WhatChanged / delta | — | ❌ **Finnes ikke** | Ny wrapper rundt ledger + snapshot diff |

**Eksisterende HTTP som ikke skal duplisere coaching:**

- `/api/training-readiness` — Garmin readiness, ikke orchestrator
- `/api/analytics/coaching` — analyse snapshot (`CoachingAnalysisService`), ikke live anbefaling

---

## Analyse-komponenter (`frontend/src/components/analysis/`)

| Komponent | Klassifisering | Cockpit V2 |
|-----------|----------------|------------|
| `AnalysisShell.tsx` | **PRIMARY** | Gjenbruk filter/URL-mønster; utvid evt. til delt layout |
| `AnalysisPresets.tsx` | **PRIMARY** | Utvid til spørsmåls-first presets |
| `TrendSummaryCard.tsx` | **PRIMARY** | Utvid til multi-horizon (28/90/365) |
| `DevelopmentTimeline.tsx` | **PRIMARY** | Evolver til sentral explorer m/ brush, events |
| `PeriodComparison.tsx` | **PRIMARY** | Koble til period explanation panel |
| `RelationshipCard.tsx` | **PRIMARY** | → detail view + lag chart |
| `RelationshipMatrixView.tsx` | **PRIMARY** | Symboler (↑↓—?⊘), ikke raw r |
| `TrainingResponsePanel.tsx` | **PRIMARY** | Spørsmåls-first ranking |
| `HistoryTimeline.tsx` | **PRIMARY** | Utvid hierarki: år → måned → uke → session |
| `BestPeriodBacktracePanel.tsx` | **PRIMARY** | Utvid til full Best Period Explorer |
| `DurationCurvePanel.tsx` | **DRILL_DOWN** | Behold i Utvikling |
| `MetricPicker.tsx` | **PRIMARY** | Gjenbruk |
| `ui.tsx` (`EvidenceBadge`, skeletons) | **PRIMARY** | **Semantiske tokens** — grunnlag for hele cockpit |

### Planlagte nye komponenter (fra spec)

| Komponent | Prioritet | Avhenger av |
|-----------|-----------|-------------|
| `NextWorkoutCard` | P0 | `workout_prescription` i today API |
| `WhyThisWorkout` | P0 | `decision_explanation` |
| `UpdateDelta` / `WhatChanged` | P0 | Ny backend delta payload |
| `WeekExplorer` | P1 | `/api/analysis/week/{date}` (finnes) |
| `InsightFeed` | P1 | `/api/analysis/highlights` (finnes delvis) |
| Chart primitives (`TimeSeriesChart`, `LagChart`, …) | P0–P1 | Design system |

---

## Legacy chart-komponenter

| Komponent | Lib | Klassifisering |
|-----------|-----|----------------|
| `PlotlyChart` | Plotly | **DRILL_DOWN** scatter |
| `ActivityChart`, `MonthlyComparisonChart`, `HrvChart`, … | Recharts | **MERGE** / standardiser |
| Inline Chart.js (`/training-stress`) | Chart.js | **DEPRECATE_LATER** → felles Recharts/Plotly wrapper |
| Tremor (`ActivityAnalytics`, activity detail) | Tremor | **LEGACY** i detalj — vurder Tailwind primitives |
| Inline Recharts i `/analytics`, `/vo2max` | Recharts | **MERGE** eller **DEPRECATE_LATER** |

**Chart-bibliotek i bruk:** Recharts (dominant), Chart.js (1 side), Plotly (scatter), Tremor (detalj).

---

## Sync → anbefaling refresh (nå vs mål)

### I dag

```
Garmin sync complete (/synkronisering)
  → window.dispatchEvent('syncCompleted')
  → useSyncListener (kun på sider med listener)
  → refreshActivitiesAfterSync (Redux)
  → ingen React Query invalidation
  → ingen WhatChanged
  → ingen coaching refresh
  → ingen bruker-feedback om anbefaling
```

### Mål (P0)

```
Sync complete
  → invalidateQueries: today, plan, analysis.*, activities, whatChanged
  → refetch GET /api/dashboard/today
  → GET /api/dashboard/what-changed (ny)
  → toast: «Ny treningsanbefaling» | «Data oppdatert — anbefaling uendret»
  → ved ny aktivitet: post-sync session summary
```

---

## Visuelt designsystem

| Område | I dag | Mål |
|--------|-------|-----|
| `/analyse` | Tailwind + `EvidenceBadge` | **Kanonisk** for nytt arbeid |
| Legacy sider | styled-components, ad hoc farger (`#3498db`, `#2c3e50`) | Ikke omskriv alt; nye flater bruker tokens |
| Session-typer | Ikke konsistent | `easy`, `long`, `threshold`, `vo2`, `race`, `strength`, `rest` |
| Evidence | Delvis i `/analyse` | `strong`, `supported`, `emerging`, `insufficient` |
| Freshness | Backend finnes; lite UI | `fresh`, `aging`, `stale`, `missing` — stille, sekundær |

---

## Backend-endepunkter — kart for cockpit

### Finnes og brukes

| Endepunkt | Frontend |
|-----------|----------|
| `GET /api/analysis/development` | `/analyse` Utvikling |
| `GET /api/analysis/timeseries` | `DevelopmentTimeline` |
| `GET /api/analysis/relationships` | Sammenhenger |
| `GET /api/analysis/history` | Historikk |
| `GET /api/analysis/week/{week_date}` | **Ubrukt** |
| `GET /api/analysis/highlights` | **Ubrukt** |
| `GET /api/activities/*` | Redux bulk load |

### Må opprettes (tynne wrappers)

| Endepunkt | Kilde | Payload (foreslått) |
|-----------|-------|---------------------|
| `GET /api/dashboard/today` | `CoachingOrchestrator.training_decision_brief` | `athlete_state`, `recommendation`, `decision_explanation`, `weekly_plan`, `key_trends`, `freshness`, `warnings`, `system_status` |
| `GET /api/dashboard/what-changed` | Ledger diff + context snapshot | `material_changes[]`, `recommendation_changed`, reason code deltas |
| `GET /api/plan` | `WeeklyPlanService` + adaptation history | uke + mesocyklus |
| `GET /api/dashboard/post-sync-summary` | `SessionQualityService` + comparable + plan effect | post-sync UX |
| `GET /api/coaching/recommendation-history` | `RecommendationLedgerService` | historikk-view |

**Regel:** Ingen ny coaching-matematikk i frontend eller nye prediktive modeller.

---

## Informasjonsarkitektur — målbilde

```
/                          PRIMARY   I DAG (Today cockpit)
/plan                      PRIMARY   Plan (uke + mesocyklus)
/analyse                     PRIMARY   Analyse (Utvikling | Sammenhenger | Historikk)
/aktiviteter                 PRIMARY   Aktivitetsliste (paginert)
/activities/[id]             PRIMARY   Session drill-down

MER / DATA (secondary nav):
  /hrv, /sovn, /body-battery, /vo2max, /training-stress
  /statistikk (inntil merged), /synkronisering
  /sammenhenger (avansert scatter)
  /analytics, /ukesanalyse (spesialist)
  /daglig-readiness (chat / legacy readiness)
  /training-status (inntil merged)
```

Brukerflyt:

```
I DAG → HVA ENDRET SEG → ANBEFALING → PLAN → UTVIKLING → HISTORISK BEVIS → ENKELTØKTER
```

---

## Ytelses-antipatterns (P0)

| Antipattern | Hvor | Fix |
|-------------|------|-----|
| 50 + 5000 aktiviteter på load | `/` | Flytt til `/aktiviteter`; paginering + virtualisering |
| 1000 aktiviteter for statistikk | `/statistikk` | Backend aggregate (`/analysis/history`, YoY API) |
| Aktiviteter siden 2010 | `/ukesanalyse` | Datoperiode-begrenset API eller dedikert endpoint |
| Full reload navigasjon | `Navbar` | Next.js `Link` + prefetch |
| Today loader ikke historie | — | Én summary-endpoint |
| 10–15 parallelle analysis calls | `/analyse` | Allerede staggered; vurder summary endpoints |

---

## Testdekning

| Område | Status |
|--------|--------|
| `/analyse` kort | `analysisCards.test.tsx` (58 linjer) |
| Today / Plan / Sync / Nav | **Ingen** |
| Spec P1 liste (18 scenarier) | **Ikke startet** |

---

## Sprint-kartlegging (implementeringsrekkefølge)

| Sprint | Scope | Audit-status |
|--------|-------|--------------|
| **A** — Nav + cockpit foundation | Audit ✅, nav redesign, flytt explorer, today API, Today UI, NextWorkout, Why | **Denne auditen** |
| **B** — Update intelligence | WhatChanged API, sync invalidation, toast, post-sync summary, rec history | Backend gap størst |
| **C** — Plan | `/plan`, uke/mesocyklus, plan changes, plan vs actual | Ingen HTTP plan i dag |
| **D** — Analyse depth | Multi-horizon, timeline cross-filter, period explain, relationship detail, lag, WeekExplorer | `/analyse` grunn ok |
| **E** — Historical | YoY, performance/recovery/structure history, annotations | Delvis backend |
| **F** — Integration | Insight feed, historical support in Why, comparable sessions, saved analyses | MCP→HTTP wraps |
| **G** — Polish | Mobil, a11y, chart standardization, query audit, fjern reloads | Navbar = quick win |

---

## Definition of done — sporbarhet

| Brukerspørsmål | Primary surface | Dagens status |
|----------------|-----------------|---------------|
| Hvordan er jeg? | `/` Today | ❌ Kun aktivitetsliste |
| Hva skal jeg trene? | `/` + `NextWorkoutCard` | ❌ |
| Hvorfor? | `WhyThisWorkout` | ❌ |
| Hva endret seg etter sync? | `WhatChanged` | ❌ |
| Plan denne uken? | `/plan` | ❌ Route finnes ikke |
| Hvorfor endret planen seg? | `/plan` | ❌ |
| Utvikling 28/90/365? | `/analyse` | ⚠️ En periode om gangen |
| Treningsmønstre + lag? | `/analyse` Sammenhenger | ⚠️ Kort, ikke detail/lag UX |
| Beste perioder / YoY / uke? | `/analyse` Historikk | ⚠️ Delvis |
| Session kvalitet / sammenligning? | `/activities/[id]` | ❌ Chart-first |
| Påvirket recovery / neste anbefaling? | Post-sync flow | ❌ |

---

## Anbefalte umiddelbare handlinger

1. **`docs/FRONTEND_COCKPIT_V2_AUDIT.md`** (dette dokumentet) — godkjent som Sprint A-grunnlag
2. **Backend:** `GET /api/dashboard/today` som tynn wrapper over `training_decision_brief(detail="standard")`
3. **Backend:** `GET /api/dashboard/what-changed` med ledger-basert diff
4. **Frontend:** Ny `AppShell` med primary/secondary nav; fjern `window.location.href`
5. **Frontend:** Flytt `page.tsx` → `/aktiviteter/page.tsx`; ny Today på `/`
6. **Frontend:** `useTodayDashboard` + `NextWorkoutCard` + `WhyThisWorkout` (Tailwind primitives fra `analysis/ui.tsx`)
7. **Sync:** Utvid `syncRefresh.ts` med React Query `queryClient.invalidateQueries`

---

## Referanser

- Forrige audit: `docs/FRONTEND_ANALYTICS_UX_AUDIT.md` (V1 — `/analyse` workspace)
- Coaching freeze: `docs/COACHING_V9_OPERATIONAL_AUDIT.md`
- Backend orchestrator: `backend/app/services/coaching_orchestrator.py`
- Analysis workspace API: `backend/app/routers/analysis_workspace.py`
- Frontend workspace: `frontend/src/app/analyse/`
