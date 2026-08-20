"""Kanonisk oversettelse av fysiologisk intensitet til HR/pace/power/RPE.

Threshold knyttes til LT2 / critical speed — ikke en prosent rundt LT1.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .adaptive_threshold_service import AdaptiveThresholdService
from .ppap_metrics_service import PpapMetricsService

# HR-andeler. Easy/recovery er LT1-forankret; threshold/VO2 er LT2-forankret.
ZONE_HR_LT1: Dict[str, Tuple[float, float]] = {
    "recovery": (0.72, 0.82),
    "easy": (0.82, 0.94),
    "strides": (0.88, 0.98),
}
ZONE_HR_LT2: Dict[str, Tuple[float, float]] = {
    "steady": (0.88, 0.94),
    "threshold": (0.94, 1.00),
    "race_pace": (0.92, 0.98),
    "vo2": (1.02, 1.08),
}
ZONE_PACE_LT1: Dict[str, Tuple[float, float]] = {
    "recovery": (1.18, 1.30),
    "easy": (1.08, 1.18),
}
ZONE_PACE_LT2: Dict[str, Tuple[float, float]] = {
    "steady": (1.06, 1.12),
    "threshold": (1.00, 1.04),
    "race_pace": (1.02, 1.08),
    "vo2": (0.92, 0.98),
}
ZONE_RPE: Dict[str, List[int]] = {
    "recovery": [2, 3],
    "easy": [3, 4],
    "steady": [5, 6],
    "threshold": [7, 8],
    "vo2": [8, 9],
    "race_pace": [7, 8],
    "strides": [6, 7],
}

WORKOUT_TO_ZONE = {
    "rest": None,
    "recovery_run": "recovery",
    "easy_run": "easy",
    "long_run": "easy",
    "long_aerobic": "easy",
    "steady": "steady",
    "threshold": "threshold",
    "vo2_intervals": "vo2",
    "race_pace": "race_pace",
    "strides": "strides",
}


class IntensityPrescriptionService:
    """Én kilde for intensitetssoner — andre services skal delegere hit."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._thresholds = AdaptiveThresholdService(db, storage)

    def prescribe(
        self,
        zone_or_workout: str,
        *,
        end_date: Optional[date] = None,
        include_treadmill: bool = False,
        environment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        day = end_date or date.today()
        zone = WORKOUT_TO_ZONE.get(zone_or_workout, zone_or_workout)
        if zone is None:
            return {
                "zone": "rest",
                "hr_bpm": None,
                "pace_sec_km": None,
                "speed_mps": None,
                "power_w": None,
                "rpe": None,
                "source": "rest",
                "confidence": 1.0,
                "limitations": [],
            }

        lt1 = self._thresholds.estimate_lt1(end_date=day, include_treadmill=include_treadmill)
        lt2 = self._thresholds.latest_lt2(day)
        cs, _dprime = self._ppap.get_critical_speed_snapshot(day)
        cp, _wprime = self._ppap.get_critical_power_snapshot(day)

        hr, hr_source, hr_conf = self._hr_range(zone, lt1, lt2)
        pace, speed, pace_source, pace_conf = self._pace_range(zone, lt1, lt2, cs)
        power = self._power_range(zone, cp)
        rpe = ZONE_RPE.get(zone)

        limitations: List[str] = []
        if lt2.get("stale"):
            limitations.append("stale_lt2")
        if lt1.get("fallback_used"):
            limitations.append("lt1_multiplier_fallback")
        if pace is None:
            limitations.append("missing_pace_data")
        if hr is None:
            limitations.append("missing_hr_anchors")

        source = pace_source or hr_source or "rpe_fallback"
        confidence = min(hr_conf, pace_conf if pace is not None else hr_conf)
        if source == "rpe_fallback":
            confidence = min(confidence, 0.35)

        env_adj = self._environment_pace_adjustment(pace, environment)
        if env_adj.get("weak_weather"):
            limitations.append("weak_weather_data")

        return {
            "zone": zone,
            "hr_bpm": hr,
            "pace_sec_km": pace,
            "nominal_pace": pace,
            "environment_adjusted_pace": env_adj.get("adjusted_pace"),
            "adjustment_reason": env_adj.get("reason"),
            "speed_mps": speed,
            "power_w": power,
            "rpe": rpe,
            "source": source,
            "confidence": round(confidence, 2),
            "lt1": {"hr": lt1.get("lt1_hr"), "confidence": lt1.get("confidence")},
            "lt2": {
                "hr": lt2.get("lt2_hr"),
                "stale": lt2.get("stale"),
                "freshness_days": lt2.get("freshness_days"),
                "confidence": lt2.get("confidence"),
            },
            "limitations": limitations,
            "missing_evidence": env_adj.get("missing_evidence") or [],
        }

    def _hr_range(
        self,
        zone: str,
        lt1: Dict[str, Any],
        lt2: Dict[str, Any],
    ) -> Tuple[Optional[List[int]], str, float]:
        lt1_hr = lt1.get("lt1_hr")
        lt2_hr = lt2.get("lt2_hr")
        if zone in ZONE_HR_LT2 and lt2_hr:
            lo, hi = ZONE_HR_LT2[zone]
            conf = float(lt2.get("confidence") or 0.4)
            if lt2.get("stale"):
                conf = min(conf, 0.4)
            return [int(float(lt2_hr) * lo), int(float(lt2_hr) * hi)], "adaptive_lt2", conf
        if zone in ZONE_HR_LT1 and lt1_hr:
            lo, hi = ZONE_HR_LT1[zone]
            return (
                [int(float(lt1_hr) * lo), int(float(lt1_hr) * hi)],
                "adaptive_lt1",
                float(lt1.get("confidence") or 0.4),
            )
        if zone in ZONE_HR_LT2 and lt1_hr:
            # Ikke bruk LT1±5% som threshold. Grovere: LT1 * 1.10–1.18 som siste HR-fallback.
            return (
                [int(float(lt1_hr) * 1.10), int(float(lt1_hr) * 1.18)],
                "lt1_hr_fallback_not_lt2",
                0.3,
            )
        return None, "rpe_fallback", 0.25

    def _pace_range(
        self,
        zone: str,
        lt1: Dict[str, Any],
        lt2: Dict[str, Any],
        cs: Optional[float],
    ) -> Tuple[Optional[List[int]], Optional[List[float]], str, float]:
        lt2_speed = lt2.get("lt2_speed_mps")
        lt1_speed = lt1.get("lt1_speed_mps")
        if lt2.get("stale"):
            lt2_speed = None
        if lt1.get("confidence", 0) < 0.45:
            lt1_speed = None

        if zone in {"threshold", "race_pace", "vo2", "steady"} and cs and float(cs) > 0:
            factor = {"threshold": (0.96, 1.00), "race_pace": (0.90, 0.96), "vo2": (1.03, 1.10), "steady": (0.88, 0.94)}[zone]
            speeds = [float(cs) * factor[0], float(cs) * factor[1]]
            paces = [int(1000 / s) for s in reversed(speeds) if s > 0]
            return paces, [round(s, 3) for s in speeds], "critical_speed", 0.7

        if zone in ZONE_PACE_LT2 and lt2_speed and float(lt2_speed) > 0:
            lo, hi = ZONE_PACE_LT2[zone]
            speeds = [float(lt2_speed) / hi, float(lt2_speed) / lo]
            paces = [int(1000 / s) for s in reversed(speeds)]
            return paces, [round(s, 3) for s in speeds], "adaptive_lt2", float(lt2.get("confidence") or 0.5)

        if zone in ZONE_PACE_LT1 and lt1_speed and float(lt1_speed) > 0:
            lo, hi = ZONE_PACE_LT1[zone]
            speeds = [float(lt1_speed) / hi, float(lt1_speed) / lo]
            paces = [int(1000 / s) for s in reversed(speeds)]
            return paces, [round(s, 3) for s in speeds], "adaptive_lt1", float(lt1.get("confidence") or 0.5)

        return None, None, "rpe_fallback", 0.25

    @staticmethod
    def _environment_pace_adjustment(
        nominal_pace: Optional[List[int]],
        environment: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Slow pace targets for heat/humidity/wind/hills; do not over-adjust on weak data."""
        if nominal_pace is None:
            return {
                "adjusted_pace": None,
                "reason": None,
                "weak_weather": False,
                "missing_evidence": ["nominal_pace"],
            }
        if not environment:
            return {
                "adjusted_pace": list(nominal_pace),
                "reason": "no_environment_data",
                "weak_weather": True,
                "missing_evidence": ["temperature", "humidity", "wind", "elevation"],
            }
        temp = environment.get("temperature_c")
        humidity = environment.get("humidity_pct")
        wind = environment.get("wind_mps")
        grade = environment.get("elevation_gain_m_per_km")
        present = [x for x in (temp, humidity, wind, grade) if x is not None]
        if len(present) < 1:
            return {
                "adjusted_pace": list(nominal_pace),
                "reason": "weak_weather_data",
                "weak_weather": True,
                "missing_evidence": ["temperature", "humidity", "wind", "elevation"],
            }
        factor = 1.0
        reasons = []
        if temp is not None and float(temp) >= 22:
            factor += min(0.08, (float(temp) - 20) * 0.008)
            reasons.append("heat")
        if humidity is not None and float(humidity) >= 70 and temp is not None and float(temp) >= 18:
            factor += 0.02
            reasons.append("humidity")
        if wind is not None and float(wind) >= 8:
            factor += 0.02
            reasons.append("wind")
        if grade is not None and float(grade) >= 15:
            factor += min(0.06, float(grade) / 400.0)
            reasons.append("hilly")
        adjusted = [int(p * factor) for p in nominal_pace]
        return {
            "adjusted_pace": adjusted,
            "reason": ",".join(reasons) or "neutral",
            "weak_weather": len(present) < 2,
            "missing_evidence": [
                k
                for k, v in {
                    "temperature": temp,
                    "humidity": humidity,
                    "wind": wind,
                    "elevation": grade,
                }.items()
                if v is None
            ],
        }

    @staticmethod
    def _power_range(zone: str, cp: Optional[float]) -> Optional[List[int]]:
        if cp is None or float(cp) <= 0:
            return None
        factors = {
            "recovery": (0.55, 0.70),
            "easy": (0.65, 0.80),
            "steady": (0.85, 0.92),
            "threshold": (0.95, 1.02),
            "vo2": (1.05, 1.20),
            "race_pace": (0.92, 1.00),
            "strides": (1.10, 1.30),
        }.get(zone)
        if not factors:
            return None
        return [int(float(cp) * factors[0]), int(float(cp) * factors[1])]
