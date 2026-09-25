"""Read-only coaching evidence for the analyse workspace.

Composes canonical observations and the existing monitors. It does not
recommend, persist, promote, recalibrate, or write feedback.
Depends on the prospective-evidence semantics: one canonical observation,
pending windows outside mature denominators, SampleSufficiencyPolicy.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .canonical_prospective_observation import CanonicalProspectiveObservationService
from .coaching_model_registry import CoachingModelRegistry
from .coaching_operational_monitors import (
    AbstentionQualityService,
    DecisionConfidenceMonitor,
    PlanChurnMonitor,
    RecommendationChurnMonitor,
    RecommendationDistributionMonitor,
    ShadowPromotionReadinessService,
)
from .data_quality_snapshot import DataQualitySnapshotService
from .feedback_prompt_service import QUALITY_SESSION_TYPES
from .monthly_coaching_review_service import coaching_do_not_change
from .outcome_maturity import EVALUATED, INCOMPLETE_DATA, PENDING, is_usable_status
from .sample_sufficiency_policy import DOMAIN_FLOORS
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator
from .sample_sufficiency_policy import SampleSufficiencyPolicy

ALLOWED_WINDOWS = (30, 90, 180, 365)
_OBSERVATION_CAP = 12

_LEVEL_LABEL = {
    "INSUFFICIENT": "Utilstrekkelig",
    "EMERGING": "Fremvoksende",
    "SUPPORTED": "Støttet",
    "STRONG": "Sterk",
}
_STRENGTH = {
    "INSUFFICIENT": "none",
    "EMERGING": "limited",
    "SUPPORTED": "supported",
    "STRONG": "strong",
}
_TYPE_LABEL = {
    "easy_run": "Rolig løping",
    "long_run": "Langtur",
    "threshold": "Terskel",
    "vo2_intervals": "VO₂-intervaller",
    "rest": "Hvile",
    "race_pace": "Konkurransefart",
    "race": "Konkurranse",
}
_STRENGTH_LABEL = {
    "none": "Ingen",
    "limited": "Begrenset",
    "supported": "Støttet",
    "strong": "Sterk",
}
_DO_NOT_CHANGE_NB = {
    "Do not add a new predictive coaching model without ProspectiveEvidenceReport deficiency.": (
        "Ikke legg til en ny prediktiv coachingmodell uten påvist mangel i den prospektive evidensrapporten."
    ),
    "Do not treat sparse samples as proof of stability or improvement.": (
        "Små utvalg er ikke bevis på stabilitet eller forbedring."
    ),
    "Sample too sparse for model changes — collect more prospective data.": (
        "Utvalget er for tynt for modellendring. Samle flere prospektive utfall."
    ),
    "Short-term effectiveness is below SUPPORTED — collect mature prospective outcomes before any model change.": (
        "Korttidseffekt er under støttet nivå. Samle modne prospektive utfall før modellen endres."
    ),
    "Shadow ELIGIBLE is not a promotion. Promotion still requires a validation run.": (
        "Skygge som er eligible er ikke en promotering. Promotering krever fortsatt en valideringskjøring."
    ),
    "Shadow model is not ELIGIBLE — do not promote.": (
        "Skyggemodellen er ikke eligible, og skal ikke promoteres."
    ),
    "Confidence calibration not proven — do not tune confidence blindly.": (
        "Confidence-kalibrering er ikke vist, og skal ikke justeres i blinde."
    ),
}

MATURITY_LEGEND = (
    {
        "status": "pending",
        "label": "Venter",
        "text": "Outcome-vinduet er ikke ferdig ennå.",
    },
    {
        "status": "incomplete_data",
        "label": "Ufullstendig",
        "text": "Vinduet er ferdig, men nødvendige datapunkter manglet.",
    },
    {
        "status": "evaluated",
        "label": "Vurdert",
        "text": "Vinduet er lukket og utfallet har en verdi.",
    },
    {
        "status": "insufficient",
        "label": "Utilstrekkelig evidens",
        "text": "Enkelte outcomes finnes, men samlet N eller spredning er for lav.",
    },
)


_INSUFFICIENT_CHANGE = {
    "status": "INSUFFICIENT_EVIDENCE",
    "text": "For lite prospektiv evidens til å konkludere om coachen har blitt bedre.",
    "causal": False,
}
_CHANGE_DELTA_FLOOR = 0.05


def coaching_change_comparison(
    observations: List[Dict[str, Any]],
    utilities: Dict[int, Dict[str, Any]],
    short_sufficiency: Dict[str, Any],
    *,
    start: date,
    end: date,
) -> Dict[str, Any]:
    """Observational early-vs-late short-term utility.

    The comparison is returned only when the whole window is SUPPORTED or
    STRONG and each half meets the workout-effectiveness emerging floor.
    """
    level = short_sufficiency.get("level")
    if level not in {"SUPPORTED", "STRONG"}:
        return {**_INSUFFICIENT_CHANGE, "evidence_level": level}
    points = []
    for row in observations:
        utility = utilities.get(row["recommendation_id"]) or {}
        if is_usable_status(utility.get("short_term_maturity")) and utility.get("short_term_utility") is not None:
            points.append((date.fromisoformat(row["as_of_date"]), float(utility["short_term_utility"])))
    midpoint = start + (end - start) / 2
    earlier = [value for day, value in points if day < midpoint]
    later = [value for day, value in points if day >= midpoint]
    floor = DOMAIN_FLOORS["workout_effectiveness"]["emerging"]
    if len(earlier) < floor or len(later) < floor:
        return {
            **_INSUFFICIENT_CHANGE,
            "evidence_level": level,
            "earlier_n": len(earlier),
            "later_n": len(later),
            "reason": "Each half of the window needs the emerging short-term floor before a comparison is shown.",
        }
    earlier_mean = round(sum(earlier) / len(earlier), 3)
    later_mean = round(sum(later) / len(later), 3)
    delta = round(later_mean - earlier_mean, 3)
    if abs(delta) < _CHANGE_DELTA_FLOOR:
        direction = "unchanged"
        text = (
            f"Korttidsutfall er omtrent uendret fra første til andre halvdel "
            f"({earlier_mean} og {later_mean}, N {len(earlier)} og {len(later)}). "
            "Det er en observasjon, ikke en årsak."
        )
    elif delta > 0:
        direction = "later_higher"
        text = (
            f"Korttidsutfall er høyere i andre halvdel ({later_mean}) enn i første ({earlier_mean}), "
            f"N {len(earlier)} og {len(later)}. Observasjonelt, ikke en påvist effekt av coachen."
        )
    else:
        direction = "later_lower"
        text = (
            f"Korttidsutfall er lavere i andre halvdel ({later_mean}) enn i første ({earlier_mean}), "
            f"N {len(earlier)} og {len(later)}. Observasjonelt, ikke en påvist effekt av coachen."
        )
    return {
        "status": "OBSERVATIONAL",
        "evidence_level": level,
        "direction": direction,
        "earlier_mean": earlier_mean,
        "later_mean": later_mean,
        "earlier_n": len(earlier),
        "later_n": len(later),
        "delta": delta,
        "text": text,
        "causal": False,
    }


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _level_label(level: Optional[str]) -> str:
    return _LEVEL_LABEL.get(level or "", "Utilstrekkelig")


class CoachingEvidenceDashboardService:
    def __init__(self, db: Session):
        self.db = db
        self._canonical = CanonicalProspectiveObservationService(db)
        self._utility = RecommendationUtilityEvaluator(db)
        self._sufficiency = SampleSufficiencyPolicy()

    def build(self, *, window_days: int = 90, end: Optional[date] = None) -> Dict[str, Any]:
        if window_days not in ALLOWED_WINDOWS:
            raise ValueError(f"window_days must be one of {ALLOWED_WINDOWS}")
        end = min(end or date.today(), date.today())
        start = end - timedelta(days=window_days)
        observations = self._canonical.resolve(start=start, end=end, today=end)
        utilities = {
            row["recommendation_id"]: self._utility.evaluate_for_observation(row, today=end)
            for row in observations
        }
        by_type = self._by_type(observations, utilities, as_of=end)
        confidence = DecisionConfidenceMonitor(self.db).assess(
            start=start,
            end=end,
            observations=observations,
            utility_by_id=utilities,
        )
        abstention = AbstentionQualityService().assess(
            self.db, start=start, end=end, observations=observations
        )
        distribution = RecommendationDistributionMonitor().assess(
            self.db, start=start, end=end, current_observations=observations
        )
        short_dates = []
        short_weights = []
        for row in observations:
            utility = utilities[row["recommendation_id"]]
            if is_usable_status(utility.get("short_term_maturity")) and utility.get("short_term_utility") is not None:
                short_dates.append(date.fromisoformat(row["as_of_date"]))
                short_weights.append(float(row.get("evidence_weight") or 0.0) or 1.0)
        short_sufficiency = self._sufficiency.assess_weighted(
            domain="workout_effectiveness",
            observation_dates=short_dates,
            evidence_weights=short_weights,
            as_of=end,
        )
        overview = self._overview(observations, utilities, short_sufficiency)
        evidence_quality = self._evidence_quality(observations, utilities, short_sufficiency)
        feasibility = self._feasibility(observations, as_of=end)
        active = CoachingModelRegistry(self.db).get_active("ranker")
        known, unknown = self._insights(by_type, confidence, overview)
        snapshot = DataQualitySnapshotService(self.db).from_observations(
            observations=observations,
            utilities=utilities,
            start=start,
            end=end,
            window_days=window_days,
        )
        operations = self._operations(
            start=start,
            end=end,
            abstention=abstention,
            distribution=distribution,
            snapshot=snapshot,
        )
        do_not_change = coaching_do_not_change(
            recommendation_count=overview["canonical_recommendation_count"],
            effectiveness_supported=bool(short_sufficiency.get("may_override_defaults")),
            shadow_status=(operations.get("shadow") or {}).get("status"),
            confidence_status=confidence.get("status"),
        )
        return {
            "status": "ok",
            "read_only": True,
            "evaluation_kind": "observational_outcome",
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "window_days": window_days,
                "allowed_windows": list(ALLOWED_WINDOWS),
            },
            "meta": {
                "depends_on": "canonical prospective evidence",
                "causal": False,
                "note": (
                    "Observational evidence inside the selected window. "
                    "The window does not change models, calibration, or the plan."
                ),
            },
            "maturity_legend": list(MATURITY_LEGEND),
            "overview": {**overview, "model_version": active.get("version"), "model_status": active.get("status")},
            "effectiveness": by_type,
            "feasibility": feasibility,
            "confidence": _public_confidence(confidence),
            "evidence_quality": evidence_quality,
            "signals": _signals(observations, utilities),
            "operations": operations,
            "operations_lines": _operations_lines(operations),
            "data_quality_snapshot": snapshot,
            "coaching_change": coaching_change_comparison(
                observations,
                utilities,
                short_sufficiency,
                start=start,
                end=end,
            ),
            "what_we_know": known,
            "what_we_do_not_know": unknown,
            "do_not_change": do_not_change,
            "do_not_change_nb": [_DO_NOT_CHANGE_NB.get(line, line) for line in do_not_change],
        }

    def _overview(
        self,
        observations: List[Dict[str, Any]],
        utilities: Dict[int, Dict[str, Any]],
        short_sufficiency: Dict[str, Any],
    ) -> Dict[str, Any]:
        pending = 0
        mature_execution = 0
        short_n = 0
        medium_n = 0
        feedback_n = 0
        explicit = 0
        legacy = 0
        for row in observations:
            status = (row.get("execution_status") or "").lower()
            if status == "pending":
                pending += 1
            else:
                mature_execution += 1
            if row.get("match_source") == "explicit_execution":
                explicit += 1
            elif row.get("match_source") == "legacy_heuristic":
                legacy += 1
            if row.get("subjective_feedback"):
                feedback_n += 1
            utility = utilities[row["recommendation_id"]]
            if is_usable_status(utility.get("short_term_maturity")) and utility.get("short_term_utility") is not None:
                short_n += 1
            if is_usable_status(utility.get("medium_term_maturity")) and utility.get("medium_term_utility") is not None:
                medium_n += 1
        matched = explicit + legacy
        n = len(observations)
        return {
            "canonical_recommendation_count": n,
            "mature_execution_count": mature_execution,
            "pending_count": pending,
            "short_term_outcome_count": short_n,
            "medium_term_outcome_count": medium_n,
            "evidence_level": short_sufficiency.get("level"),
            "evidence_label": _level_label(short_sufficiency.get("level")),
            "feedback_count": feedback_n,
            "feedback_coverage": round(feedback_n / n, 3) if n else None,
            "explicit_match_count": explicit,
            "legacy_match_count": legacy,
            "explicit_matching_share": round(explicit / matched, 3) if matched else None,
        }

    def _by_type(
        self,
        observations: List[Dict[str, Any]],
        utilities: Dict[int, Dict[str, Any]],
        *,
        as_of: date,
    ) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "short_vals": [],
                "short_dates": [],
                "short_weights": [],
                "medium_vals": [],
                "medium_dates": [],
                "quality_vals": [],
                "recovery_vals": [],
                "quality_scores": [],
                "pending": 0,
                "execution": 0,
                "recommendations": 0,
                "feedback": 0,
                "incomplete": 0,
                "observations": [],
            }
        )
        for row in observations:
            wtype = row.get("recommended_workout_type") or "unknown"
            bucket = buckets[wtype]
            bucket["recommendations"] += 1
            status = (row.get("execution_status") or "").lower()
            if status == "pending":
                bucket["pending"] += 1
            else:
                bucket["execution"] += 1
            if row.get("subjective_feedback"):
                bucket["feedback"] += 1
            if row.get("data_quality_score") is not None:
                bucket["quality_scores"].append(float(row["data_quality_score"]))
            utility = utilities[row["recommendation_id"]]
            weight = float(row.get("evidence_weight") or 0.0) or 1.0
            obs_date = date.fromisoformat(row["as_of_date"])
            if utility.get("short_term_maturity") == PENDING:
                pass
            elif utility.get("short_term_maturity") == INCOMPLETE_DATA:
                bucket["incomplete"] += 1
            elif is_usable_status(utility.get("short_term_maturity")) and utility.get("short_term_utility") is not None:
                bucket["short_vals"].append(float(utility["short_term_utility"]))
                bucket["short_dates"].append(obs_date)
                bucket["short_weights"].append(weight)
            if is_usable_status(utility.get("medium_term_maturity")) and utility.get("medium_term_utility") is not None:
                bucket["medium_vals"].append(float(utility["medium_term_utility"]))
                bucket["medium_dates"].append(obs_date)
            if utility.get("session_quality_included") and utility.get("session_quality_component") is not None:
                bucket["quality_vals"].append(float(utility["session_quality_component"]))
            observed = utility.get("observed_recovery_response") or {}
            if is_usable_status(observed.get("maturity_status")) and observed.get("value") is not None:
                bucket["recovery_vals"].append(float(observed["value"]))
            if len(bucket["observations"]) < _OBSERVATION_CAP:
                bucket["observations"].append(
                    {
                        "recommendation_id": row.get("recommendation_id"),
                        "as_of_date": row.get("as_of_date"),
                        "activity_id": row.get("activity_id"),
                        "execution_status": row.get("execution_status"),
                        "match_source": row.get("match_source"),
                        "short_term_maturity": utility.get("short_term_maturity"),
                        "short_term_utility": utility.get("short_term_utility"),
                    }
                )
        result = []
        for wtype, bucket in sorted(buckets.items()):
            sufficiency = self._sufficiency.assess_weighted(
                domain="workout_effectiveness",
                observation_dates=bucket["short_dates"],
                evidence_weights=bucket["short_weights"],
                as_of=as_of,
            )
            medium_sufficiency = self._sufficiency.assess_weighted(
                domain="workout_effectiveness",
                observation_dates=bucket["medium_dates"],
                evidence_weights=[1.0] * len(bucket["medium_dates"]),
                as_of=as_of,
            )
            level = sufficiency.get("level")
            result.append(
                {
                    "workout_type": wtype,
                    "label": _TYPE_LABEL.get(wtype, wtype),
                    "recommendation_count": bucket["recommendations"],
                    "execution_count": bucket["execution"],
                    "mature_outcome_count": len(bucket["short_vals"]),
                    "pending_count": bucket["pending"],
                    "incomplete_count": bucket["incomplete"],
                    "short_term_outcome": _mean(bucket["short_vals"]),
                    "short_term_sample_count": len(bucket["short_vals"]),
                    "medium_term_outcome": _mean(bucket["medium_vals"]),
                    "medium_term_sample_count": len(bucket["medium_vals"]),
                    "medium_spread_days": medium_sufficiency.get("spread_days"),
                    "medium_evidence_level": medium_sufficiency.get("level"),
                    "data_quality_mean": _mean(bucket["quality_scores"]),
                    "data_quality_sample_count": len(bucket["quality_scores"]),
                    "session_quality": _mean(bucket["quality_vals"]),
                    "session_quality_sample_count": len(bucket["quality_vals"]),
                    "observed_recovery_response": _mean(bucket["recovery_vals"]),
                    "observed_recovery_sample_count": len(bucket["recovery_vals"]),
                    "feedback_count": bucket["feedback"],
                    "evidence_level": level,
                    "evidence_label": _level_label(level),
                    "conclusion_strength": _STRENGTH.get(level or "", "none"),
                    "conclusion_strength_label": _STRENGTH_LABEL.get(
                        _STRENGTH.get(level or "", "none"), "Ingen"
                    ),
                    "sufficiency": sufficiency,
                    "observations": bucket["observations"],
                }
            )
        return result

    def _feasibility(self, observations: List[Dict[str, Any]], *, as_of: date) -> Dict[str, Any]:
        counts = {"followed": 0, "modified": 0, "replaced": 0, "skipped": 0, "pending": 0, "unplanned": 0}
        adherence = []
        dates = []
        weights = []
        for row in observations:
            status = (row.get("execution_status") or "").lower()
            if status in counts:
                counts[status] += 1
            elif status in {"completed", "executed", "done"}:
                counts["followed"] += 1
            if status != "pending":
                dates.append(date.fromisoformat(row["as_of_date"]))
                weights.append(float(row.get("evidence_weight") or 0.0) or 1.0)
                if row.get("overall_adherence") is not None:
                    adherence.append(float(row["overall_adherence"]))
        sufficiency = self._sufficiency.assess_weighted(
            domain="execution_patterns",
            observation_dates=dates,
            evidence_weights=weights,
            as_of=as_of,
        )
        return {
            **counts,
            "adherence": _mean(adherence),
            "adherence_sample_count": len(adherence),
            "execution_sample_count": len(dates),
            "evidence_level": sufficiency.get("level"),
            "evidence_label": _level_label(sufficiency.get("level")),
            "sufficiency": sufficiency,
            "note": "Gjennomføring og etterlevelse er ikke fysiologisk effekt.",
        }

    def _evidence_quality(
        self,
        observations: List[Dict[str, Any]],
        utilities: Dict[int, Dict[str, Any]],
        short_sufficiency: Dict[str, Any],
    ) -> Dict[str, Any]:
        explicit = legacy = pending = incomplete = 0
        quality_scores = []
        for row in observations:
            if row.get("match_source") == "explicit_execution":
                explicit += 1
            elif row.get("match_source") == "legacy_heuristic":
                legacy += 1
            if (row.get("execution_status") or "") == "pending":
                pending += 1
            utility = utilities[row["recommendation_id"]]
            if utility.get("short_term_maturity") == INCOMPLETE_DATA:
                incomplete += 1
            if row.get("data_quality_score") is not None:
                quality_scores.append(float(row["data_quality_score"]))
        return {
            "raw_sample_count": short_sufficiency.get("sample_count"),
            "effective_sample_count": short_sufficiency.get("effective_sample_count"),
            "spread_days": short_sufficiency.get("spread_days"),
            "sufficiency_level": short_sufficiency.get("level"),
            "sufficiency_label": _level_label(short_sufficiency.get("level")),
            "data_quality_coverage": round(len(quality_scores) / len(observations), 3) if observations else None,
            "data_quality_mean": _mean(quality_scores),
            "explicit_execution_matches": explicit,
            "legacy_heuristic_matches": legacy,
            "pending_windows": pending,
            "incomplete_windows": incomplete,
            "may_override_defaults": short_sufficiency.get("may_override_defaults"),
        }

    def _insights(
        self,
        by_type: List[Dict[str, Any]],
        confidence: Dict[str, Any],
        overview: Dict[str, Any],
    ) -> tuple:
        known = []
        unknown = []
        for row in by_type:
            label = row["label"]
            n = row["mature_outcome_count"]
            level = row["evidence_level"]
            if n == 0 and row["recommendation_count"] == 0:
                continue
            if level in {"EMERGING", "SUPPORTED", "STRONG"} and n > 0:
                recovery = row["observed_recovery_response"]
                recovery_text = (
                    f" Observert restitusjonsrespons: {recovery}."
                    if recovery is not None
                    else ""
                )
                known.append(
                    {
                        "workout_type": row["workout_type"],
                        "title": label,
                        "sample_count": n,
                        "evidence_level": level,
                        "evidence_label": row["evidence_label"],
                        "conclusion_strength": row["conclusion_strength"],
                        "observed_recovery_response": recovery,
                        "observed_recovery_sample_count": row["observed_recovery_sample_count"],
                        "text": (
                            f"{label} har {n} modne korttidsutfall. "
                            f"Evidens: {row['evidence_label']}. "
                            f"Konklusjonsstyrke: {row['conclusion_strength']}.{recovery_text}"
                        ),
                    }
                )
            else:
                unknown.append(
                    {
                        "code": "insufficient_type",
                        "workout_type": row["workout_type"],
                        "sample_count": n,
                        "evidence_level": level,
                        "text": (
                            f"{label} har foreløpig {n} modne observasjoner. "
                            "Systemet beholder derfor standardreglene."
                        ),
                    }
                )
            medium_gap = _medium_unknown(row)
            if medium_gap is not None:
                unknown.append(medium_gap)
        if confidence.get("status") == "INSUFFICIENT_DATA":
            unknown.append(
                {
                    "code": "confidence_underpowered",
                    "sample_count": confidence.get("sample_count"),
                    "evidence_level": "INSUFFICIENT",
                    "text": "Confidence-kalibrering har for få modne utfall til å vurderes.",
                }
            )
        quality_rows = [row for row in by_type if row["workout_type"] in QUALITY_SESSION_TYPES]
        quality_recs = sum(row["recommendation_count"] for row in quality_rows)
        quality_feedback = sum(row["feedback_count"] for row in quality_rows)
        coverage = overview.get("feedback_coverage")
        if quality_recs and quality_feedback / quality_recs < 0.25:
            pct = round(100 * quality_feedback / quality_recs)
            unknown.append(
                {
                    "code": "low_feedback_coverage",
                    "sample_count": quality_feedback,
                    "text": f"Subjektiv feedback finnes for {pct} % av kvalitetsøktene.",
                }
            )
        elif overview["canonical_recommendation_count"] and (coverage is None or coverage < 0.25):
            pct = 0 if coverage is None else round(coverage * 100)
            unknown.append(
                {
                    "code": "low_feedback_coverage",
                    "sample_count": overview["feedback_count"],
                    "text": f"Subjektiv feedback finnes for {pct} % av de kanoniske anbefalingene.",
                }
            )
        race_rows = [row for row in by_type if row["workout_type"] in {"race", "race_pace"}]
        race_recs = sum(row["recommendation_count"] for row in race_rows)
        race_n = sum(row["mature_outcome_count"] for row in race_rows)
        if race_recs == 0:
            unknown.append(
                {
                    "code": "taper_not_personalized",
                    "sample_count": 0,
                    "evidence_level": "INSUFFICIENT",
                    "text": "Ingen konkurranseanbefalinger i vinduet, så taper er ikke personliggjort.",
                }
            )
        elif race_n < 6:
            unknown.append(
                {
                    "code": "too_few_races",
                    "sample_count": race_n,
                    "evidence_level": "INSUFFICIENT",
                    "text": f"For få modne konkurranseutfall ({race_n}) til å personliggjøre taper.",
                }
            )
        return known, unknown

    def _operations(
        self,
        *,
        start: date,
        end: date,
        abstention: Dict[str, Any],
        distribution: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        churn = RecommendationChurnMonitor().assess(self.db, day=end)
        plan = PlanChurnMonitor().assess(self.db, as_of=end, window_days=(end - start).days or 1)
        freshness = snapshot.get("freshness") or {}
        coverage = snapshot.get("source_coverage") or {}
        shadow = ShadowPromotionReadinessService().assess(self.db, start=start, end=end)
        return {
            "abstention": {
                "status": abstention.get("status"),
                "sample_count": abstention.get("sample_count"),
                "abstention_rate": abstention.get("abstention_rate"),
                "note": abstention.get("note"),
            },
            "distribution": {
                "sample_count": distribution.get("sample_count"),
                "unexpected_shift": distribution.get("unexpected_shift"),
                "types_from_zero": distribution.get("types_from_zero"),
                "note": distribution.get("note"),
            },
            "recommendation_churn": {
                "status": churn.get("status"),
                "sample_count": churn.get("sample_count"),
                "type_changes": churn.get("type_changes"),
            },
            "plan_churn": {"status": plan.get("status"), "sample_count": plan.get("sample_count")},
            "data_latency": {
                "stale_local_despite_source": freshness.get("stale_local_despite_source"),
                "last_sync_at": freshness.get("last_sync_at"),
            },
            "data_quality_trend": {
                "hrv_coverage": coverage.get("hrv"),
                "rhr_coverage": coverage.get("rhr"),
                "sleep_coverage": coverage.get("sleep"),
                "activity_count": coverage.get("activity_count"),
            },
            "shadow": {
                "status": shadow.get("status"),
                "sample_count": shadow.get("sample_count"),
                "note": shadow.get("note"),
            },
        }


def _medium_unknown(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Separate an open medium-term window from samples that lack spread."""
    label = row["label"]
    if row["medium_term_sample_count"] == 0 and row["short_term_sample_count"] > 0:
        return {
            "code": "medium_term_not_mature",
            "workout_type": row["workout_type"],
            "sample_count": 0,
            "evidence_level": "INSUFFICIENT",
            "text": f"Mellomlangs respons etter {label} er ikke moden i dette vinduet.",
        }
    spread = row.get("medium_spread_days")
    if (
        row["medium_term_sample_count"] > 0
        and row.get("medium_evidence_level") == "INSUFFICIENT"
        and spread is not None
        and spread < SampleSufficiencyPolicy.MIN_SPREAD_DAYS_FOR_FULL_CREDIT
    ):
        return {
            "code": "medium_term_spread",
            "workout_type": row["workout_type"],
            "sample_count": row["medium_term_sample_count"],
            "evidence_level": "INSUFFICIENT",
            "text": (
                f"Mellomlangs respons etter {label} mangler tilstrekkelig "
                f"tidsmessig spredning ({spread} dager)."
            ),
        }
    return None


