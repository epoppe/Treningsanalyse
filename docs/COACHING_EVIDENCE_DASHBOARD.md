# Coaching evidence dashboard

Depends on the prospective evidence contract in
`docs/PROSPECTIVE_EVIDENCE_CONTRACT.md` (PR #81,
`cursor/prospective-evidence-correctness-a924`). This dashboard does not
fork that semantics and does not add a predictive model.

## Purpose

`GET /api/dashboard/coaching-evidence` shows prospective observational
evidence for a chosen analysis window (30, 90, 180, or 365 days).

It is not causal proof. The window does not change physiological models,
calibration parameters, the plan, or the ledger. The handler is read-only:
it does not recommend, persist, promote a shadow model, recalibrate, or
write feedback. The evidence, feedback, and feedback-prompt GET responses
are `Cache-Control: no-store`, so a saved feel is not hidden behind a cached
prompt.

## Definitions

| Term | Means |
|---|---|
| Recommendation | Canonical `RecommendationRecord` chain tip. Shadow and superseded rows are not extra N. |
| Execution | Followed, modified, replaced, skipped, unplanned, or pending. |
| Feasibility | Whether that session type was carried out. Separate from effect. |
| Adherence | How closely duration or intensity matched. A feasibility fact. |
| Session quality | Markers on the performed activity, included in short-term utility only when that window is evaluated. |
| Physiological response | Observed HRV, RHR, TSB, and the short-term utility built from them. |
| Subjective feedback | Athlete RPE, feel, legs, motivation, and pain. Extra signal, not ground truth. |
| Effectiveness | Mature physiological or training response. Not "the athlete usually complies". |
| Evidence strength | `SampleSufficiencyPolicy` level for that metric. Small N stays insufficient. |
| Confidence calibration | How often `decision_confidence` matches the binary favorable outcome. `INSUFFICIENT_DATA` when the floor is not met. |

Pending, incomplete, evaluated, and insufficient evidence are separate
statuses. Pending is an open window. Incomplete is a closed window without
the required points. Insufficient evidence means some outcomes exist, but
N or spread is too low.

## Evidence hierarchy

Personal prospective evidence, then historical personal evidence, then
defaults. The dashboard does not override defaults unless short-term
effectiveness is `SUPPORTED` or `STRONG`. Until then `do_not_change`
repeats the monthly-review gate. `Shadow ELIGIBLE` is not a promotion.

The dashboard keeps the English governance sentences in `do_not_change` so they
stay identical to the monthly review. `do_not_change_nb` and `operations_lines`
are the Norwegian presentation of those same gates. A missing race
recommendation says taper is not personalized. A medium-term line appears only
when a short-term outcome already exists.

## Feedback

`GET` and `PUT /api/activities/{activity_id}/feedback` read and replace the
latest `AthleteFeedback` row. A repeated edit updates that row. It does not
insert another one, and it does not rewrite recommendation records.

Scales live on the service: RPE 1–10, pain 0–10, motivation 1–5, and the
existing feel and legs sets. Invalid values return 422. Unknown activities
return 404.

`GET /api/activities/{activity_id}/feedback-prompt` asks `FeedbackValueService`
whether a prompt has information value. It does not prompt every workout,
does not prompt an activity that already has feedback, and does not prompt
activities older than 14 days. The call does not write.

## Flow

```text
CanonicalProspectiveObservation
  → RecommendationUtilityEvaluator (once per observation)
  → CoachingEvidenceDashboardService
  → GET /api/dashboard/coaching-evidence
  → Analyse /analyse?tab=coaching
```

```text
Activity
  → feedback prompt (read-only)
  → PUT AthleteFeedback (latest row)
  → subjective_feedback on the next canonical observation
```
