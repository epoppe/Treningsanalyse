# Coaching V8 Audit — Simplify → Verify → Monitor → Improve

**Branch context:** post Adaptive Coaching Engine v7 on `main` (`ef0d8fc`).  
**Objective:** reduce overlapping rules, strengthen evidence, stabilize decisions, improve observability — **not** add another predictive model layer.

Classification used throughout:

| Tag | Meaning |
|-----|---------|
| **P0** | Correctness / safety / trust — do now |
| **P1** | High-value improvement — do next |
| **P2** | Useful but optional |
| **DEFER** | Explicitly not in this iteration |
| **REMOVE/CONSOLIDATE** | Prefer delete/merge over new abstraction |

---

## Executive summary

The live decision spine is sound:

```
Garmin/data → PPAP/state → calibration → NextBestWorkout (+ ranker)
→ prescription → weekly plan → ledger → execution → outcome → ValidationRun/shadow
```

The main risk is **conceptual sprawl**: duplicate Banister/load math, dual readiness semantics, recursive `recommend()` inside health checks, hardcoded cliffs that ignore calibrated params, free-text traces without stable reason codes, and periodization services that are not on the live path but inflate the mental model.

**v8 stance:** KEEP the spine; MERGE duplicates; DEPRECATE wrappers that re-enter the engine; ADD explainability, health/integrity, evidence policy, and golden/consistency tests — then **stop building models** until prospective evidence accumulates.

---

## 1. Architecture complexity audit — P0

### Live decision path (canonical)

```
Garmin sync / DB
  → PpapMetricsService (CTL/ATL/TSB, HRV/RHR, readiness.total_score, CS, …)
  → AthleteStateService.build_state
  → AthleteCalibrationService (params) + AdaptiveThresholdService (LT1/LT2)
  → NextBestWorkoutService.recommend
        → rule cascade + decision_trace
        → WorkoutCandidateRanker.rank (optional override)
        → WorkoutPrescriptionService + IntensityPrescriptionService
  → WeeklyPlanService → WeeklyPlanOptimizer → TrainingPlanStore
  → PlanAdaptationService
  → RecommendationLedgerService (immutable snapshot)
  → ShadowRecommendationService (optional; never mutates plan)
  → RecommendationExecutionService → AthleteFeedbackService
  → RecommendationUtilityEvaluator / ShadowOutcomeEvaluationService / ValidationRun
```

**Not on live path (periodization / offline):** `MesocyclePlanner`, `TaperPlanner`, `DeloadNeedService`, `LoadProgressionService`, `TemporalModelValidationService`, `ValidationRunService`.

### Dependency graph (simplified)

```
CoachingOrchestrator
 ├─ CoachingModelHealthService ──⚠──→ NextBestWorkoutService (×8 historical probes)  [CONSOLIDATE]
 ├─ AthleteStateService → PpapMetricsService, CoachingDecisionMetricsService
 ├─ NextBestWorkoutService
 │    ├─ PpapMetricsService
 │    ├─ AthleteCalibrationService
 │    ├─ AdaptiveThresholdService
 │    ├─ LoadVariabilityService
 │    ├─ RaceCapabilityService / GoalContext / TrainingPhase / MS readiness
 │    ├─ WorkoutCandidateRanker → ProspectiveOutcomeLookup
 │    └─ WorkoutPrescriptionService → IntensityPrescriptionService
 ├─ WeeklyPlanService → WeeklyPlanOptimizer → PlanSimulation / Availability / ExecutionPattern
 ├─ PlanAdaptationService
 ├─ RecommendationLedgerService
 └─ ShadowRecommendationService
```

### KEEP / MERGE / DEPRECATE

