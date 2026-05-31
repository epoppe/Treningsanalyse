import unittest
from unittest.mock import MagicMock

from app.database.models.activity import Activity
from app.services.activity_data_validation import (
    apply_garmin_list_hr_fields,
    max_hr_from_fit_records,
    normalize_ground_contact_time_ms,
    normalize_stride_length_meters,
    validate_and_repair_activity,
)


class NormalizeUnitsTests(unittest.TestCase):
    def test_stride_cm_to_m(self):
        self.assertAlmostEqual(normalize_stride_length_meters(105.0), 1.05)

    def test_stride_already_meters(self):
        self.assertAlmostEqual(normalize_stride_length_meters(1.05), 1.05)

    def test_gct_ms_unchanged(self):
        self.assertEqual(normalize_ground_contact_time_ms(276.0), 276.0)

    def test_gct_seconds_to_ms(self):
        self.assertEqual(normalize_ground_contact_time_ms(0.276), 276.0)


class HeartRateRepairTests(unittest.TestCase):
    def test_clears_invalid_max_below_avg(self):
        activity = Activity(
            activity_id="1",
            average_heart_rate=156.0,
            max_heart_rate=149.0,
        )
        result = validate_and_repair_activity(activity)
        self.assertTrue(result.changed)
        self.assertIsNone(activity.max_heart_rate)

    def test_fixes_max_from_fit_records(self):
        activity = Activity(
            activity_id="2",
            average_heart_rate=156.0,
            max_heart_rate=149.0,
            detailed_metrics={
                "records": [
                    {"heart_rate": 150},
                    {"heart_rate": 172},
                ]
            },
        )
        result = validate_and_repair_activity(activity)
        self.assertTrue(result.changed)
        self.assertEqual(activity.max_heart_rate, 172.0)

    def test_apply_garmin_list_hr(self):
        activity = Activity(activity_id="3", average_heart_rate=150.0)
        changed = apply_garmin_list_hr_fields(
            activity,
            {"maxHR": 168, "minHR": 98},
        )
        self.assertTrue(changed)
        self.assertEqual(activity.max_heart_rate, 168.0)
        self.assertEqual(activity.min_heart_rate, 98.0)


class MaxHrFromFitTests(unittest.TestCase):
    def test_max_from_records(self):
        peak = max_hr_from_fit_records(
            {"records": [{"heart_rate": 140}, {"heart_rate": 165}]}
        )
        self.assertEqual(peak, 165.0)


class _FakeHrFrame:
    empty = False
    columns = ["heart_rate"]

    def __getitem__(self, _key):
        return self

    def dropna(self):
        return self

    def max(self):
        return 171.0


class StorageBackfillTests(unittest.TestCase):
    def test_max_from_parquet(self):
        storage = MagicMock()
        storage.get_activity_details.return_value = _FakeHrFrame()

        activity = Activity(
            activity_id="10",
            average_heart_rate=156.0,
            max_heart_rate=None,
        )
        result = validate_and_repair_activity(activity, storage=storage)
        self.assertTrue(result.changed)
        self.assertEqual(activity.max_heart_rate, 171.0)


if __name__ == "__main__":
    unittest.main()
