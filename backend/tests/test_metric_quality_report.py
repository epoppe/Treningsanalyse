import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.mcp.metric_quality import build_metric_quality_report, format_metric_quality_markdown


class MetricQualityReportTests(unittest.TestCase):
    def test_build_report_classifies_statuses(self):
        def fake_query(key, start_date=None, end_date=None, limit=14):
            if key == "fitness.ctl":
                return {
                    "status": "ok",
                    "points": [{"date": "2026-05-31", "value": 42.0}],
                }
            if key == "broken.metric":
                return {"status": "error", "message": "boom"}
            return {"status": "ok", "points": []}

        catalog = [
            {"key": "fitness.ctl", "category": "fitness", "unit": "load", "scope": "daily", "source": "derived"},
            {"key": "broken.metric", "category": "x", "unit": "x", "scope": "daily", "source": "derived"},
            {"key": "empty.metric", "category": "x", "unit": "x", "scope": "daily", "source": "derived", "heuristic": True},
        ]
        report = build_metric_quality_report(
            catalog_metrics=catalog,
            query_timeseries_fn=fake_query,
            reference_date=date(2026, 5, 31),
        )
        self.assertEqual(report["summary"]["ok"], 1)
        self.assertEqual(report["summary"]["bug"], 1)
        self.assertEqual(report["summary"]["no_data"], 1)
        md = format_metric_quality_markdown(report)
        self.assertIn("fitness.ctl", md)


if __name__ == "__main__":
    unittest.main()
