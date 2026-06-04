import unittest
from datetime import date

from app.mcp.metric_quality import build_metric_quality_report, format_metric_quality_markdown


def _empty_ok_series():
    return {"status": "ok", "points": []}


def _ok_with_point(value=42.0, point_date="2026-05-31"):
    return {
        "status": "ok",
        "points": [{"date": point_date, "value": value}],
    }


class MetricQualityReportTests(unittest.TestCase):
    def _report_for(self, catalog, query_fn, reference_date=date(2026, 5, 31)):
        return build_metric_quality_report(
            catalog_metrics=catalog,
            query_timeseries_fn=query_fn,
            reference_date=reference_date,
        )

    def _entry(self, report, key):
        return next(e for e in report["entries"] if e["metric_key"] == key)

    def test_supported_metric_with_data_becomes_ok(self):
        catalog = [
            {
                "key": "activity.training_stress_score",
                "category": "activity",
                "unit": "score",
                "scope": "activity",
                "source": "stored",
                "availability": "supported",
            },
        ]

        def query(key, start_date=None, end_date=None, limit=14):
            if key == "activity.training_stress_score":
                return _ok_with_point(55.0)
            return _empty_ok_series()

        report = self._report_for(catalog, query)
        entry = self._entry(report, "activity.training_stress_score")

        self.assertEqual(entry["status"], "ok")
        self.assertEqual(entry["latest_value"], 55.0)
        self.assertEqual(entry["latest_date"], "2026-05-31")
        self.assertEqual(report["summary"]["ok"], 1)

    def test_not_ingested_without_data_becomes_not_ingested(self):
        reason = "Krever Garmin health sync som ikke er kjørt."
        catalog = [
            {
                "key": "health.resting_heart_rate",
                "category": "health",
                "unit": "bpm",
                "scope": "daily",
                "source": "stored",
                "availability": "not_ingested",
                "availability_reason": reason,
            },
        ]

        report = self._report_for(catalog, lambda *_a, **_k: _empty_ok_series())
        entry = self._entry(report, "health.resting_heart_rate")

        self.assertEqual(entry["status"], "not_ingested")
        self.assertEqual(entry["issue"], reason)
        self.assertIsNone(entry["latest_value"])
        self.assertEqual(report["summary"]["not_ingested"], 1)

    def test_empty_source_derived_without_data_becomes_empty_source(self):
        reason = "Krever HRV-rader i databasen."
        catalog = [
            {
                "key": "readiness.hrv_delta_pct",
                "category": "readiness",
                "unit": "pct",
                "scope": "daily",
                "source": "derived",
                "availability": "empty_source",
                "availability_reason": reason,
            },
        ]

        report = self._report_for(catalog, lambda *_a, **_k: _empty_ok_series())
        entry = self._entry(report, "readiness.hrv_delta_pct")

        self.assertEqual(entry["status"], "empty_source")
        self.assertEqual(entry["issue"], reason)
        self.assertEqual(report["summary"]["empty_source"], 1)

    def test_unsupported_without_data_becomes_unsupported(self):
        reason = "Metrikken er ikke implementert i timeseries-motoren."
        catalog = [
            {
                "key": "legacy.unsupported_metric",
                "category": "legacy",
                "unit": "x",
                "scope": "daily",
                "source": "stored",
                "availability": "unsupported",
                "availability_reason": reason,
            },
        ]

        report = self._report_for(catalog, lambda *_a, **_k: _empty_ok_series())
        entry = self._entry(report, "legacy.unsupported_metric")

        self.assertEqual(entry["status"], "unsupported")
        self.assertEqual(entry["issue"], reason)
        self.assertEqual(report["summary"]["unsupported"], 1)

    def test_empty_series_without_availability_hint_stays_no_data(self):
        catalog = [
            {
                "key": "computed.metric",
                "category": "fitness",
                "unit": "load",
                "scope": "daily",
                "source": "derived",
                "availability": "computed",
            },
        ]

        report = self._report_for(catalog, lambda *_a, **_k: _empty_ok_series())
        entry = self._entry(report, "computed.metric")

        self.assertEqual(entry["status"], "no_data")
        self.assertEqual(report["summary"]["no_data"], 1)

    def test_build_report_classifies_errors_and_markdown(self):
        def query(key, start_date=None, end_date=None, limit=14):
            if key == "fitness.ctl":
                return _ok_with_point()
            if key == "broken.metric":
                return {"status": "error", "message": "boom"}
            return _empty_ok_series()

        catalog = [
            {"key": "fitness.ctl", "category": "fitness", "unit": "load", "scope": "daily", "source": "derived"},
            {"key": "broken.metric", "category": "x", "unit": "x", "scope": "daily", "source": "derived"},
            {
                "key": "empty.metric",
                "category": "x",
                "unit": "x",
                "scope": "daily",
                "source": "derived",
                "heuristic": True,
                "availability": "computed",
            },
        ]
        report = self._report_for(catalog, query)

        self.assertEqual(report["summary"]["ok"], 1)
        self.assertEqual(report["summary"]["bug"], 1)
        self.assertEqual(report["summary"]["no_data"], 1)
        md = format_metric_quality_markdown(report)
        self.assertIn("fitness.ctl", md)
        self.assertIn("Availability", md)


if __name__ == "__main__":
    unittest.main()
