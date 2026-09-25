"""Known-empty health days stay out of the range-endpoint fetch list."""

from __future__ import annotations

import unittest
from datetime import date

from app.services.health_data_missing_helpers import missing_dates_to_fetch


class MissingDatesToFetchTests(unittest.TestCase):
    def test_skips_stored_days_and_known_empty_days(self):
        pending = missing_dates_to_fetch(
            date(2026, 1, 1),
            date(2026, 1, 4),
            existing={date(2026, 1, 1)},
            known_missing={date(2026, 1, 2)},
        )
        self.assertEqual(pending, [date(2026, 1, 3), date(2026, 1, 4)])

    def test_empty_range_fetches_nothing(self):
        self.assertEqual(
            missing_dates_to_fetch(date(2026, 2, 2), date(2026, 2, 1), set(), set()),
            [],
        )
