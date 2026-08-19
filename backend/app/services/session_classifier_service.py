"""Klassifiserer løpeøkter etter treningsformål basert på HR, tempo, laps og TE."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..database.models.activity import Activity, ActivityLap
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .coaching_analysis_service import CoachingAnalysisService

SESSION_TYPES = (
    "recovery_run",
    "easy_aerobic",
    "long_aerobic",
    "steady",
    "tempo",
    "threshold",
    "vo2_intervals",
    "anaerobic",
    "race",
    "mixed",
    "unknown",
)

LONG_AEROBIC_MIN_DURATION_S = 75 * 60
RECOVERY_HR_LT1_RATIO = 0.88
INTERVAL_MIN_WORK_REPEATS = 3
INTERVAL_WORK_MIN_SECONDS = 60
RACE_NAME_PATTERN = re.compile(
    r"\b(race|marathon|half\s*marathon|hm\b|5k|10k|konkurranse|løp\b|parkrun)\b",
    re.IGNORECASE,
)


@dataclass
class _ZoneProfile:
    low_s: float = 0.0
    threshold_s: float = 0.0
    high_s: float = 0.0
    unknown_s: float = 0.0
    method: str = "unknown"

    @property
    def known_total(self) -> float:
        return self.low_s + self.threshold_s + self.high_s

    def pct(self, zone: str) -> Optional[float]:
        total = self.known_total
        if total <= 0:
            return None
        mapping = {"low": self.low_s, "threshold": self.threshold_s, "high": self.high_s}
        return mapping.get(zone, 0.0) / total * 100.0


@dataclass
class _ClassificationScore:
    session_type: str
    score: float
    evidence: List[str] = field(default_factory=list)


class SessionClassifierService:
    """Evidence-based session type classification for running activities."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        coaching: Optional[CoachingAnalysisService] = None,
    ):
        self.db = db
        self.storage = storage
        self._coaching = coaching or CoachingAnalysisService(db, storage)

    def classify_activity(
        self,
        activity: Activity,
        *,
        end_date: Optional[date] = None,
        lt1_hr: Optional[float] = None,
        lt2_hr: Optional[float] = None,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        if not is_running_activity(activity, include_treadmill=include_treadmill):
            return self._result("unknown", 0.2, ["non_running_activity"], "activity_type")

        if lt1_hr is None or lt2_hr is None:
            ref_day = end_date or (activity.start_time.date() if activity.start_time else date.today())
            thresholds = self._coaching.build_coaching_analysis(
                days=90,
                end_date=ref_day,
                include_treadmill=include_treadmill,
            ).get("thresholds", {})
            lt1_hr = lt1_hr or thresholds.get("lt1", {}).get("heart_rate_bpm")
            lt2_hr = lt2_hr or thresholds.get("lt2", {}).get("heart_rate_bpm")

        buckets, method = self._coaching.get_activity_intensity_buckets(activity, lt1_hr, lt2_hr)
        profile = _ZoneProfile(
            low_s=buckets.get("low", 0.0),
            threshold_s=buckets.get("threshold", 0.0),
            high_s=buckets.get("high", 0.0),
            unknown_s=buckets.get("unknown", 0.0),
            method=method,
        )
        duration = float(activity.duration or 0.0)
        aerobic_te = float(activity.total_training_effect) if activity.total_training_effect else None
        anaerobic_te = (
            float(activity.total_anaerobic_training_effect)
            if activity.total_anaerobic_training_effect
            else None
        )
        interval_evidence = self._interval_structure(activity, lt1_hr, lt2_hr)

        if RACE_NAME_PATTERN.search(activity.activity_name or ""):
            profile_evidence = []
            if profile.pct("high") is not None:
                profile_evidence.append(f"{profile.pct('high'):.0f}% above LT2")
            if aerobic_te is not None:
                profile_evidence.append(f"aerobic_training_effect={aerobic_te:.1f}")
            return self._result(
                "race",
                0.9,
                [f"activity_name={activity.activity_name!r}", *profile_evidence],
                profile.method,
            )

        candidates: List[_ClassificationScore] = []
        if self._looks_like_race(activity, profile, aerobic_te, anaerobic_te):
            candidates.append(
                _ClassificationScore(
                    "race",
                    0.92 if RACE_NAME_PATTERN.search(activity.activity_name or "") else 0.85,
                    self._race_evidence(activity, profile, aerobic_te),
                )
            )
        if interval_evidence.get("work_repeats", 0) >= INTERVAL_MIN_WORK_REPEATS:
            candidates.append(
                _ClassificationScore(
                    "vo2_intervals",
                    0.75 + min(0.15, interval_evidence["work_repeats"] * 0.03),
                    interval_evidence.get("evidence", []),
                )
            )
        if profile.pct("high") is not None and profile.pct("high") >= 25 and aerobic_te and aerobic_te >= 4.0:
            candidates.append(
                _ClassificationScore(
                    "anaerobic",
                    0.7 + min(0.2, profile.pct("high") / 100.0),
                    [f"{profile.pct('high'):.0f}% of known time above LT2", f"aerobic_training_effect={aerobic_te:.1f}"],
                )
            )
        if profile.pct("threshold") is not None and profile.pct("threshold") >= 30:
            candidates.append(
                _ClassificationScore(
                    "threshold",
                    0.65 + min(0.25, profile.pct("threshold") / 200.0),
                    [f"{profile.pct('threshold'):.0f}% of known time between LT1 and LT2"],
                )
            )
        if profile.pct("threshold") is not None and 15 <= profile.pct("threshold") < 30:
            candidates.append(
                _ClassificationScore(
                    "tempo",
                    0.6,
                    [f"{profile.pct('threshold'):.0f}% of known time between LT1 and LT2"],
                )
            )
        if duration >= LONG_AEROBIC_MIN_DURATION_S and profile.pct("low") is not None and profile.pct("low") >= 70:
            candidates.append(
                _ClassificationScore(
                    "long_aerobic",
                    0.75,
                    [f"duration={duration / 60:.0f}min", f"{profile.pct('low'):.0f}% below LT1"],
                )
            )
        if self._is_recovery(activity, profile, lt1_hr, aerobic_te):
            candidates.append(
                _ClassificationScore(
                    "recovery_run",
                    0.7,
                    self._recovery_evidence(activity, profile, lt1_hr, aerobic_te),
                )
            )
        if profile.pct("low") is not None and profile.pct("low") >= 75 and duration < LONG_AEROBIC_MIN_DURATION_S:
            candidates.append(
                _ClassificationScore(
                    "easy_aerobic",
                    0.65,
                    [f"{profile.pct('low'):.0f}% below LT1"],
                )
            )
        if profile.pct("low") is not None and 40 <= profile.pct("low") <= 65 and profile.pct("threshold") is not None and profile.pct("threshold") >= 25:
            candidates.append(
                _ClassificationScore(
                    "steady",
                    0.55,
                    ["sustained moderate intensity between easy and threshold"],
                )
            )

        if aerobic_te is not None and aerobic_te >= 3.5:
            for candidate in candidates:
                if candidate.session_type in {"threshold", "tempo", "vo2_intervals", "anaerobic"}:
                    candidate.evidence.append(f"aerobic_training_effect={aerobic_te:.1f}")

        if not candidates:
            if profile.known_total <= 0:
                return self._result("unknown", 0.15, ["missing_hr_and_thresholds"], method)
            if self._is_mixed(profile):
                return self._result(
                    "mixed",
                    0.45,
                    ["multiple intensity zones without dominant pattern"],
                    method,
                )
            return self._result("unknown", 0.3, ["insufficient_classification_signals"], method)

        candidates.sort(key=lambda c: c.score, reverse=True)
        top = candidates[0]

        compatible_easy = {"recovery_run", "easy_aerobic", "long_aerobic", "steady"}
        if len(candidates) >= 2 and candidates[1].session_type in compatible_easy and top.session_type in compatible_easy:
            pass  # keep top — subtypes are not contradictory
        elif len(candidates) >= 2 and candidates[1].score >= top.score * 0.92:
            mixed_evidence = top.evidence + [f"also_considered={candidates[1].session_type}"]
            return self._result("mixed", min(top.score, 0.55), mixed_evidence, method)

        if top.session_type == "race" and any("activity_name" in e for e in top.evidence):
            return self._result(top.session_type, min(0.95, top.score + 0.1), top.evidence, method)

        confidence = min(0.95, top.score)
        if method == "average_hr":
            confidence *= 0.85
        if profile.unknown_s > duration * 0.5:
            confidence *= 0.75

        return self._result(top.session_type, round(confidence, 2), top.evidence, method)

    def _result(
        self,
        session_type: str,
        confidence: float,
        evidence: List[str],
        method: str,
    ) -> Dict[str, Any]:
        return {
            "session_type": session_type,
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
            "evidence": evidence,
            "method": method,
        }

    def _is_recovery(
        self,
        activity: Activity,
        profile: _ZoneProfile,
        lt1_hr: Optional[float],
        aerobic_te: Optional[float],
    ) -> bool:
        if aerobic_te is not None and aerobic_te > 2.5:
            return False
        if profile.pct("low") is not None and profile.pct("low") >= 85:
            return True
        if (
            lt1_hr
            and activity.average_heart_rate
            and float(activity.average_heart_rate) < float(lt1_hr) * RECOVERY_HR_LT1_RATIO
        ):
            return True
        return aerobic_te is not None and aerobic_te <= 2.0 and profile.pct("high") is not None and profile.pct("high") < 5

    def _recovery_evidence(
        self,
        activity: Activity,
        profile: _ZoneProfile,
        lt1_hr: Optional[float],
        aerobic_te: Optional[float],
    ) -> List[str]:
        evidence: List[str] = []
        if profile.pct("low") is not None:
            evidence.append(f"{profile.pct('low'):.0f}% below LT1")
        if lt1_hr and activity.average_heart_rate:
            evidence.append(f"avg_hr={activity.average_heart_rate:.0f} vs lt1={lt1_hr:.0f}")
        if aerobic_te is not None:
            evidence.append(f"aerobic_training_effect={aerobic_te:.1f}")
        return evidence

    def _looks_like_race(
        self,
        activity: Activity,
        profile: _ZoneProfile,
        aerobic_te: Optional[float],
        anaerobic_te: Optional[float],
    ) -> bool:
        name = activity.activity_name or ""
        if RACE_NAME_PATTERN.search(name):
            return True
        high_pct = profile.pct("high") or 0.0
        if high_pct >= 15 and aerobic_te and aerobic_te >= 4.5:
            return True
        if anaerobic_te and anaerobic_te >= 3.0 and high_pct >= 10:
            return True
        return False

    def _race_evidence(
        self,
        activity: Activity,
        profile: _ZoneProfile,
        aerobic_te: Optional[float],
    ) -> List[str]:
        evidence: List[str] = []
        if activity.activity_name and RACE_NAME_PATTERN.search(activity.activity_name):
            evidence.append(f"activity_name={activity.activity_name!r}")
        if profile.pct("high") is not None:
            evidence.append(f"{profile.pct('high'):.0f}% above LT2")
        if aerobic_te is not None:
            evidence.append(f"aerobic_training_effect={aerobic_te:.1f}")
        return evidence

    def _is_mixed(self, profile: _ZoneProfile) -> bool:
        zones = [profile.pct("low"), profile.pct("threshold"), profile.pct("high")]
        significant = sum(1 for pct in zones if pct is not None and pct >= 20)
        return significant >= 2

    def _interval_structure(
        self,
        activity: Activity,
        lt1_hr: Optional[float],
        lt2_hr: Optional[float],
    ) -> Dict[str, Any]:
        laps: List[ActivityLap] = list(activity.laps or [])
        if not laps and activity.activity_id:
            laps = (
                self.db.query(ActivityLap)
                .filter(ActivityLap.activity_id == activity.activity_id)
                .order_by(ActivityLap.lap_number)
                .all()
            )

        if len(laps) < INTERVAL_MIN_WORK_REPEATS + 1:
            return {"work_repeats": 0, "evidence": []}

        work_repeats = 0
        for lap in laps:
            hr = lap.average_heart_rate
            duration = float(lap.duration or 0)
            if not hr or duration < INTERVAL_WORK_MIN_SECONDS:
                continue
            if lt2_hr and float(hr) >= float(lt2_hr) * 0.97:
                work_repeats += 1
            elif lt1_hr and lt2_hr and float(lt1_hr) < float(hr) <= float(lt2_hr) * 1.02:
                work_repeats += 1

        evidence: List[str] = []
        if work_repeats >= INTERVAL_MIN_WORK_REPEATS:
            evidence.append(f"{work_repeats} repeated work intervals")
        return {"work_repeats": work_repeats, "evidence": evidence}