def _pct(value: Any) -> str:
    if value is None:
        return "–"
    return f"{round(float(value) * 100)} %"


def _operations_lines(operations: Dict[str, Any]) -> List[Dict[str, str]]:
    """Short decision lines. Status codes stay on the raw operations object."""
    abstention = operations.get("abstention") or {}
    distribution = operations.get("distribution") or {}
    churn = operations.get("recommendation_churn") or {}
    plan = operations.get("plan_churn") or {}
    latency = operations.get("data_latency") or {}
    quality = operations.get("data_quality_trend") or {}
    shadow = operations.get("shadow") or {}
    if abstention.get("status") == "INSUFFICIENT_DATA":
        abstention_text = (
            f"For få observasjoner til å vurdere avståelse (N {abstention.get('sample_count')}). "
            "Avståelsesraten er ikke et mål i seg selv."
        )
    else:
        abstention_text = (
            f"Status {abstention.get('status')} "
            f"(N {abstention.get('sample_count')}, rate {_pct(abstention.get('abstention_rate'))}). "
            "Avståelsesraten er ikke et mål i seg selv."
        )
    if distribution.get("unexpected_shift"):
        distribution_text = "Fordelingen av anbefalingstyper har skiftet uventet."
    else:
        distribution_text = "Ingen uventet skift i anbefalingstypene."
    if latency.get("stale_local_despite_source"):
        latency_text = "Lokal data er eldre enn kilden."
    else:
        latency_text = "Ingen kjent forsinkelse mellom kilde og lokal data."
    shadow_status = shadow.get("status")
    shadow_label = {
        "NOT_READY": "ikke klar",
        "INSUFFICIENT_DATA": "uten nok data",
        "BLOCKED": "blokkert",
    }.get(shadow_status, shadow_status)
    if shadow_status == "ELIGIBLE":
        shadow_text = "Skyggemodellen er eligible. Det er ikke en promotering."
    else:
        shadow_text = f"Skyggemodellen er {shadow_label}. Eligible er ikke en promotering."
    return [
        {"code": "abstention", "label": "Avståelse", "text": abstention_text},
        {"code": "distribution", "label": "Anbefalingsfordeling", "text": distribution_text},
        {
            "code": "recommendation_churn",
            "label": "Anbefalingsbytte",
            "text": (
                f"Status {churn.get('status')} "
                f"(N {churn.get('sample_count')}, {churn.get('type_changes')} typeendringer)."
            ),
        },
        {
            "code": "plan_churn",
            "label": "Planendring",
            "text": f"Status {plan.get('status')} (N {plan.get('sample_count')}).",
        },
        {"code": "data_latency", "label": "Dataforsinkelse", "text": latency_text},
        {
            "code": "data_quality_trend",
            "label": "Datakvalitet",
            "text": (
                f"HRV {_pct(quality.get('hrv_coverage'))}, "
                f"hvilepuls {_pct(quality.get('rhr_coverage'))}, "
                f"søvn {_pct(quality.get('sleep_coverage'))}."
            ),
        },
        {"code": "shadow", "label": "Skygge", "text": shadow_text},
    ]


