# Coaching V9 Operational Audit

**Branch context:** `main` after PR #47 (`39d08e0`) — post correctness pass.  
**Objective:** Prove the system works in real use → automate quality gates → measure prospective performance → remove legacy complexity → prepare for feature freeze.  
**Not in scope:** new predictive coaching models, readiness scores, ML frameworks, periodization algorithms.

Classification: **P0** correctness · **P1** operational quality · **P2** cleanup · **DEFER**

Verified against repository inventory (CI, services, tests, docs) on current `main`.

---

## Executive summary

The live coaching spine is feature-rich and already hardened (v5–v8 + correctness). The largest operational gaps are:

1. **Coaching invariants are not in GitHub CI** — suites exist locally (`test_coaching_*`, v5/v7) but `ci.yml` only runs platform tests.
2. **Export has no restore write-path** — `validate_restore_payload` only; no roundtrip drill.
3. **No canonical prospective evidence report** — ValidationRun/shadow pieces exist but no single operational report.
4. **Sample floors are fragmented** — `PersonalizationEvidencePolicy` (8/20/40) vs calibration (12) vs promote (20) vs drift (4).
5. **Governance freeze exists** but needs an explicit temporary feature-freeze rule for speculative models.

This iteration implements P0/P1 (plus low-risk P2) without adding predictive layers.

---

## Findings by area

### 1. GitHub CI quality gate — **P0** (implement)

| Status | Detail |
|--------|--------|
| Exists | `.github/workflows/ci.yml`: Ruff, MyPy (narrow), Alembic upgrade, limited pytest, API smoke |
| Gap | No coaching unit/invariant tests; no explicit coaching invariant suite |
| Action | Extend CI + `npm run ci:backend` with coaching invariant module + selected suites |

Required invariants (must fail CI):

- future data cannot alter historical recommendation
- shadow cannot alter production plan
- unavailable day cannot receive workout
- safety guardrail not overridden by personalization
- duplicate sync cannot duplicate execution
- supersede graph remains valid
- insufficient evidence ≠ stable
- preview cannot persist state

### 2. Alembic CI — **P0** (implement)

| Status | Detail |
|--------|--------|
| Exists | `alembic upgrade head` + `test_alembic_migrations.py` in CI |
| Gap | No multi-head detection; no explicit previous-revision → head path; no post-migrate coaching smoke |
| Action | Add heads check, upgrade-from-previous test, startup smoke after migrate |

### 3. Backup/restore drill — **P0** (implement)

| Status | Detail |
|--------|--------|
| Exists | `CoachingDataExportService.export_*` + `validate_restore_payload` |
| Gap | No `restore()`; no `RestoreValidationReport`; no roundtrip test |
| Action | Implement restore + integrity-backed validation report |

### 4. Prospective evidence report — **P0** (implement)

| Status | Detail |
|--------|--------|
| Exists | Ledger, executions, shadow outcome eval, ValidationRun dashboard fragments |
| Gap | No `ProspectiveEvidenceReportService` |
| Action | Canonical report from **recorded** prospective data only |

### 5. Sample sufficiency policy — **P0** (implement)

| Status | Detail |
|--------|--------|
| Exists | `PersonalizationEvidencePolicy` |
| Gap | Parallel thresholds in calibration, drift, promotion, prospective lookup |
| Action | `SampleSufficiencyPolicy` as canonical floors + temporal spread; wrap/delegate from policy |

### 6. Prospective-first evidence hierarchy — **P0** (implement)

| Status | Detail |
|--------|--------|
| Exists | Partial in RecoveryCost `source` field |
| Gap | Not standardized across services |
| Action | `EvidenceHierarchy` helper with prospective → historical → default |

### 7–15. Monitors — **P1** (implement)

Confidence calibration, abstention quality, recommendation distribution, model change impact, shadow readiness, plan/recommendation churn, data latency, data-quality trend — monitoring only, no auto-rollback.

### 16. Feedback completion — **P2** (low-risk implement)

`FeedbackValueService` — priority signals only, no spam.

### 17–18. Legacy deletion / duplicate calc — **P1** (audit + low-risk)

| Candidate | Replacement | Safe to remove now? |
|-----------|-------------|---------------------|
| `CoachingAnalysisService._banister_model` | PPAP CTL/ATL/TSB | **No** — analytics API + MCP still call it |
| Placeholders `get_fueling_score` / `get_recovery_model_accuracy` | N/A (always None) | **Yes** if callers tolerate removal |
| Thin wrappers / backtest v2 labels | Orchestrator | Prefer deprecate docs; delete only if callers=0 |

Full Banister merge deferred (**DEFER**) — high blast radius for aesthetics.

### 19. Config centralization — **P1** (light)

Centralize model-configurable coaching constants in one module; leave SAFETY constants explicit.

### 20–21. Perf regression CI / DB growth — **P2** (DEFER / light)

Generous N+1 integrity budget already exists. Full perf CI deferred to avoid flake. Growth estimate in ops doc only.

### 22–23. Ops runbook + monthly review — **P1** (implement)

### 24. Feature freeze governance — **P0** (implement)

Update `COACHING_MODEL_GOVERNANCE.md` with temporary freeze rule.

---

## Implementation sprints (this PR)

| Sprint | Items |
|--------|-------|
| A | CI gate, Alembic CI, restore drill, SampleSufficiency, evidence hierarchy |
| B | ProspectiveEvidenceReport, confidence/abstention/distribution/shadow |
| C | Plan/rec churn, latency, data-quality trend |
| D | Low-risk legacy cleanup, config module, duplicate audit notes |
| E | Ops runbook, monthly review, governance freeze |

---

## Explicit DEFER

- New readiness / race / periodization / ML models
- Automatic shadow promotion
- Automatic confidence recalibration from small n
- Full Banister deletion from analytics API
- Flaky millisecond perf CI
- Automatic deletion of recommendation/execution history
