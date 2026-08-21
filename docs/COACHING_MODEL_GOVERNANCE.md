# Coaching Model Governance

**Purpose:** Prefer accumulating prospective evidence over adding speculative models.

This project already has a closed loop (recommendation → execution → outcome), ValidationRun promotion, baselines, and shadow evaluation. Further predictive/personalized coaching models must pass the gate below.

---

## Temporary feature freeze (mandatory after V9)

**Do not add a new predictive coaching model** unless **all** of the following are true:

| # | Requirement | Evidence |
|---|-------------|----------|
| **1** | Existing model has a **measured deficiency** | `ProspectiveEvidenceReportService` / monthly review citing material problem — not vibes |
| **2** | Prospective report demonstrates the problem | Recorded prospective sample with `SampleSufficiencyPolicy` ≥ SUPPORTED where relevant |
| **3** | Outcome metric is defined | Utility / recovery cost / adherence — not imitation-only |
| **4** | Baseline exists | Active model or `CoachingBaselines` |
| **5** | Enough data exists for evaluation | Sufficiency policy + ValidationRun floors |
| **6** | A simpler rule/config change cannot solve it | Documented alternative rejected |

If any item fails → **DEFER**. Improve data quality, sync reliability, explanations, integrity, or monitoring instead.

**Allowed during freeze:** dashboards, reporting, bug fixes, observability, CI, restore drills, duplicate consolidation, documentation.

**Not allowed during freeze:** new readiness scores, race predictors, neural nets, generic ML frameworks, new periodization algorithms, new composite scores, new Garmin metrics “because they exist”.

---

## Stop condition (ongoing)

Do **not** add a new predictive or personalized coaching model unless **all** of the following are true:

| # | Requirement | Evidence |
|---|-------------|----------|
| **A** | Existing model has a **documented deficiency** | Issue/doc citing ValidationRun, shadow outcome gap, prospective report, or safety incident |
| **B** | **Outcome metric** is defined | Utility / recovery cost / adherence / race decomposition — not imitation-only |
| **C** | A **baseline** exists | `CoachingBaselines` or prior active model |
| **D** | **Enough data** exists to evaluate | `SampleSufficiencyPolicy` / `PersonalizationEvidencePolicy` / ValidationRun floors |
| **E** | Expected **decision impact is material** | Would change prescriptions or periodization in a non-trivial fraction of days |

If any item fails → **DEFER**.

---

## Allowed work without a new model

- Consolidating duplicate metric producers
- Explainability / reason codes
- Observability and integrity
- Safety invariant hardening
- Confidence calibration **monitoring** (no auto-recalibration from small n)
- Shadow outcome evaluation and promotion discipline
- Plan / recommendation churn monitoring
- Bug fixes and performance (query budget)
- Export/restore and operational runbooks

---

## Promotion still requires ValidationRun

Activation of any new or changed ranker/calibration config requires:

```text
promote(model_key=..., version=..., validation_run_id=...)
```

Manual gate dicts are emergency-only (`manual_override=true` + reason).

Shadow recommendations must never mutate the active plan.

Shadow status `ELIGIBLE` ≠ promoted — still requires registry gates.

---

## Evidence hierarchy

1. Prospective personal evidence (if `SampleSufficiencyPolicy` allows)
2. Historical personal evidence (if sufficient)
3. Physiological / default rules

Personal data alone does **not** auto-replace defaults.

---

## Anti-patterns

- Black-box ML “because we can”
- New composite scores that do not change a decision
- Wrapper services that only call another service
- Self-certification without immutable ValidationRun
- Treating missing data as negative physiology
- Personalizing taper / doses from n &lt; policy minimum
- Calling low sample = stable / healthy
- Calling historical correlation = causal
- Calling shadow improvement = proven improvement

---

## Review question for every PR

> Does this help us **prove what works** with prospective evidence, or does it add another unverified rule?

If the latter — reject or reclassify as DEFER.

After V9: **FREEZE NEW PREDICTIVE COACHING FEATURES.** Collect prospective data and use the monthly review to decide whether another model change is justified.
