"""Tests for plan vs actual comparison."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from app.services.plan_vs_actual_service import PlanVsActualService


class PlanVsActualServiceTests(unittest.TestCase):
    def test_summarize_completion_rate(self):
        service = PlanVsActualService(MagicMock())
        days = [
            {"planned_type": "threshold", "execution_status": "followed", "actual_type": "threshold"},
            {"planned_type": "easy_run", "execution_status": "missed", "actual_type": None},
        ]
        summary = service._summarize(days)
        self.assertEqual(summary["planned_count"], 2)
        self.assertEqual(summary["completed_count"], 1)
        self.assertEqual(summary["completion_rate"], 0.5)

    def test_compare_uses_week_start(self):
        db = MagicMock()
        service = PlanVsActualService(db)
        with patch.object(service, "_actual_for_day", return_value={"type": "easy_run", "execution_status": "followed"}):
            result = service.compare(
                {
                    "week_start": "2026-08-18",
                    "sessions": [{"day_offset": 0, "type": "easy_run", "duration_min": 45}],
                }
            )
        self.assertEqual(result["week_start"], "2026-08-18")
        self.assertEqual(result["days"][0]["date"], "2026-08-18")
        self.assertEqual(result["days"][0]["planned_type"], "easy_run")


if __name__ == "__main__":
    unittest.main()
