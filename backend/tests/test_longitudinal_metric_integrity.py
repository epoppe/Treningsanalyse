"""Longitudinal metric integrity: units, as-of, exact ranges, lag, history."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.database.models.sleep import HRV
from app.database.models.summaries import MonthlySummary
from app.services.analytics_metric_registry import ANALYTICS_METRICS, get_analytics_metric
from app.services.history_cockpit_service import HistoryCockpitService
from app.services.mcp_derived_metrics_service import DERIVED_METRIC_CATALOG, McpDerivedMetricsService
from app.services.metric_registry import METRIC_REGISTRY
from app.services.performance_metrics_service import PerformanceMetricsService
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.temporal_metric_contract import (
    aggregation_window_days,
    contract_for,
    effective_sample_count,
    speed_mps_to_kmh,
    stimulus_bounds,
    stimulus_producer_family,
)
from app.services.trend_analysis_service import METRIC_FETCHERS, TrendAnalysisService
from app.services.training_response_service import TrainingResponseService, residualize_outcomes


def _session():
    tmp = tempfile.TemporaryDirectory()
    engine = create_engine(f"sqlite:///{Path(tmp.name) / 'test.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    return tmp, db


def _speed_efforts(activity: Activity, speed: float):
    durations = [180, 360, 720, 1200, 1800]
    return [
        {
            "metric_type": "speed",
            "duration_seconds": duration,
            "speed_mps": speed,
            "value": speed,
            "activity_id": activity.activity_id,
            "activity_start_time": activity.start_time.isoformat() if activity.start_time else None,
        }
        for duration in durations
    ]


class UnitContractTests(unittest.TestCase):
    def test_speed_conversion(self):
        self.assertEqual(speed_mps_to_kmh(4.0), 14.4)
        self.assertEqual(speed_mps_to_kmh(3.5), 12.6)

    def test_critical_speed_registry_contract(self):
        contract = contract_for("running.critical_speed")
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(contract.canonical_unit, "m/s")
        self.assertEqual(contract.display_unit, "km/h")
        self.assertEqual(contract.display_multiplier, 3.6)
        self.assertEqual(contract.temporal_semantics, "snapshot")
        self.assertTrue(contract.supports_as_of)
        self.assertEqual(METRIC_REGISTRY["critical_speed"]["units"], "m_per_s")
        self.assertEqual(get_analytics_metric("running.critical_speed")["unit"], "km/h")
        self.assertEqual(DERIVED_METRIC_CATALOG["running.critical_speed"]["unit"], "km/h")

    def test_analyse_metrics_match_display_units(self):
        for key in ANALYTICS_METRICS:
            contract = contract_for(key)
            self.assertIsNotNone(contract, key)
            assert contract is not None
            analytics = get_analytics_metric(key)
            self.assertEqual(analytics["unit"], contract.display_unit, key)
            self.assertIn(contract.temporal_semantics, {
                "observation",
                "snapshot",
                "rolling_mean",
                "rolling_median",
                "rolling_best",
                "cumulative",
                "derived_state",
            })
            if key in DERIVED_METRIC_CATALOG:
                self.assertEqual(DERIVED_METRIC_CATALOG[key]["unit"], contract.display_unit, key)

    def test_duration_curve_catalog_is_kmh_while_producer_is_mps(self):
        for key in ("running.speed_5m", "running.speed_20m_hist"):
            contract = contract_for(key)
            assert contract is not None
            self.assertEqual(contract.canonical_unit, "m/s")
            self.assertEqual(DERIVED_METRIC_CATALOG[key]["unit"], "km/h")
            self.assertEqual(contract.display_multiplier, 3.6)

    def test_hist_speed_is_rolling_best_not_independent_days(self):
        contract = contract_for("running.speed_20m_hist")
        assert contract is not None
        self.assertEqual(contract.temporal_semantics, "rolling_best")
        self.assertEqual(contract.smoothing_window_days, 365)


class PresentationBoundaryTests(unittest.TestCase):
    def test_api_converts_critical_speed_and_duration_curve(self):
        tmp, db = _session()
        try:
            service = McpDerivedMetricsService(db, MagicMock())
            service._ppap = MagicMock()
            service._ppap.get_critical_speed_snapshot.return_value = (4.0, 12.0)
            service._ppap.get_duration_curve_value.return_value = 3.5
            self.assertEqual(service._daily_metric_value("running.critical_speed", date(2026, 5, 1)), 14.4)
            self.assertEqual(service._daily_metric_value("running.speed_5m", date(2026, 5, 1)), 12.6)
            self.assertEqual(service._daily_metric_value("running.w_prime", date(2026, 5, 1)), 12.0)
        finally:
            db.close()
            tmp.cleanup()


class AsOfCriticalSpeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.db = _session()
        running = ActivityType(type_key="running", type_name="Running")
        self.db.add(running)
        self.db.commit()
        self.type_id = running.id
        self.storage = MagicMock()
        self.perf = PerformanceMetricsService(self.db, self.storage)
        self.speeds = {}

        def extract(activity):
            return _speed_efforts(activity, self.speeds[activity.activity_id])

        self.perf.extract_activity_best_efforts = extract  # type: ignore[method-assign]

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _add(self, activity_id: str, day: date, speed: float) -> None:
        self.speeds[activity_id] = speed
        self.db.add(
            Activity(
                activity_id=activity_id,
                activity_name="Run",
                start_time=datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc),
                duration=3600,
                distance=speed * 3600,
                average_speed=speed,
                activity_type_id=self.type_id,
            )
        )
        self.db.commit()

    def test_future_effort_does_not_change_historical_critical_speed(self):
        day = date(2026, 5, 1)
        self._add("early", day - timedelta(days=10), 4.0)
        before = self.perf.calculate_critical_speed(days=365, end_date=day)
        self.assertAlmostEqual(before["critical_speed_mps"], 4.0, places=2)
        self._add("late", day + timedelta(days=3), 5.0)
        after = self.perf.calculate_critical_speed(days=365, end_date=day)
        self.assertEqual(after["critical_speed_mps"], before["critical_speed_mps"])
        later = self.perf.calculate_critical_speed(days=365, end_date=day + timedelta(days=3))
        self.assertGreater(later["critical_speed_mps"], before["critical_speed_mps"])

    def test_snapshot_uses_end_date_not_current_snapshot(self):
        day = date(2026, 5, 1)
        self._add("early", day - timedelta(days=2), 4.0)
        ppap = PpapMetricsService(self.db, self.storage)
        ppap._perf_service_instance = self.perf
        cs, _w = ppap.get_critical_speed_snapshot(day)
        self.assertAlmostEqual(cs, 4.0, places=2)
        self._add("late", day + timedelta(days=5), 5.2)
        ppap._critical_speed_cache.clear()
        again, _ = ppap.get_critical_speed_snapshot(day)
        self.assertAlmostEqual(again, 4.0, places=2)

    def test_future_effort_does_not_change_historical_duration_metric(self):
        day = date(2026, 5, 1)
        self._add("early", day - timedelta(days=4), 4.0)
        curve = self.perf.build_duration_curve(days=365, end_date=day)
        speed_5 = next(
            point["speed_mps"]
            for point in curve["curves"]["speed"]
            if point["duration_seconds"] == 360
        )
        self.assertAlmostEqual(speed_5, 4.0, places=2)
        self._add("late", day + timedelta(days=2), 5.5)
        again = self.perf.build_duration_curve(days=365, end_date=day)
        speed_again = next(
            point["speed_mps"]
            for point in again["curves"]["speed"]
            if point["duration_seconds"] == 360
        )
        self.assertAlmostEqual(speed_again, 4.0, places=2)


class ExactRangeTests(unittest.TestCase):
    def test_45_day_brush_is_not_snapped(self):
        from app.main import app
        from app.dependencies import get_db, get_data_storage

        def _db():
            yield MagicMock()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = lambda: MagicMock()
        try:
            with patch("app.routers.analysis_workspace.TrendAnalysisService") as trend:
                trend.return_value.analyze_all.return_value = {"metrics": {}}
                trend.return_value.compare_periods.return_value = {
                    "unit": "km/h",
                    "period_a_summary": {"value": 14.4, "method": "latest_snapshot", "sample_count": 4, "effective_sample_count": 2, "coverage_ratio": 0.1, "mean": 14.0, "median": 14.2, "end_value": 14.4, "point_in_time": True},
                    "period_b_summary": {"value": 14.0, "method": "latest_snapshot", "sample_count": 4, "effective_sample_count": 2, "coverage_ratio": 0.1, "mean": 13.8, "median": 14.0, "end_value": 14.0, "point_in_time": True},
                    "absolute_delta": 0.4,
                    "relative_delta": 2.9,
                    "effect_vs_personal_noise": 1.2,
                    "sample_count": 4,
                    "effective_sample_count": 2,
                    "coverage": {},
                    "uncertainty": {"ci95": [-0.1, 0.8], "estimate": 0.4},
                    "evidence": "uncertain",
                    "from_zero": False,
                }
                from fastapi.testclient import TestClient

                client = TestClient(app)
                dev = client.get(
                    "/api/analysis/development",
                    params={"start_date": "2026-01-01", "end_date": "2026-02-14"},
                )
                self.assertEqual(dev.status_code, 200, dev.text)
                body = dev.json()
                self.assertEqual(body["analyzed_days"], 45)
                self.assertTrue(body["exact_range"])
                self.assertEqual(body["window"], "45d")
                windows = trend.return_value.analyze_all.call_args.kwargs["windows"]
                self.assertEqual(windows, (45,))

                comp = client.get(
                    "/api/analysis/period-comparison",
                    params={"start_date": "2026-01-01", "end_date": "2026-02-14"},
                )
                self.assertEqual(comp.status_code, 200, comp.text)
                compared = comp.json()
                self.assertEqual(compared["days"], 45)
                self.assertTrue(compared["exact_range"])
                self.assertEqual(compared["start_date"], "2026-01-01")
                self.assertEqual(compared["end_date"], "2026-02-14")
                self.assertEqual(compared["previous_end_date"], "2025-12-31")
                self.assertEqual(compared["previous_start_date"], "2025-11-17")
                row = compared["rows"][0]
                self.assertIn("unit", row)
                self.assertIsNotNone(row["period_a"]["summary_method"])
        finally:
            app.dependency_overrides.clear()


class TrainingResponseWindowTests(unittest.TestCase):
    def test_lag_28_threshold_14_excludes_outcome_day(self):
        outcome = date(2026, 9, 26)
        window = aggregation_window_days("threshold_volume")
        self.assertEqual(window, 14)
        bounds = stimulus_bounds(outcome, 28, aggregation_days=window)
        self.assertEqual(bounds["stimulus_end"], date(2026, 8, 29))
        self.assertEqual(bounds["stimulus_start"], date(2026, 8, 16))
        self.assertEqual((bounds["stimulus_end"] - bounds["stimulus_start"]).days + 1, 14)
        self.assertLess(bounds["stimulus_end"], outcome)
        easy = aggregation_window_days("easy_volume")
        self.assertEqual(easy, 28)
        easy_bounds = stimulus_bounds(outcome, 28, aggregation_days=easy)
        self.assertEqual((easy_bounds["stimulus_end"] - easy_bounds["stimulus_start"]).days + 1, 28)
        self.assertNotEqual(
            (easy_bounds["stimulus_end"] - easy_bounds["stimulus_start"]).days,
            28,
        )

    def test_long_run_minutes_are_not_easy_minutes(self):
        tmp, db = _session()
        try:
            running = ActivityType(type_key="running", type_name="Running")
            db.add(running)
            db.commit()
            day = date(2026, 6, 1)
            for activity_id, duration in (("easy", 2400), ("long", 6000)):
                db.add(
                    Activity(
                        activity_id=activity_id,
                        activity_name="Run",
                        start_time=datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc),
                        duration=duration,
                        distance=10000,
                        activity_type_id=running.id,
                    )
                )
            db.commit()
            service = TrainingResponseService(db, MagicMock())

            def classify(activity, **_kwargs):
                if activity.activity_id == "long":
                    return {"session_type": "long_aerobic"}
                return {"session_type": "easy_aerobic"}

            with patch(
                "app.services.session_classifier_service.SessionClassifierService.classify_activity",
                side_effect=classify,
            ):
                long_min = service._stimulus_value("long_run_volume", day, day)
                easy_min = service._fallback_stimulus_minutes("easy_volume", day, day)
            self.assertEqual(long_min, 100.0)
            self.assertNotEqual(long_min, easy_min)

            def classify_vo2(activity, **_kwargs):
                if activity.activity_id == "long":
                    return {"session_type": "anaerobic"}
                return {"session_type": "vo2_intervals"}

            with patch(
                "app.services.session_classifier_service.SessionClassifierService.classify_activity",
                side_effect=classify_vo2,
            ):
                vo2 = service._stimulus_value("vo2_volume", day, day)
            self.assertEqual(vo2, 40.0)
        finally:
            db.close()
            tmp.cleanup()


class TrendSemanticsTests(unittest.TestCase):
    def test_effective_n_is_below_raw_n_for_rolling_series(self):
        effective = effective_sample_count(90, span_days=90, smoothing_window_days=30)
        self.assertLess(effective, 90)
        self.assertLessEqual(effective, 90 // 30)

    def test_change_point_returns_actual_date(self):
        tmp, db = _session()
        try:
            service = TrendAnalysisService(db, None)
            start = date(2026, 1, 1)
            series = [
                (start + timedelta(days=index), 10.0 if index < 20 else 40.0)
                for index in range(40)
            ]
            found = service._detect_change_point(series)
            self.assertTrue(found["change_detected"])
            self.assertEqual(found["change_date"], (start + timedelta(days=20)).isoformat())
        finally:
            db.close()
            tmp.cleanup()

    def test_metric_specific_noise_threshold_differs(self):
        hrv = contract_for("cardio.hrv_7d")
        vo2 = contract_for("performance.vo2max")
        assert hrv and vo2
        self.assertNotEqual(
            hrv.meaningful_change_fallback_relative_pct,
            vo2.meaningful_change_fallback_relative_pct,
        )
        self.assertGreater(hrv.meaningful_change_minimum_absolute, vo2.meaningful_change_minimum_absolute)


class HistorySemanticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.db = _session()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _month(self, year: int, month: int, distance: float, tss: float = 10) -> None:
        start = date(year, month, 1)
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        self.db.add(
            MonthlySummary(
                year=year,
                month=month,
                month_start_date=start,
                month_end_date=end,
                total_distance=distance,
                total_duration=distance,
                total_activities=1 if distance else 0,
                total_tss=tss,
            )
        )

    def test_period_all_is_not_capped_at_36(self):
        for index in range(40):
            year = 2023 + index // 12
            month = index % 12 + 1
            self._month(year, month, 1000)
        self.db.commit()
        payload = HistoryCockpitService(self.db, None).monthly_history(
            start=date(2023, 1, 1),
            end=date(2026, 4, 30),
            period="all",
        )
        self.assertFalse(payload["capped"])
        self.assertGreaterEqual(payload["available_month_count"], 40)
        self.assertGreaterEqual(payload["month_count"], 40)

    def test_current_month_never_reads_future_dates(self):
        as_of = date(2026, 9, 26)
        payload = HistoryCockpitService(self.db, MagicMock()).performance_recovery_history(
            end_date=as_of,
            months=3,
        )
        current = payload["months"][-1]
        self.assertEqual(current["month"], "2026-09")
        self.assertEqual(current["effective_end"], "2026-09-26")
        self.assertTrue(current["partial"])
        self.assertLess(current["month_end"], "2026-09-30")

    def test_mtd_yoy_compares_equivalent_days_and_from_zero_is_not_100(self):
        as_of = date(2026, 9, 26)
        running = ActivityType(type_key="running", type_name="Running")
        self.db.add(running)
        self.db.commit()
        self.db.add(
            Activity(
                activity_id="this-year",
                activity_name="Run",
                start_time=datetime(2026, 9, 10, 8, tzinfo=timezone.utc),
                duration=3600,
                distance=10000,
                activity_type_id=running.id,
            )
        )
        self.db.add(
            Activity(
                activity_id="last-year-in",
                activity_name="Run",
                start_time=datetime(2025, 9, 10, 8, tzinfo=timezone.utc),
                duration=1800,
                distance=5000,
                activity_type_id=running.id,
            )
        )
        self.db.add(
            Activity(
                activity_id="last-year-after-mtd",
                activity_name="Run",
                start_time=datetime(2025, 9, 28, 8, tzinfo=timezone.utc),
                duration=7200,
                distance=20000,
                activity_type_id=running.id,
            )
        )
        self._month(2026, 8, 1000)
        self._month(2025, 8, 0)
        self.db.commit()
        payload = HistoryCockpitService(self.db, None).yoy_months(end_date=as_of, months=2)
        september = next(row for row in payload["rows"] if row["month"] == 9)
        self.assertTrue(september["partial"])
        self.assertEqual(september["comparison_basis"], "month_to_date")
        self.assertEqual(september["current"]["distance_m"], 10000)
        self.assertEqual(september["previous_year"]["distance_m"], 5000)
        august = next(row for row in payload["rows"] if row["month"] == 8)
        self.assertIsNone(august["deltas"]["distance_pct"])
        self.assertEqual(august["comparison_basis"], "from_zero")

    def test_same_month_percentile_when_coverage_allows(self):
        for year, value in ((2023, 30), (2024, 40), (2025, 50), (2026, 55)):
            self.db.add(HRV(measurement_date=date(year, 9, 10), rmssd=value))
        self.db.commit()
        payload = HistoryCockpitService(self.db, MagicMock()).performance_recovery_history(
            end_date=date(2026, 9, 26),
            months=48,
        )
        current = payload["months"][-1]
        context = current.get("seasonal_context") or {}
        self.assertEqual(context.get("metric"), "hrv_median")
        self.assertGreaterEqual(context.get("same_month_samples") or 0, 3)
        self.assertIsNotNone(context.get("percentile_vs_same_month"))

    def test_period_all_starts_at_earliest_summary_not_ten_years(self):
        from app.routers.analysis_workspace import _history_start

        self._month(2014, 1, 500)
        self.db.commit()
        start, basis = _history_start(self.db, date(2026, 9, 26), "all")
        self.assertEqual(basis, "earliest_monthly_summary")
        self.assertEqual(start, date(2014, 1, 1))
        self.assertLess(start, date(2026, 9, 26) - timedelta(days=3650))

    def test_load_regimes_mark_a_durable_level_shift(self):
        for index in range(16):
            year = 2024 + index // 12
            month = index % 12 + 1
            self._month(year, month, 1000, tss=100 if index < 8 else 400)
        self.db.commit()
        payload = HistoryCockpitService(self.db, None).monthly_history(
            start=date(2024, 1, 1),
            end=date(2025, 4, 30),
            period="all",
        )
        shifts = [row for row in payload["regimes"] if row["kind"] == "level_shift_up"]
        self.assertTrue(shifts)
        self.assertTrue(any(row["durable"] for row in payload["regimes"]))
        self.assertTrue(all(row["interpretation"] == "load_regime" for row in payload["regimes"]))


class ContractAlignmentTests(unittest.TestCase):
    def test_domain_cards_map_atl_and_consistency(self):
        from app.routers.analysis_workspace import DOMAIN_METRICS, _domain_from_block

        by_domain = {row["domain"]: row for row in DOMAIN_METRICS}
        self.assertEqual(by_domain["training_load"]["metric"], "atl")
        self.assertEqual(by_domain["training_load"]["mcp_key"], "fitness.atl")
        self.assertEqual(by_domain["consistency"]["metric"], "consistency")
        self.assertEqual(by_domain["consistency"]["mcp_key"], "consistency.score")
        self.assertNotEqual(by_domain["consistency"]["metric"], "vo2max")
        self.assertEqual(by_domain["fitness"]["metric"], "ctl")

        card = _domain_from_block(
            by_domain["fitness"],
            {
                "direction": "improving",
                "sample_count": 90,
                "effective_sample_count": 2,
                "confidence": 0.9,
                "higher_is_better": True,
            },
            "90d",
        )
        self.assertEqual(card["evidence"], "insufficient")

    def test_context_direction_is_not_called_improving(self):
        tmp, db = _session()
        try:
            service = TrendAnalysisService(db, None)
            self.assertEqual(service._direction("ctl", 12.0, 2.0, 10, 10), "higher")
            self.assertEqual(service._direction("atl", -8.0, 2.0, 10, 10), "lower")
            self.assertEqual(service._direction("vo2max", 2.0, 0.5, 10, 10), "improving")
            self.assertEqual(service._direction("resting_hr", -3.0, 1.0, 10, 10), "improving")
        finally:
            db.close()
            tmp.cleanup()

    def test_efficiency_and_decoupling_use_canonical_producers(self):
        tmp, db = _session()
        try:
            service = TrendAnalysisService(db, None)
            self.assertEqual(METRIC_FETCHERS["easy_run_efficiency"], "fitness.ef_30d")
            self.assertEqual(METRIC_FETCHERS["decoupling"], "cardio.drift_score")
            with patch.object(
                service._derived,
                "metric_definition",
                return_value={"scope": "daily"},
            ), patch.object(
                service._derived,
                "query_timeseries",
                return_value={"points": [{"date": "2026-09-01", "value": 1.25}]},
            ) as query:
                points = service._fetch_series(
                    "easy_run_efficiency",
                    date(2026, 9, 1),
                    date(2026, 9, 1),
                )
            self.assertEqual(query.call_args.args[0], "fitness.ef_30d")
            self.assertEqual(points, [(date(2026, 9, 1), 1.25)])
        finally:
            db.close()
            tmp.cleanup()

    def test_stimulus_aliases_share_one_producer_family(self):
        self.assertEqual(stimulus_producer_family("easy_volume"), "zone_low")
        self.assertEqual(stimulus_producer_family("stimulus.easy_minutes_7d"), "zone_low")
        self.assertEqual(stimulus_producer_family("stimulus.easy_minutes_28d"), "zone_low")
        self.assertEqual(stimulus_producer_family("weekly_tss"), "tss_sum")
        self.assertEqual(stimulus_producer_family("stimulus.tss_28d"), "tss_sum")
        self.assertEqual(stimulus_producer_family("stimulus.vo2_minutes_14d"), "vo2_intervals")
        self.assertEqual(aggregation_window_days("stimulus.tss_28d"), 28)
        self.assertEqual(aggregation_window_days("weekly_tss"), 7)
        self.assertEqual(aggregation_window_days("stimulus.easy_minutes_28d"), 28)

    def test_dose_buckets_residualize_time_season_and_ctl(self):
        import math

        rows = []
        start = date(2023, 1, 1)
        for index in range(24):
            day = start + timedelta(days=21 * index)
            time_index = float(21 * index)
            ctl = 50.0 + 8.0 * math.sin(index / 2.5)
            angle = 2.0 * math.pi * (day.timetuple().tm_yday / 365.25)
            outcome = 0.04 * time_index + 0.3 * ctl + math.sin(angle) + 0.5 * math.cos(angle)
            rows.append(
                {
                    "date": day,
                    "outcome": outcome,
                    "stimulus": float(index % 5),
                    "ctl": ctl,
                }
            )
        adjusted = residualize_outcomes(rows)
        self.assertTrue(adjusted["controls_time"])
        self.assertTrue(adjusted["controls_season"])
        self.assertTrue(adjusted["controls_baseline_fitness"])
        self.assertTrue(adjusted["fully_controlled"])
        self.assertLess(max(abs(value) for value in adjusted["residuals"]), 1e-6)


if __name__ == "__main__":
    unittest.main()
