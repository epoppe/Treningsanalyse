"""Transparent flerdimensjonal atlet-tilstand — ingen opaque super-score."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .coaching_decision_metrics_service import CoachingDecisionMetricsService
from .context_adjusted_trend_service import ContextAdjustedTrendService
from .metric_evidence import MetricEvidence
from .ppap_metrics_service import PpapMetricsService
from .trend_analysis_service import TrendAnalysisService


class AthleteStateService:
    """Samlet men eksplisitt tilstandsmodell for AI-coaching."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._decision = CoachingDecisionMetricsService(db, self._ppap)
        self._trends = TrendAnalysisService(db, storage)
        self._context_trends = ContextAdjustedTrendService(db, storage)

    def build_state(self, day: Optional[date] = None) -> Dict[str, Any]:
        day = day or date.today()
        ctl = self._ppap.get_ctl(day)
        atl = self._ppap.get_atl(day)
        tsb = self._ppap.get_tsb(day)
        hrv_delta = self._ppap.get_hrv_delta_pct(day)
        readiness = self._ppap.get_readiness_component(day, "readiness.total_score")

        ctl_trend = self._trends.analyze_metric("ctl", end_date=day, window_days=28)
        ef_trend = self._context_trends.analyze_metric(
            "easy_run_efficiency",
            end_date=day,
            window_days=90,
        )
        durability = self._decision.get_durability_score(day)
        consistency = self._decision.get_consistency_score(day)
        durability_trend = self._trends.analyze_metric("durability", end_date=day, window_days=90)

        return {
            "date": day.isoformat(),
            "fitness": self._dim(
                value=ctl,
                trend=ctl_trend.get("direction"),
                confidence=ctl_trend.get("confidence", 0.4),
                evidence=["fitness.ctl", f"ctl_trend={ctl_trend.get('direction')}"],
            ),
            "fatigue": self._dim(
                value=atl,
                trend="elevated" if tsb is not None and float(tsb) < -10 else "moderate",
                confidence=0.7 if atl is not None else 0.2,
                evidence=["fitness.atl", f"tsb={tsb}"],
            ),
            "recovery": self._dim(
                value=readiness if readiness is not None else (
                    70 + float(hrv_delta) if hrv_delta is not None else None
                ),
                trend="improving" if hrv_delta is not None and float(hrv_delta) > 0 else (
                    "declining" if hrv_delta is not None and float(hrv_delta) < -5 else "stable"
                ),
                confidence=0.65 if hrv_delta is not None or readiness is not None else 0.2,
                evidence=[
                    f"hrv_delta_pct={hrv_delta}",
                    f"readiness.total_score={readiness}",
                ],
            ),
            "durability": self._dim(
                value=durability,
                trend=durability_trend.get("direction"),
                confidence=durability_trend.get("confidence", 0.3),
                evidence=["running.durability_score", "long_run quality"],
            ),
            "threshold_fitness": self._dim(
                value=None,
                trend=self._trends.analyze_metric(
                    "lactate_threshold_pace",
                    end_date=day,
                    window_days=90,
                ).get("direction"),
                confidence=0.4,
                evidence=["lactate_threshold_history", "adaptive LT1"],
            ),
            "aerobic_efficiency": self._dim(
                value=(ef_trend.get("context_adjusted_trend") or {}).get("current"),
                trend=(ef_trend.get("context_adjusted_trend") or {}).get("direction"),
                confidence=ef_trend.get("confidence", 0.3),
                evidence=["easy_run_efficiency context-adjusted", *ef_trend.get("adjustments", [])],
            ),
            "consistency": self._dim(
                value=consistency,
                trend=None,
                confidence=0.7 if consistency is not None else 0.1,
                evidence=["training_days_per_window"],
            ),
            "load_tolerance": self._dim(
                value=tsb,
                trend=None,
                confidence=0.6 if tsb is not None else 0.2,
                evidence=["fitness.tsb", "not a single opaque score"],
            ),
            "model_notes": [
                "Dimensions are separate — do not average into one readiness number.",
                "Each value carries its own confidence and evidence.",
            ],
        }

    @staticmethod
    def _dim(
        *,
        value: Any,
        trend: Optional[str],
        confidence: float,
        evidence: list,
    ) -> Dict[str, Any]:
        return {
            "value": value,
            "trend": trend,
            "confidence": round(max(0.0, min(1.0, float(confidence))), 2),
            "evidence": evidence,
        }