| Component | Verdict | Notes |
|-----------|---------|-------|
| `CoachingOrchestrator` | **KEEP** | Transaction owner; single live entry |
| `NextBestWorkoutService` + `WorkoutCandidateRanker` | **KEEP** | Decision core |
| `PpapMetricsService` | **KEEP** | Canonical metric facade |
| `AthleteCalibrationService` / `AdaptiveThresholdService` | **KEEP** | Personalization + LT |
| Ledger / execution / ValidationRun / shadow outcome | **KEEP** | Closed loop |
| `CoachingAnalysisService._banister_model` | **MERGE** | Duplicate CTL/ATL/TSB vs PPAP |
| `CoachingDecisionMetricsService.get_*recommendation` | **MERGE** | Re-instantiates recommend — thin delegate only |
| MCP `training_readiness_check` parallel policy | **DEPRECATE** as decision authority | Keep as diagnostics only |
| `CoachingModelHealthService` ×8 `recommend` | **CONSOLIDATE** | Use ledger histogram / skip recursive engine |
| Dual readiness (`readiness.total_score` vs MCP `readiness_score`) | **CONSOLIDATE** | Document Garmin score as live; rename MCP composite |
| Monotony 2.0 vs 2.2 | **CONSOLIDATE** | One constant module |
| Confidence field aliases | **CONSOLIDATE** | Keep aliases; prefer `data_quality` / `evidence_strength` / `decision_confidence` |
| `coaching_backtest_v4_service` | **DEPRECATE** label LEGACY | Offline only |
| Mesocycle/taper/deload | **KEEP** off live path | Document as periodization APIs |
| Placeholder `get_fueling_score` / `get_recovery_model_accuracy` | **REMOVE** when touching that file | Always `None` |

**Target:** fewer overlapping rules, same capability.

---

## 2. Single source of truth for derived metrics — P0

| Metric | Canonical producer | Units | Freshness | Fallback | as_of |
|--------|-------------------|-------|-----------|----------|-------|
| CTL | `PpapMetricsService.get_ctl` | Banister fitness | aging with last TSS day | None → missing | day arg |
| ATL | `PpapMetricsService.get_atl` | Banister fatigue | same | missing | day |
| TSB | `PpapMetricsService.get_tsb` | CTL−ATL | same | missing | day |
| HRV deviation | `PpapMetricsService.get_hrv_delta_pct` | % vs baseline | `FreshnessPolicy.hrv_baseline` | missing ≠ negative | day |
| RHR deviation | `PpapMetricsService.get_rhr_delta_bpm` | bpm | same | missing ≠ negative | day |
| LT1 | `AdaptiveThresholdService.estimate_lt1` | bpm / pace | derived | LT2×factor | end_date |
| LT2 | `AdaptiveThresholdService.latest_lt2` | bpm | stale >90d | aging usable as fallback | end_date |
| Critical speed | `PpapMetricsService.get_critical_speed_snapshot` | m/s | CS policy | None | day |
| VO2max | Garmin `vo2_max_precise` | ml/kg/min | VO2 policy | no live estimator | observed_at |
| Durability | `CoachingDecisionMetricsService.get_durability_score` | 0–100 | trend window | low confidence | day |
| EF | activity + `get_ef_rolling` | EF units | context-adjusted optional | missing | day |
| Weekly load | **no single API** → define via MetricRegistry → load_var / minutes | TSS or min | week window | 0 | week_end |
| Monotony | `LoadVariabilityService.analyze` | Foster mean/std | 7d | None | day |
| Session class | `SessionClassifierService` | enum | per activity | unknown | end_date |
| Readiness (live) | Garmin `readiness.total_score` via PPAP | 0–100 | daily | missing | day |

**Action:** introduce lightweight `MetricRegistry` (code module, **no new DB table**) documenting producer + units + freshness key.

---

## 3. Decision trace auditability — P0

**Today:** free-form `decision_trace` list `{factor, value, effect, threshold…}` persisted as JSON.

**Gap:** no stable reason-code registry; hard to aggregate “why”.

**Action:** `DecisionExplanation` + `coaching_reason_codes` registry; map traces → `top_reasons` / `guardrails_triggered` / `alternatives`.

---

## 4–5. Decision consistency & threshold cliffs — P0

Safety cliffs (KEEP hard): readiness &lt; 35 rest; TSB &lt; −25 recovery; hard_days≥3; MS pain; unavailable day.

Heuristic cliffs (SMOOTH / hysteresis where flips): readiness 55/75 bands, evidence_strength 0.35/0.5, ranker gap &lt; 8, deload HRV −10 (should use calibration).

**Action:** `DecisionConsistencyService` perturbation tests; optional hysteresis near non-safety bands; wire deload/progression to shared constants + calibration where safe.

---

## 6–11. Lineage, health, integrity, evidence, decay, drift — P1

