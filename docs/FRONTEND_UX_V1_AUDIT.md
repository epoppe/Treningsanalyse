# Frontend UX V1 Audit

**Branch context:** `main` after coaching V9 (`6b2cf42`). Backend coaching is **feature-frozen**.  
**Objective:** Turn the frontend from a metric gallery into a coherent training decision cockpit.  
**Constraint:** Do not change coaching algorithms; frontend consumes summary APIs only.

Classification: **KEEP** · **MERGE** · **REDESIGN** · **MOVE_TO_DETAILS** · **REMOVE_LATER**

---

## Executive summary

Today the App Router is a **flat metric gallery** (14 nav links) with hard `window.location.href` reloads. Home (`/`) is an activity explorer with filters — not a coaching decision surface. Backend coaching (AthleteState, NextBestWorkout, DecisionExplanation, weekly plan, health/integrity, prospective evidence) has **zero frontend surface** beyond readiness-adjacent pages.

V1 introduces task-first IA (Today / Plan / Progress / Activities / Insights / System), a Today dashboard, design tokens (Tailwind + shadcn for new UI), soft navigation, and coaching summary endpoints.

---

## Current routes

| Route | Classification | Notes |
|-------|----------------|-------|
| `/` | **REDESIGN** → Today dashboard | Currently activity list + filters |
| `/activities` | **KEEP** (new) | Host relocated activity explorer |
| `/activities/[id]` | **REDESIGN** (later sprint) | Charts before interpretation today |
| `/daglig-readiness` | **MOVE_TO_DETAILS** | Link from Today / Insights |
| `/training-status` | **MERGE** into Progress | |
| `/training-stress` | **MERGE** into Progress (Load) | |
| `/vo2max` | **MOVE_TO_DETAILS** from Progress | |
| `/analytics` | **MOVE_TO_DETAILS** from Progress | |
| `/ukesanalyse` | **MOVE_TO_DETAILS** (efficiency) | |
| `/statistikk` | **MOVE_TO_DETAILS** | |
| `/hrv`, `/sovn`, `/stress`, `/body-battery` | **MOVE_TO_DETAILS** from Insights | |
| `/sammenhenger` | **MOVE_TO_DETAILS** from Insights | |
| `/synkronisering` | **MOVE_TO_DETAILS** from System | |
| `/readiness-chat` | **KEEP** (API route) | |

---

## Components

| Component | Classification |
|-----------|----------------|
| `Navbar.tsx` | **REDESIGN** → AppShell (sidebar + mobile bottom nav), soft Links |
| `ActivityList` / `ActivityCard` / virtualization | **KEEP** on Activities |
| `ActivityChart`, economy charts | **KEEP** / standardize later |
| Chart wrappers (Hrv, Sleep, VO2…) | **MERGE** toward shared wrappers (Sprint 7) |
| `TrainingReadiness.tsx` | **REMOVE_LATER** (orphaned duplicate of page) |
| `ActivityFilters.tsx` | **REMOVE_LATER** (orphaned) |
| `DataSyncPanel.tsx` | **REMOVE_LATER** (superseded by sync page) |
| `SkeletonLoader` | **MERGE** into shared Empty/Error/Skeleton |
| `ui/button|card|badge` | **KEEP** — primary for new UI |

---

## Design system decision

See `docs/FRONTEND_DESIGN_SYSTEM.md`.

**Primary for new work:** Tailwind + existing shadcn (`ui/*`) + CSS semantic tokens.  
**Legacy:** styled-components pages remain as drill-downs until migrated.  
**Do not** rewrite all old pages in V1.

---

## Backend → frontend IA mapping

| User task | Backend capability | Frontend surface |
|-----------|-------------------|------------------|
| How am I? | AthleteState, readiness, HRV/sleep | Today → AthleteStateCard |
| What to do? | NextBestWorkout + prescription | Today → NextWorkoutCard |
| Why? | DecisionExplanation reason codes | Today → WhyThisWorkout |
| This week | Weekly plan sessions | Today / Plan → WeeklyTrainingPlan |
| Block | Mesocycle | Plan → TrainingBlockView |
| Goal | Goal context / race capability | Plan → GoalCard |
| Progress | Trends, LT2, VO2, CTL/ATL/TSB | Progress page + drill-downs |
| Insights | HRV, sleep, drift, prospective | Insights page |
| System | Health, integrity, sync | System page (quiet on Today) |

---

## Gaps closed in V1 (this PR)

1. Coaching summary REST API (`/api/coaching/*`) wrapping orchestrator — no algorithm change  
2. Task-first navigation + soft routing  
3. Today dashboard (state, next workout, why, week, warnings)  
4. Plan / Progress / Insights / System shell pages  
5. Activities moved off home  
6. Typed coaching contracts + React Query hooks  
7. Design tokens + status/session colors  
8. Standard Skeleton / Empty / Error / Stale states  
9. Frontend behavior tests for Today states  

---

## Explicit DEFER

- Full chart wrapper consolidation across all legacy pages  
- Dark mode  
- OpenAPI type generation pipeline  
- Activity detail full reinterpretation (Sprint 5 depth)  
- Deleting unused routes immediately  
- LLM-generated daily summary (use reason codes only)
