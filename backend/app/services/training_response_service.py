"""Analyserer historisk sammenheng mellom treningsbelastning og senere utfall — uten kausalitet."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .adaptive_threshold_service import AdaptiveThresholdService
from .coaching_analysis_service import CoachingAnalysisService
from .mcp_derived_metrics_service import McpDerivedMetricsService
from .ppap_metrics_service import PpapMetricsService
from .statistical_uncertainty import bootstrap_ci, evidence_band
from .temporal_metric_contract import (
    aggregation_window_days,
    contract_for,
    resolve_stimulus,
    sample_overlap,
    stimulus_bounds,
    stimulus_producer_family,
)

DEFAULT_LAG_WINDOWS = (7, 14, 21, 28)
# Aggregation length is owned by metric metadata (STIMULUS_AGGREGATION_DAYS).
# Lag is a separate offset: the stimulus window ends `lag` days before the outcome.
MIN_EFFECT_FOR_RANKING = 0.25
MIN_N_FOR_RANKING = 12

STIMULUS_METRICS = (
    "easy_volume",
    "threshold_volume",
    "high_intensity_volume",
    "weekly_tss",
)

def _stimulus_kind(stimulus: str) -> str:
    contract = resolve_stimulus(stimulus)
    if contract is not None and contract.dependencies:
        return str(contract.dependencies[0])
    return stimulus


def residualize_outcomes(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Residual of outcome after time, season, and baseline CTL.

    Descriptive adjustment so dose buckets are not raw means along a time trend.
    Not a causal training effect.
    """
    import numpy as np

    outcomes = [float(row["outcome"]) for row in rows]
    empty = {
        "residuals": outcomes,
        "covariates": [],
        "controls_time": False,
        "controls_season": False,
        "controls_baseline_fitness": False,
        "fully_controlled": False,
    }
    n = len(rows)
    if n < 8:
        return empty
    ctl_present = [row.get("ctl") for row in rows if row.get("ctl") is not None]
    use_ctl = len(ctl_present) / n >= 0.7
    use_season = n >= 16
    ctl_fill = float(sorted(ctl_present)[len(ctl_present) // 2]) if ctl_present else 0.0
    origin = min(row["date"] for row in rows)
    columns: List[List[float]] = []
    names: List[str] = ["intercept", "time_index"]
    for row in rows:
        time_index = float((row["date"] - origin).days)
        cols = [1.0, time_index]
        if use_ctl:
            ctl = row.get("ctl")
            cols.append(float(ctl) if ctl is not None else ctl_fill)
        if use_season:
            angle = 2.0 * math.pi * (row["date"].timetuple().tm_yday / 365.25)
            cols.extend([math.sin(angle), math.cos(angle)])
        columns.append(cols)
    if use_ctl:
        names.append("baseline_ctl")
    if use_season:
        names.extend(["season_sin", "season_cos"])
    design = np.asarray(columns, dtype=float)
    target = np.asarray(outcomes, dtype=float)
    try:
        coef, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
    except np.linalg.LinAlgError:
        return empty
    if int(rank) < design.shape[1]:
        return empty
    fitted = design @ coef
    residuals = (target - fitted).tolist()
    return {
        "residuals": [float(value) for value in residuals],
        "covariates": names,
        "controls_time": True,
        "controls_season": use_season,
        "controls_baseline_fitness": use_ctl,
        "fully_controlled": use_ctl and use_season,
    }


OUTCOME_CONTRACT_KEYS = {
    "easy_efficiency": "fitness.ef_30d",
    "critical_speed": "running.critical_speed",
    "threshold_pace": "performance.threshold_pace",
    "vo2max": "performance.vo2max",
    "hrv": "cardio.hrv_7d",
    "resting_hr": "cardio.rhr_7d",
    "durability": "running.durability_score",
}


OUTCOME_METRICS = {
    "easy_efficiency": "fitness.ef_30d",
    "critical_speed": "running.critical_speed",
    "threshold_pace": "__threshold_pace__",
    "vo2max": "__vo2max__",
    "hrv": "cardio.hrv_7d",
    "resting_hr": "cardio.rhr_7d",
    "durability": "__durability__",
}


class TrainingResponseService:
    """Konservativ analyse av load→response med LT1/LT2-soner og eksplisitte begrensninger."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._derived = McpDerivedMetricsService(db, storage)
        self._coaching = CoachingAnalysisService(db, storage)
        self._thresholds = AdaptiveThresholdService(db, storage)

    def analyze_responses(
        self,
        *,
        end_date: Optional[date] = None,
        lookback_days: int = 365,
        lag_windows: Tuple[int, ...] = DEFAULT_LAG_WINDOWS,
        training_context=None,
    ) -> Dict[str, Any]:
        from .as_of_training_context import resolve_history_end

        end = resolve_history_end(end_date, training_context=training_context)
        start = end - timedelta(days=lookback_days)
        if training_context is not None and hasattr(training_context, "train_start"):
            start = max(start, training_context.train_start)
        # Conservative family size for stimulus × outcome × lag search.
        family_size = max(1, len(STIMULUS_METRICS) * len(OUTCOME_METRICS) * len(lag_windows))
        relationships: List[Dict[str, Any]] = []

        for stimulus_key in STIMULUS_METRICS:
            for outcome_key in OUTCOME_METRICS:
                best = self._best_lag_relationship(
                    stimulus_key,
                    outcome_key,
                    start,
                    end,
                    lag_windows,
                    family_size=family_size,
                )
                if best is not None:
                    relationships.append(best)

        # Only moderate/strong statistical support may influence ranking.
        ranking_eligible = [
            r for r in relationships if r.get("statistical_support") in {"moderate", "strong"}
        ]
        return {
            "end_date": end.isoformat(),
            "lookback_days": lookback_days,
            "relationships": relationships,
            "ranking_eligible_relationships": ranking_eligible,
            "multiple_testing": {
                "family_size": family_size,
                "method": "bonferroni_effect_threshold",
                "min_effect_for_ranking": MIN_EFFECT_FOR_RANKING,
                "min_n_for_ranking": MIN_N_FOR_RANKING,
            },
            "training_context_applied": training_context is not None,
            "disclaimer": "Correlations describe historical co-movement — not causal training effects.",
        }

    def analyze_dose_response(
        self,
        *,
        stimulus: str = "threshold_volume",
        outcome: str = "threshold_pace",
        end_date: Optional[date] = None,
        lookback_days: int = 365,
        lag_days: int = 21,
    ) -> Dict[str, Any]:
        """Observational dose buckets. Ikke kalt optimal dose."""
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)
        rows: List[Dict[str, Any]] = []
        window_days = aggregation_window_days(stimulus)
        self._ppap.prime_load_series(start, end)
        current = start + timedelta(days=lag_days + window_days - 1)
        while current <= end:
            bounds = stimulus_bounds(current, lag_days, aggregation_days=window_days)
            stim = self._stimulus_value(stimulus, bounds["stimulus_start"], bounds["stimulus_end"])
            out = self._outcome_value(outcome, current)
            if stim is not None and out is not None:
                ctl = self._ppap.get_ctl(bounds["stimulus_end"])
                rows.append(
                    {
                        "stimulus": float(stim),
                        "outcome": float(out),
                        "date": current,
                        "ctl": None if ctl is None else float(ctl),
                    }
                )
            current += timedelta(days=7)

        adjustment = residualize_outcomes(rows)
        if len(rows) < 6:
            return {
                "stimulus": stimulus,
                "response": outcome,
                "dose_response": [],
                "best_supported_historical_range": None,
                "confidence": 0.0,
                "sample_count": len(rows),
                "adjustment": adjustment,
                "disclaimer": "observational_association_not_causal_not_optimal",
            }

        xs = sorted(row["stimulus"] for row in rows)
        t1 = xs[len(xs) // 3]
        t2 = xs[(2 * len(xs)) // 3]
        buckets = [
            {"range": [0, round(t1, 1)], "residuals": [], "raw": []},
            {"range": [round(t1, 1), round(t2, 1)], "residuals": [], "raw": []},
            {"range": [round(t2, 1), round(xs[-1], 1)], "residuals": [], "raw": []},
        ]
        outcome_contract = contract_for(OUTCOME_CONTRACT_KEYS.get(outcome, ""))
        invert = bool(outcome_contract and outcome_contract.direction == "lower_is_better")
        for row, residual in zip(rows, adjustment["residuals"]):
            stim = row["stimulus"]
            if stim <= t1:
                slot = buckets[0]
            elif stim <= t2:
                slot = buckets[1]
            else:
                slot = buckets[2]
            slot["residuals"].append(float(residual))
            slot["raw"].append(row["outcome"])

        dose_response = []
        best_idx = None
        best_score = None
        for idx, bucket in enumerate(buckets):
            vals = bucket["residuals"]
            raw_vals = bucket["raw"]
            mean_v = sum(vals) / len(vals) if vals else None
            raw_mean = sum(raw_vals) / len(raw_vals) if raw_vals else None
            score = (-mean_v if invert else mean_v) if mean_v is not None else None
            dose_response.append(
                {
                    "range": bucket["range"],
                    "effect": round(mean_v, 3) if mean_v is not None else None,
                    "raw_effect": round(raw_mean, 3) if raw_mean is not None else None,
                    "sample_count": len(vals),
                    "label": ("low", "moderate", "high")[idx],
                }
            )
            if (
                adjustment["fully_controlled"]
                and score is not None
                and (best_score is None or score > best_score)
                and len(vals) >= 3
            ):
                best_score = score
                best_idx = idx

        best_range = dose_response[best_idx]["range"] if best_idx is not None else None
        conf = min(0.75, 0.2 + 0.02 * len(rows))
        if best_range is None:
            conf = min(conf, 0.3)
        effects = [b["effect"] for b in dose_response if b.get("effect") is not None]
        unc = bootstrap_ci(effects) if effects else {"estimate": None, "ci95": None, "sample_count": 0}
        support = evidence_band(sample_count=len(rows), effect_size=0.2 if best_range else 0.0)
        return {
            "stimulus": stimulus,
            "canonical_stimulus": resolve_stimulus(stimulus).key if resolve_stimulus(stimulus) else None,
            "response": outcome,
            "lag_days": lag_days,
            "dose_response": dose_response,
            "best_supported_historical_range": best_range,
            "confidence": round(conf, 2),
            "evidence_strength": round(conf, 2),
            "statistical_support": support,
            "uncertainty": unc,
            "sample_count": len(rows),
            "adjustment": {
                "method": "ols_residual" if adjustment["controls_time"] else "raw_mean",
                "covariates": [name for name in adjustment["covariates"] if name != "intercept"],
                "controls_time": adjustment["controls_time"],
                "controls_season": adjustment["controls_season"],
                "controls_baseline_fitness": adjustment["controls_baseline_fitness"],
                "fully_controlled": adjustment["fully_controlled"],
                "note": (
                    "Bucket effect is the mean residual after the listed covariates. "
                    "A historical range is reported only when time, season, and baseline CTL are all controlled."
                ),
            },
            "disclaimer": "observational_association_not_causal — not an optimal_range",
        }

    def _best_lag_relationship(
        self,
        stimulus: str,
        outcome: str,
        start: date,
        end: date,
        lag_windows: Tuple[int, ...],
        *,
        family_size: int = 1,
        aggregation_days: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for lag in lag_windows:
            result = self._correlate(
                stimulus,
                outcome,
                start,
                end,
                lag,
                family_size=family_size,
                aggregation_days=aggregation_days,
            )
            if result is not None:
                candidates.append(result)
        if not candidates:
            return None
        # Stability across lags: same sign and |effect| above ranking floor.
        stable_folds = 0
        signs = [1 if c["effect_size"] > 0 else -1 for c in candidates if abs(c["effect_size"]) >= 0.15]
        if signs and all(s == signs[0] for s in signs):
            stable_folds = sum(
                1 for c in candidates if abs(c["effect_size"]) >= MIN_EFFECT_FOR_RANKING
            )
        best = max(candidates, key=lambda c: c["evidence_strength"])
        best["stable_folds"] = stable_folds
        best["statistical_support"] = evidence_band(
            sample_count=best["sample_count"],
            effect_size=best["effect_size"],
            min_n=MIN_N_FOR_RANKING,
            min_effect=MIN_EFFECT_FOR_RANKING,
            stable_folds=stable_folds,
        )
        best["ranking_eligible"] = best["statistical_support"] in {"moderate", "strong"}
        return best

    def _correlate(
        self,
        stimulus: str,
        outcome: str,
        start: date,
        end: date,
        lag_days: int,
        *,
        family_size: int = 1,
        aggregation_days: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        window_days = aggregation_window_days(stimulus, aggregation_days)
        pairs: List[Tuple[float, float]] = []
        pair_dates: List[date] = []
        current = start + timedelta(days=lag_days + window_days - 1)
        while current <= end:
            bounds = stimulus_bounds(current, lag_days, aggregation_days=window_days)
            stimulus_val = self._stimulus_value(
                stimulus,
                bounds["stimulus_start"],
                bounds["stimulus_end"],
            )
            outcome_val = self._outcome_value(outcome, current)
            if stimulus_val is not None and outcome_val is not None:
                pairs.append((stimulus_val, outcome_val))
                pair_dates.append(current)
            current += timedelta(days=7)

        if len(pairs) < 5:
            return None

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        r = _pearson(xs, ys)
        if r is None or math.isnan(r):
            return None
        detrended = _first_difference_correlation(xs, ys)
        overlap = sample_overlap(len(pairs), aggregation_days=window_days, step_days=7)
        sign_conflict = (
            detrended is not None
            and abs(r) >= 0.2
            and abs(detrended) >= 0.15
            and (r > 0) != (detrended > 0)
        )

        effect_size = round(r, 3)
        if abs(r) < 0.15:
            relationship = "uncertain"
        elif r > 0:
            relationship = "positive"
        else:
            relationship = "negative"

        # Bonferroni-style: raise effective |r| bar with family size.
        adjusted_min = MIN_EFFECT_FOR_RANKING * (1.0 + math.log10(max(1, family_size)) * 0.15)
        raw_conf = min(0.9, abs(r) * confidence_from_samples(len(pairs)))
        if abs(r) < adjusted_min:
            raw_conf = min(raw_conf, 0.35)
        evidence_strength = round(raw_conf, 2)
        support = evidence_band(
            sample_count=int(overlap["effective_pairs"]),
            effect_size=effect_size,
            min_n=MIN_N_FOR_RANKING,
            min_effect=adjusted_min,
        )
        limitations = [
            "observational_correlation_not_causation",
            "confounding_by_other_training_not_controlled",
            "multiple_testing_across_stimulus_outcome_lag",
            "overlapping_windows_effective_n_is_conservative",
        ]
        if sign_conflict:
            support = "weak"
            relationship = "uncertain"
            limitations.append("raw_and_detrended_sign_conflict")
        example = stimulus_bounds(
            pair_dates[-1] if pair_dates else end,
            lag_days,
            aggregation_days=window_days,
        )

        return {
            "stimulus": stimulus,
            "outcome": outcome,
            "lag_days": lag_days,
            "aggregation_days": window_days,
            "stimulus_start": example["stimulus_start"].isoformat(),
            "stimulus_end": example["stimulus_end"].isoformat(),
            "outcome_date": example["outcome_date"],
            "relationship": relationship,
            "effect_size": effect_size,
            "raw_correlation": effect_size,
            "detrended_correlation": round(detrended, 3) if detrended is not None else None,
            "confidence": evidence_strength,  # compatibility alias
            "evidence_strength": evidence_strength,
            "decision_confidence": None,
            "statistical_support": support,
            "ranking_eligible": support in {"moderate", "strong"} and not sign_conflict,
            "multiple_testing_adjusted_min_effect": round(adjusted_min, 3),
            "sample_count": len(pairs),
            "raw_pairs": overlap["raw_pairs"],
            "effective_pairs": overlap["effective_pairs"],
            "sample_overlap": overlap["sample_overlap"],
            "causal": False,
            "limitations": limitations,
        }

    def _stimulus_value(self, stimulus: str, start: date, end: date) -> Optional[float]:
        family = stimulus_producer_family(stimulus)
        kind = _stimulus_kind(stimulus)
        if family == "tss_sum":
            return self._weekly_tss_sum(start, end)
        if family == "long_aerobic":
            return self._session_type_minutes(start, end, {"long_aerobic"})
        if family == "vo2_intervals":
            return self._session_type_minutes(start, end, {"vo2_intervals"})

        zone_key = {
            "zone_low": "low",
            "zone_threshold": "threshold",
            "zone_high": "high",
        }.get(family)
        if zone_key is None:
            return None

        lt1, lt2 = self._threshold_hr_bounds(end)
        if lt1 is None or lt2 is None:
            return self._fallback_stimulus_minutes(kind, start, end)

        zone_seconds = self._zone_seconds_in_window(start, end, lt1, lt2)
        seconds = zone_seconds.get(zone_key, 0.0)
        return round(seconds / 60.0, 1) if seconds > 0 else None

    def _threshold_hr_bounds(self, end: date) -> Tuple[Optional[float], Optional[float]]:
        adaptive = self._thresholds.estimate_lt1(end_date=end)
        history = self._coaching._latest_threshold_history(end)
        lt2 = history.lactate_threshold_heart_rate if history else None
        lt1 = adaptive.get("lt1_hr")
        return (float(lt1) if lt1 else None, float(lt2) if lt2 else None)

    def _zone_seconds_in_window(
        self,
        start: date,
        end: date,
        lt1: float,
        lt2: float,
    ) -> Dict[str, float]:
        totals = {"low": 0.0, "threshold": 0.0, "high": 0.0}
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity):
                continue
            buckets, _method = self._coaching.get_activity_intensity_buckets(activity, lt1, lt2)
            for key in totals:
                totals[key] += float(buckets.get(key, 0.0))
        return totals

    def _weekly_tss_sum(self, start: date, end: date) -> Optional[float]:
        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        total = 0.0
        for activity in activities:
            if not is_running_activity(activity):
                continue
            tss = activity.training_stress_score or activity.epoc
            if tss:
                total += float(tss)
        return round(total, 1) if total > 0 else None

    def _session_type_minutes(
        self,
        start: date,
        end: date,
        session_types: set,
    ) -> Optional[float]:
        """Minutes of canonical session types with activity date in [start, end]."""
        from .session_classifier_service import SessionClassifierService

        classifier = SessionClassifierService(self.db, self.storage, self._coaching)
        lt1, lt2 = self._threshold_hr_bounds(end)
        total_min = 0.0
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity) or not activity.duration or activity.start_time is None:
                continue
            if activity.start_time.date() > end:
                continue
            classification = classifier.classify_activity(
                activity,
                end_date=end,
                lt1_hr=lt1,
                lt2_hr=lt2,
            )
            if classification.get("session_type") in session_types:
                total_min += float(activity.duration) / 60.0
        return round(total_min, 1) if total_min > 0 else None

    def _fallback_stimulus_minutes(self, stimulus: str, start: date, end: date) -> Optional[float]:
        """Fallback når LT1/LT2 mangler — bruk session classifier som grov proxy."""
        from .session_classifier_service import SessionClassifierService

        classifier = SessionClassifierService(self.db, self.storage, self._coaching)
        total_min = 0.0
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        proxy_map = {
            "easy_volume": {"recovery_run", "easy_aerobic", "long_aerobic"},
            "threshold_volume": {"steady", "tempo", "threshold"},
            "high_intensity_volume": {"vo2_intervals", "anaerobic", "race"},
        }
        allowed = proxy_map.get(stimulus, set())
        for activity in activities:
            if not is_running_activity(activity) or not activity.duration:
                continue
            classification = classifier.classify_activity(activity, end_date=end)
            if classification.get("session_type") in allowed:
                total_min += float(activity.duration) / 60.0
        return round(total_min, 1) if total_min > 0 else None

    def _outcome_value(self, outcome: str, day: date) -> Optional[float]:
        if outcome == "durability":
            from .coaching_decision_metrics_service import CoachingDecisionMetricsService

            return CoachingDecisionMetricsService(self.db, self._ppap).get_durability_score(day)
        if outcome == "vo2max":
            from ..database.models.activity import GarminPerformanceMetric

            row = (
                self.db.query(GarminPerformanceMetric.vo2_max_precise)
                .filter(func.date(GarminPerformanceMetric.date) <= day)
                .order_by(GarminPerformanceMetric.date.desc())
                .first()
            )
            return float(row[0]) if row and row[0] is not None else None
        if outcome == "threshold_pace":
            history = self._coaching._latest_threshold_history(day)
            if history and history.lactate_threshold_speed and history.lactate_threshold_speed > 0:
                return 1000.0 / float(history.lactate_threshold_speed)
            return None

        metric_key = OUTCOME_METRICS.get(outcome)
        if not metric_key or metric_key.startswith("__"):
            return None
        value = self._derived._daily_metric_value(metric_key, day)
        return float(value) if value is not None else None


def _first_difference_correlation(xs: List[float], ys: List[float]) -> Optional[float]:
    """Correlation of successive changes. Reduces shared-trend spurious association."""
    if len(xs) < 4 or len(xs) != len(ys):
        return None
    dx = [xs[i] - xs[i - 1] for i in range(1, len(xs))]
    dy = [ys[i] - ys[i - 1] for i in range(1, len(ys))]
    return _pearson(dx, dy)


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def confidence_from_samples(n: int) -> float:
    if n < 5:
        return 0.3
    if n < 10:
        return 0.5
    if n < 20:
        return 0.7
    return 0.85