def _public_confidence(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sample_count": report.get("sample_count"),
        "brier_score": report.get("brier_score"),
        "expected_calibration_error": report.get("expected_calibration_error"),
        "bins": report.get("bins"),
        "status": report.get("status"),
        "coverage": report.get("coverage"),
        "abstention_rate": report.get("abstention_rate"),
        "level": report.get("level"),
        "favorable_outcome_definition": report.get("favorable_outcome_definition"),
        "note": report.get("note"),
    }


def _signals(observations: List[Dict[str, Any]], utilities: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    short_n = sum(
        1
        for row in observations
        if is_usable_status(utilities[row["recommendation_id"]].get("short_term_maturity"))
        and utilities[row["recommendation_id"]].get("short_term_utility") is not None
    )
    quality_n = sum(
        1 for utility in utilities.values() if utility.get("session_quality_included")
    )
    fields = {key: 0 for key in ("rpe", "session_feel", "legs", "motivation", "pain")}
    feedback_n = 0
    quality_recs = 0
    quality_feedback = 0
    for row in observations:
        feedback = row.get("subjective_feedback")
        if feedback:
            feedback_n += 1
            if isinstance(feedback, dict):
                for key in fields:
                    if feedback.get(key) is not None:
                        fields[key] += 1
        if row.get("recommended_workout_type") in QUALITY_SESSION_TYPES:
            quality_recs += 1
            if feedback:
                quality_feedback += 1
    return {
        "objective": {
            "sources": ["garmin_activity", "hrv", "rhr", "tss_epoc", "session_quality"],
            "short_term_sample_count": short_n,
            "session_quality_sample_count": quality_n,
        },
        "subjective": {
            "sources": ["rpe", "session_feel", "legs", "motivation", "pain"],
            "fields": fields,
            "sample_count": feedback_n,
            "coverage": round(feedback_n / len(observations), 3) if observations else None,
            "quality_session_count": quality_recs,
            "quality_feedback_count": quality_feedback,
            "quality_coverage": round(quality_feedback / quality_recs, 3) if quality_recs else None,
            "provenance": "athlete_feedback",
            "ground_truth": False,
            "replaces_objective_data": False,
        },
    }

