# Coaching Model Governance

**Purpose:** Prefer accumulating prospective evidence over adding speculative models.

This project already has a closed loop (recommendation → execution → outcome), ValidationRun promotion, baselines, and shadow evaluation. Further predictive/personalized coaching models must pass the gate below.

---

## Stop condition (mandatory)

Do **not** add a new predictive or personalized coaching model unless **all** of the following are true:

| # | Requirement | Evidence |
|---|-------------|----------|
| **A** | Existing model has a **documented deficiency** | Issue/doc citing ValidationRun, shadow outcome gap, or safety incident — not vibes |
| **B** | **Outcome metric** is defined | Utility / recovery cost / adherence / race decomposition — not imitation-only |
| **C** | A **baseline** exists | `CoachingBaselines` or prior active model |
| **D** | **Enough data** exists to evaluate | Prospective sample size meeting `PersonalizationEvidencePolicy` / ValidationRun `sample_size` floors |
| **E** | Expected **decision impact is material** | Would change prescriptions or periodization in a non-trivial fraction of days |

If any item fails → **DEFER**. Improve data quality, sync reliability, explanations, or integrity instead.

---

## Allowed work without a new model

- Consolidating duplicate metric producers
- Explainability / reason codes
- Observability and integrity
- Safety invariant hardening
- Calibration of confidence (reliability diagrams)
- Shadow outcome evaluation and promotion discipline
- Plan stability / replan hysteresis
- Bug fixes and performance (query budget)

---

## Promotion still requires ValidationRun

Activation of any new or changed ranker/calibration config requires:

```text
promote(model_key=..., version=..., validation_run_id=...)
```

Manual gate dicts are emergency-only (`manual_override=true` + reason).

Shadow recommendations must never mutate the active plan.

---

## Anti-patterns

- Black-box ML “because we can”
- New composite scores that do not change a decision
- Wrapper services that only call another service
- Self-certification without immutable ValidationRun
- Treating missing data as negative physiology
- Personalizing taper / doses from n &lt; policy minimum

---

## Review question for every PR

> Does this help us **prove what works** with prospective evidence, or does it add another unverified rule?

If the latter — reject or reclassify as DEFER.