| Item | Classification | Action this iteration |
|------|----------------|----------------------|
| Data lineage on explanation | **P1** | Attach freshness via `FreshnessPolicy` + MetricRegistry |
| CoachingHealthService | **P1** | Aggregate sync/model/ValidationRun/samples |
| CoachingIntegrityService | **P1** | Detect orphans/duplicates/cycles; no destructive auto-repair |
| Personalization evidence budget | **P1** | Single `PersonalizationEvidencePolicy` |
| Personalization decay | **P1** | Weight decay by age in policy (no delete) |
| Concept drift | **P1** | Lightweight `AthleteConceptDriftService` rolling windows |
| Training response half-life | **P1** | Broad lag window summary from existing lags |
| Recovery cost model | **P1** | Transparent ranges by session type |
| Session dose | **P1** | Canonical dose dict for effectiveness/recovery |
| Min effective dose | **P2 / DEFER** | Needs more prospective n |
| Plan robustness / replan / stability | **P1** | Explicit policy + scores |
| Novelty/monotony of recs | **P2 / DEFER** | Monitor via health histogram first |
| Mutation testing | **P2 / DEFER** | High maintenance |
| Feedback quality metadata | **P2 / DEFER** | Optional later |
| Race pacing model expansion | **DEFER** | Prove utility first |

---

## 12–19. Planning economics & stability — P1 (selective)

Implement lightweight:

- `RecoveryCostService`
- `session_dose` helper
- response window summarizer (reuse TrainingResponse lags)
- `PlanRobustnessService` + `ReplanningPolicy` + `PlanStabilityService`

Do **not** auto-reschedule from daily HRV noise.

---

## 20–24. Safety, golden masters, migration — P0/P1

- Adversarial safety tests: personalization / shadow / utility cannot schedule on unavailable day; pain cannot raise intensity.
- Golden master fixtures: decision class + reason codes + guardrails (no float equality).
- Migration smoke already covered by alembic tests; add coaching restore/integrity smoke.
- Failure recovery: rely on existing tx/idempotency; document + one interrupted-write test.

---

## 25–28. Interface & governance — P1/P0

- Reason-code registry (machine-readable).
- MCP concise contract: `why`, `guardrails`, `data_freshness`, `plan_stability`, `model_health`, `evidence`.
- **`docs/COACHING_MODEL_GOVERNANCE.md`**: stop condition for new models — **P0 governance**.

---

## Proposed change backlog (classified)

| # | Change | Class |
|---|--------|-------|
| A1 | Architecture KEEP/MERGE/DEPRECATE map (this doc) | P0 |
| A2 | MetricRegistry module | P0 |
| A3 | Threshold cliff inventory + shared constants | P0 |
| A4 | Safety invariant adversarial tests | P0 |
| A5 | Golden master decision tests | P0 |
| A6 | DecisionExplanation + reason codes | P0 |
| A7 | Remove recursive recommend from model health | P0 CONSOLIDATE |
| B1 | Lineage fields on explanation | P1 |
| B2 | CoachingHealthService | P1 |
| B3 | CoachingIntegrityService | P1 |
| B4 | PersonalizationEvidencePolicy (+ decay) | P1 |
| B5 | AthleteConceptDriftService | P1 |
| C1 | RecoveryCostService | P1 |
| C2 | SessionDose | P1 |
| C3 | Response half-life summary | P1 |
| C4 | Plan robustness | P1 |
| D1 | ReplanningPolicy | P1 |
| D2 | PlanStabilityService | P1 |
| D3 | Migration/integrity smoke | P1 |
| E1 | MCP v8 concise fields | P1 |
| E2 | Model governance doc | P0 |
| E3 | Min effective dose | **DEFER** |
| E4 | Mutation testing | **DEFER** |
| E5 | Feedback late_entry weighting | **DEFER** |
| E6 | Recommendation novelty optimizer | **DEFER** |
| E7 | New ML ranker / neural models | **DEFER — forbidden without governance gate** |

---

## Definition of done checklist

1. Canonical metric producers documented in MetricRegistry  
2. Stable reason codes on live recommendations  
3. Consistency tests for insignificant perturbations  
4. Safety guardrails applied after scoring; adversarial tests pass  
5. Integrity checker reports coaching consistency  
6. One personalization evidence policy  
7. Drift service detects relationship change without auto-promote  
8. Recovery cost ranges inform planning consumers  
9. Robustness + replan policy reduce churn from noise  
10. Plan stability metric exposed  
11. Migration/restore/integrity smoke exists  
12. Governance doc answers when NOT to build another model  

**Architectural objective achieved when:** fewer overlapping rules, stronger evidence, more stable decisions, better observability, more prospective learning — **not** more services for their own sake.
