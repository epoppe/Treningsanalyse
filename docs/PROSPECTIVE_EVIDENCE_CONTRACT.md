# Prospective evidence contract

Canonical path for one coaching observation:

```text
RecommendationRecord
  → canonical resolution (one chain tip; shadow excluded)
  → RecommendationExecution          (authoritative when present)
  → Activity                         (legacy heuristic only if no execution link)
  → outcome maturity                 (pending / mature / incomplete_data / evaluated)
  → observed outcome                 (observational, not causal)
  → evidence sufficiency             (SampleSufficiencyPolicy, metric-specific n)
```

`CanonicalProspectiveObservationService` is the only place that decides which
`RecommendationRecord` is one prospective observation. Evidence services consume
that result. They do not re-implement supersede-chain selection.

## What counts as one observation

- Shadow recommendations (`RecommendationRecord.is_shadow` and `ShadowRecommendation`)
  are excluded from production evidence.
- A supersede chain (`superseded_by_id`) is one observation. The canonical row is
  the chain tip: active, otherwise latest `generated_at`, otherwise highest id.
- Several unlinked tips on the same `as_of_date` collapse to one deterministic tip.
  `ledger_quality` says `multiple_unlinked_same_day`.
- A broken pointer or a cycle does not loop and does not disappear. `ledger_quality`
  is `incomplete_supersede_graph`.

Returned metadata includes `recommendation_id`, `as_of_date`, `canonical`,
`supersede_chain_length`, `execution_id`, `activity_id`, `observation_status`,
and `maturity_status`.

## Matching

| Situation | `match_source` | Evidence weight |
|---|---|---|
| `RecommendationExecution` on the chain | `explicit_execution` | 1.0 |
| No execution, running activity on the day or within 3 days, window closed | `legacy_heuristic` | 0.35 |
| Window still open, no execution | `none` | 0.0 (`execution_status=pending`) |

An explicit execution is never replaced by the legacy activity search.
Legacy rows carry `match_confidence` and `match_reason`.

## Maturity

| Outcome | Closed when | Pending means |
|---|---|---|
| Execution | the recommendation calendar day has ended | not skipped, not a failure |
| Short-term recovery (HRV/RHR, ~24–48h) | `today >= as_of + 2 days` | missing markers are not a poor response |
| Medium-term (through +21 days) | `today >= as_of + 21 days` | missing CTL/TSB change is not a decline |

Only `evaluated` rows enter that metric's denominator. `pending_count` is reported
beside the mean. `sample_count` is per metric: recommendations, execution,
adherence, short-term recovery, session quality included in that short-term score, medium-term, subjective feedback.

## Words that are not interchangeable

| Term | Means |
|---|---|
| Recommendation | The recorded prescription (`RecommendationRecord` chain tip). |
| Execution | What was done relative to that prescription (`followed`, `modified`, `replaced`, `skipped`, `unplanned`, `pending`). |
| Adherence | How closely duration/intensity matched the prescription. A feasibility fact. |
| Feasibility | Probability or history of the athlete carrying out that session type. Used for planning. |
| Session quality | Markers on the performed activity. Not adherence. |
| Recovery response | Observed HRV/RHR/TSB after the **actual** session. `observed_recovery_response`. Observational, not causal. |
| Expected recovery cost | What the default envelope expected the **recommended** type to cost. `expected_recovery_cost`. |
| Training effectiveness | Physiological or training response (short-term utility, medium-term change). Not "the user usually complies". |
| Utility | Bounded 0–1 summary of observed markers. Higher HRV than baseline raises short-term utility. |
| Confidence | `decision_confidence` is the estimated probability of the binary favorable outcome below. |
| Evidence strength | How much independent, mature, well-spread data supports a statement (`SampleSufficiencyPolicy`). |

`get_hrv_delta_pct` is percent vs baseline: `100 * (today - baseline) / baseline`.
Positive means HRV is above baseline. Missing HRV is missing, not a drop.

Once the short-term window is evaluated, short-term utility may also include the
existing `SessionQualityService` score for the linked activity. That score is
mapped from 0–100 to 0–1 and enters the average once, beside HRV and RHR. It is
left out while the window is pending, when there is no linked activity or no
scorable session type, and when the quality service returns no measured
components — its default prior is not an observation. Missing quality does not
lower the average. Session quality is not adherence and is not mixed into
`expected_recovery_cost`. `session_quality_outcomes` counts how many short-term
outcomes included that score. It is not a separate composite.

Favorable outcome for calibration (not built from confidence):

```text
short_term_maturity == evaluated AND short_term_utility >= 0.55
```

`DecisionConfidenceMonitor` reports sample count, Brier score, calibration bins,
expected calibration error, coverage, abstention rate, and status.
`INSUFFICIENT_DATA` below the `confidence_calibration` floor. No auto-recalibration.

`ModelChangeImpactService` may say `consistent_with_improvement` only when both
windows have enough mature favorable-outcome evidence and the later rate is
materially higher. A change in workout mix alone is `no_material_change` or
`possible_regression`, never improvement. A type that is new in the later
window is reported as `from_zero`. That marker is not an unexpected shift, so
it does not relabel a real outcome improvement as a regression.

The monthly review pairs each mean with its own sample count, including
short-term utility, session quality included in that utility, medium-term
change, observed recovery, and subjective feedback. `sparse_data` stays true
until short-term effectiveness reaches `SUPPORTED`. Recommendation count alone
does not clear that gate. `Shadow ELIGIBLE` in the review is not a promotion.

A recorded recommendation whose execution can already be judged stays
`outcome=pending` until the short-term window closes. The per-recommendation
label uses the same session-quality rule: a score with no measured components
is missing, so the quality service's default prior cannot become
`favorable_response`.

## Subjective feedback

`AthleteFeedback` is a separate observational source (`provenance=athlete_feedback`).
It has its own sample count. It does not replace Garmin markers, it is not ground
truth, and it does not by itself define effectiveness. Asking for it stays on the
existing low-friction rule in `FeedbackValueService` (do not require feedback after
every workout).

A prospective observation includes feedback only when `recorded_at` is on or
before `min(today, as_of + SHORT_TERM_LAG_DAYS)`. A later row does not replace
an in-window row, and feedback that exists only after the cutoff stays missing.
Edits update the latest row and keep the original `recorded_at`. The same cutoff
applies when feedback raises an observed recovery estimate. Deload on a date
uses feedback recorded on or before that date.

## Sufficiency

Prospective denominators use `SampleSufficiencyPolicy` (`assess` / `assess_weighted`).
`ProspectiveOutcomeLookup` does not keep a private `MIN_SAMPLES`.

Local floors that remain are estimator or hysteresis constraints, not a second
evidence policy: Theil-Sen slope/direction sample sizes, calibration-snapshot
step damping, and the concept-drift per-window count (that count is the
`concept_drift` emerging floor).
