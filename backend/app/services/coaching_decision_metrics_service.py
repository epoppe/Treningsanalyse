"""Coaching-beslutningsmetrikker utover standard Garmin — brukt av trenere og AI."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database.models import HRV
from ..database.models.activity import Activity
from ..utils.activity_filters import is_running_activity

LONG_RUN_MIN_DURATION_S = 75 * 60
CONSISTENCY_WINDOW_DAYS = 28
FORM_STABILITY_WINDOW_DAYS = 30
FITNESS_GAIN_LOOKBACK_DAYS = 42

EVENT_KEYS = ("5k", "10k", "hm", "marathon")
LIMITER_KEYS = (
    "aerobic",
    "threshold",
    "vo2",
    "fatigue",
    "sleep",
    "consistency",
)

WORKOUT_TYPES = (
    "rest",
    "recovery_run",
    "easy_run",
    "long_run",
    "threshold",
    "vo2_intervals",
    "race_pace",
)


class CoachingDecisionMetricsService:
    """Beregner treningsbeslutningsmetrikker fra eksisterende aktivitets- og helsedata."""

    def __init__(self, db: Session, ppap: Any):
        self.db = db
        self._ppap = ppap

    def get_consistency_score(self, day: date, window_days: int = CONSISTENCY_WINDOW_DAYS) -> Optional[float]:
        start = day - timedelta(days=window_days - 1)
        rows = (
            self.db.query(func.date(Activity.start_time))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= day,
                )
            )
            .distinct()
            .all()
        )
        training_days = 0
        for row in rows:
            activities = (
                self.db.query(Activity)
                .filter(func.date(Activity.start_time) == row[0])
                .all()
            )
            if any(is_running_activity(a) for a in activities):
                training_days += 1
        return round(training_days / window_days * 100.0, 1)

    def get_fitness_gain_rate(self, day: date) -> Optional[float]:
        ctl_now = self._ppap.get_ctl(day)
        past = day - timedelta(days=FITNESS_GAIN_LOOKBACK_DAYS)
        ctl_past = self._ppap.get_ctl(past)
        if ctl_now is None or ctl_past is None:
            return None
        return round((float(ctl_now) - float(ctl_past)) / FITNESS_GAIN_LOOKBACK_DAYS, 2)

    def get_polarization_score(self, day: date) -> Optional[float]:
        z1 = self._ppap.get_coaching_zone_pct(day, "coaching.zone1_pct")
        z3 = self._ppap.get_coaching_zone_pct(day, "coaching.zone3_pct")
        z2 = self._ppap.get_coaching_zone_pct(day, "coaching.zone2_pct")
        if z1 is None:
            return None
        z1 = float(z1)
        z3 = float(z3 or 0)
        z2 = float(z2 or 0)
        penalty = abs(z1 - 80.0) * 0.8 + abs(z3 - 20.0) * 0.8 + max(0.0, z2 - 12.0) * 1.5
        return round(max(0.0, min(100.0, 100.0 - penalty)), 1)

    def get_training_block(self, day: date) -> Optional[str]:
        ctl_raw = self._ppap.get_ctl(day)
        atl_raw = self._ppap.get_atl(day)
        tsb_raw = self._ppap.get_tsb(day)
        if ctl_raw is None or atl_raw is None or tsb_raw is None:
            return None
        ctl = float(ctl_raw)
        atl = float(atl_raw)
        tsb = float(tsb_raw)
        ctl_past_raw = self._ppap.get_ctl(day - timedelta(days=14))
        ctl_past = float(ctl_past_raw) if ctl_past_raw is not None else ctl
        ctl_delta = ctl - ctl_past

        if tsb > 12 and atl < ctl * 0.75:
            return "recovery"
        if tsb < -20 or atl > ctl * 1.15:
            return "overload"
        if ctl_delta > 3 and tsb < 0:
            return "build"
        if ctl_delta > 1 and tsb >= -5:
            return "base"
        if tsb >= 0 and tsb <= 12 and ctl_delta <= 1:
            return "peak"
        return "maintain"

    def get_event_readiness(self, day: date, event: str) -> Optional[float]:
        total = self._ppap.get_readiness_component(day, "readiness.total_score")
        tsb = self._ppap.get_tsb(day)
        hrv_delta = self._ppap.get_hrv_delta_pct(day)
        sleep_debt = self._ppap.get_sleep_debt_hours(day, 7)
        if total is None:
            if tsb is None and hrv_delta is None and sleep_debt is None:
                return None
            score = 50.0
        else:
            score = float(total)

        if tsb is not None:
            if event in {"5k", "10k"}:
                if -5 <= tsb <= 12:
                    score += 8.0
                elif tsb < -15:
                    score -= 15.0
            elif event == "hm":
                if -8 <= tsb <= 8:
                    score += 5.0
                elif tsb < -18:
                    score -= 12.0
            else:  # marathon
                if ctl := self._ppap.get_ctl(day):
                    if float(ctl) >= 40:
                        score += 5.0
                if tsb < -25:
                    score -= 10.0

        if hrv_delta is not None and float(hrv_delta) < -12:
            score -= 8.0
        if sleep_debt is not None and float(sleep_debt) > 6:
            score -= 10.0

        durability = self.get_durability_score(day)
        if event in {"hm", "marathon"} and durability is not None:
            score = score * 0.6 + float(durability) * 0.4

        return round(max(0.0, min(100.0, score)), 1)

    def get_pb_probability(self, day: date, distance: str) -> Optional[float]:
        readiness = self.get_event_readiness(day, distance)
        if readiness is None:
            return None
        tsb = self._ppap.get_tsb(day)
        consistency = self.get_consistency_score(day)
        prob = float(readiness) * 0.55
        if tsb is not None and -3 <= float(tsb) <= 10:
            prob += 15.0
        if consistency is not None and float(consistency) >= 75:
            prob += 10.0
        if consistency is not None and float(consistency) < 55:
            prob -= 15.0
        return round(max(0.0, min(100.0, prob)), 1)

    def _long_runs(self, start: date, end: date) -> List[Activity]:
        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                    Activity.duration.isnot(None),
                    Activity.duration >= LONG_RUN_MIN_DURATION_S,
                )
            )
            .order_by(Activity.start_time.desc())
            .all()
        )
        return [a for a in activities if is_running_activity(a)]

    def compute_long_run_quality(self, activity: Activity) -> Optional[float]:
        if not is_running_activity(activity) or not activity.duration:
            return None
        if float(activity.duration) < LONG_RUN_MIN_DURATION_S:
            return None

        score = 100.0
        pace_drop = activity.pace_drop_pct
        hr_drift = activity.hr_drift_pct
        cadence_drop = activity.cadence_drop_pct
        ef_drop = activity.ef_drop_pct
        neg_split = activity.negative_split_percent

        if pace_drop is not None:
            score -= min(35.0, max(0.0, float(pace_drop)) * 2.0)
        if hr_drift is not None:
            score -= min(25.0, max(0.0, float(hr_drift)) * 1.2)
        if cadence_drop is not None:
            score -= min(15.0, max(0.0, float(cadence_drop)) * 0.8)
        if ef_drop is not None:
            score -= min(20.0, max(0.0, float(ef_drop)) * 1.5)
        if neg_split is not None and float(neg_split) < -1.0:
            score += min(8.0, abs(float(neg_split)) * 0.3)

        if activity.fatigue_resistance_score is not None:
            score = score * 0.5 + float(activity.fatigue_resistance_score) * 0.5

        return round(max(0.0, min(100.0, score)), 1)

    def get_long_run_quality_score(self, day: date) -> Optional[float]:
        runs = self._long_runs(day - timedelta(days=56), day)
        if not runs:
            return None
        scores = []
        for activity in runs[:3]:
            value = self.compute_long_run_quality(activity)
            if value is not None:
                scores.append(value)
        if not scores:
            return None
        return round(mean(scores), 1)

    def get_durability_score(self, day: date) -> Optional[float]:
        runs = self._long_runs(day - timedelta(days=90), day)
        if not runs:
            return None

        components: List[float] = []
        for activity in runs[:5]:
            if activity.fatigue_resistance_score is not None:
                components.append(float(activity.fatigue_resistance_score))
                continue
            quality = self.compute_long_run_quality(activity)
            if quality is not None:
                components.append(quality)
        if not components:
            return None
        return round(mean(components), 1)

    def compute_mechanical_efficiency(self, activity: Activity) -> Optional[float]:
        if not is_running_activity(activity):
            return None
        vo = activity.vertical_oscillation
        if vo is None or float(vo) <= 0:
            return None
        vo_m = float(vo) / 100.0
        if activity.average_speed and activity.average_speed > 0:
            return round(float(activity.average_speed) / vo_m, 2)
        power = activity.average_power or activity.normalized_power
        if power and power > 0:
            return round(float(power) / vo_m, 1)
        return None

    def get_form_stability_score(self, day: date) -> Optional[float]:
        start = day - timedelta(days=FORM_STABILITY_WINDOW_DAYS - 1)
        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= day,
                )
            )
            .all()
        )
        runs = [a for a in activities if is_running_activity(a)]
        cadences = [float(a.average_running_cadence) for a in runs if a.average_running_cadence]
        strides = [float(a.stride_length) for a in runs if a.stride_length]
        gcts = [float(a.ground_contact_time) for a in runs if a.ground_contact_time]

        def cv_penalty(values: List[float]) -> Optional[float]:
            if len(values) < 4:
                return None
            avg = mean(values)
            if avg <= 0:
                return None
            cv = pstdev(values) / avg * 100.0
            return max(0.0, min(40.0, cv * 2.0))

        penalties = [p for p in (cv_penalty(cadences), cv_penalty(strides), cv_penalty(gcts)) if p is not None]
        if not penalties:
            return None
        return round(max(0.0, min(100.0, 100.0 - mean(penalties))), 1)

    def get_hrv_resilience_score(self, day: date) -> Optional[float]:
        start = day - timedelta(days=21)
        rows = (
            self.db.query(HRV.measurement_date, HRV.rmssd)
            .filter(
                and_(
                    HRV.measurement_date >= start,
                    HRV.measurement_date <= day,
                    HRV.rmssd.isnot(None),
                )
            )
            .order_by(HRV.measurement_date)
            .all()
        )
        if len(rows) < 7:
            return None

        baseline = self._ppap.get_hrv_baseline(day)
        if baseline is None:
            baseline = mean(float(r.rmssd) for r in rows)

        recovery_speeds: List[float] = []
        i = 0
        while i < len(rows) - 2:
            if float(rows[i].rmssd) < float(baseline) * 0.9:
                j = i + 1
                while j < len(rows) and float(rows[j].rmssd) < float(baseline) * 0.95:
                    j += 1
                if j < len(rows) and j > i:
                    dip = float(baseline) - float(rows[i].rmssd)
                    recovery = float(rows[j].rmssd) - float(rows[i].rmssd)
                    days = (rows[j].measurement_date - rows[i].measurement_date).days or 1
                    if dip > 0 and recovery > 0:
                        recovery_speeds.append(recovery / dip / days)
                i = j
            else:
                i += 1

        if not recovery_speeds:
            delta = self._ppap.get_hrv_delta_pct(day)
            if delta is None:
                return None
            return round(max(0.0, min(100.0, 70.0 + float(delta) * 0.5)), 1)

        avg_speed = mean(recovery_speeds)
        return round(max(0.0, min(100.0, 50.0 + avg_speed * 80.0)), 1)

    def get_limiting_factors(self, day: date) -> Dict[str, float]:
        scores: Dict[str, float] = {}

        hrv_delta = self._ppap.get_hrv_delta_pct(day)
        if hrv_delta is not None and float(hrv_delta) < 0:
            scores["aerobic"] = min(100.0, abs(float(hrv_delta)) * 2.5)

        sleep = self._ppap.get_readiness_component(day, "readiness.sleep_component")
        if sleep is not None and float(sleep) < 65:
            scores["sleep"] = min(100.0, (65.0 - float(sleep)) * 1.8)

        tsb = self._ppap.get_tsb(day)
        if tsb is not None and float(tsb) < -8:
            scores["fatigue"] = min(100.0, abs(float(tsb)) * 2.0)

        z2 = self._ppap.get_coaching_zone_pct(day, "coaching.zone2_pct")
        if z2 is not None and float(z2) > 18:
            scores["threshold"] = min(100.0, (float(z2) - 15.0) * 4.0)

        z3 = self._ppap.get_coaching_zone_pct(day, "coaching.zone3_pct")
        z1 = self._ppap.get_coaching_zone_pct(day, "coaching.zone1_pct")
        if z3 is not None and z1 is not None and float(z3) > 25 and float(z1) < 70:
            scores["vo2"] = min(100.0, (float(z3) - 20.0) * 3.0)

        consistency = self.get_consistency_score(day)
        if consistency is not None and float(consistency) < 65:
            scores["consistency"] = min(100.0, (65.0 - float(consistency)) * 1.5)

        if not scores:
            return {}
        return {key: round(value, 1) for key, value in scores.items()}

    def get_limiter_score(self, day: date, limiter: str) -> Optional[float]:
        return self.get_limiting_factors(day).get(limiter)

    def get_recommended_workout(self, day: date) -> Optional[str]:
        total = self._ppap.get_readiness_component(day, "readiness.total_score")
        tsb = self._ppap.get_tsb(day)
        ctl = self._ppap.get_ctl(day)
        atl = self._ppap.get_atl(day)
        acwr = (float(atl) / float(ctl)) if ctl and atl and float(ctl) > 0 else None

        if total is not None and float(total) < 35:
            return "rest"
        if tsb is not None and float(tsb) < -25:
            return "recovery_run"
        if acwr is not None and float(acwr) > 1.4:
            return "easy_run"

        block = self.get_training_block(day)
        if block == "recovery":
            return "recovery_run"
        if block == "overload":
            return "easy_run"

        if total is not None and float(total) >= 75 and tsb is not None and 0 <= float(tsb) <= 12:
            return "vo2_intervals"
        if total is not None and float(total) >= 65 and tsb is not None and -8 <= float(tsb) <= 5:
            return "threshold"

        consistency = self.get_consistency_score(day)
        if consistency is not None and float(consistency) < 55:
            return "easy_run"

        return "easy_run"

    def get_fueling_score(self, day: date) -> Optional[float]:
        """Placeholder — krever ernæringsdata som ikke finnes i dag."""
        return None

    def get_recovery_model_accuracy(self, day: date) -> Optional[float]:
        """Placeholder — krever historisk validering mot faktisk prestasjon."""
        return None

    def build_coaching_snapshot(self, day: Optional[date] = None) -> Dict[str, Any]:
        day = day or date.today()
        limiters = self.get_limiting_factors(day)
        top_limiter = max(limiters, key=limiters.get) if limiters else None

        return {
            "date": day.isoformat(),
            "consistency": {
                "score": self.get_consistency_score(day),
                "interpretation": "85+ svært bra, 70–85 bra, <60 inkonsistent",
            },
            "fitness": {
                "gain_rate_ctl_per_day": self.get_fitness_gain_rate(day),
                "ctl": self._ppap.get_ctl(day),
            },
            "long_run": {
                "quality_score": self.get_long_run_quality_score(day),
                "durability_score": self.get_durability_score(day),
            },
            "readiness_by_event": {
                event: self.get_event_readiness(day, event) for event in EVENT_KEYS
            },
            "pb_probability": {
                event: self.get_pb_probability(day, event) for event in EVENT_KEYS
            },
            "polarization_score": self.get_polarization_score(day),
            "training_block": self.get_training_block(day),
            "biomechanics": {
                "form_stability": self.get_form_stability_score(day),
            },
            "recovery": {
                "hrv_resilience": self.get_hrv_resilience_score(day),
                "fueling_score": self.get_fueling_score(day),
                "model_accuracy": self.get_recovery_model_accuracy(day),
            },
            "limiting_factors": limiters,
            "top_limiter": top_limiter,
            "recommended_workout": self.get_recommended_workout(day),
            "data_gaps": [
                "fueling_score krever karbohydrat-/ernæringsregistrering",
                "recovery_model_accuracy krever historisk validering",
                "race_execution_score krever planlagt konkurransedata",
            ],
        }
