import unittest

from app.mcp import training_tools


class MetricCatalogUnitTests(unittest.TestCase):
    def test_duration_not_percent(self):
        self.assertEqual(training_tools._infer_metric_unit("duration"), "s")
        self.assertEqual(training_tools._infer_metric_unit("total_duration"), "s")
        self.assertEqual(training_tools._infer_metric_unit("best_duration"), "s")
        self.assertEqual(training_tools._infer_metric_unit("elapsed_duration"), "s")
        self.assertEqual(training_tools._infer_metric_unit("moving_duration"), "s")
        self.assertEqual(training_tools._infer_metric_unit("duration_per_day"), "s")

    def test_duration_trend_is_percent(self):
        self.assertEqual(training_tools._infer_metric_unit("duration_trend"), "%")

    def test_ground_contact_time_is_ms(self):
        self.assertEqual(training_tools._infer_metric_unit("ground_contact_time"), "ms")

    def test_ratio_suffix_still_percent(self):
        self.assertEqual(training_tools._infer_metric_unit("vertical_ratio"), "%")
        self.assertEqual(training_tools._infer_metric_unit("distance_ratio"), "%")

    def test_catalog_activity_duration_unit(self):
        unit = training_tools.METRIC_CATALOG["activity.duration"]["unit"]
        self.assertEqual(unit, "s")

    def test_catalog_ground_contact_unit(self):
        unit = training_tools.METRIC_CATALOG["activity.ground_contact_time"]["unit"]
        self.assertEqual(unit, "ms")


if __name__ == "__main__":
    unittest.main()
