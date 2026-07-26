"""Tester for metrikk-avhengighetsgraf og cache-invalidation."""

from __future__ import annotations

import unittest

from app.cache.cache_manager import CacheManager
from app.metrics.dependency_graph import (
    INPUT_NODES,
    METRIC_DEPENDENCIES,
    METRIC_TO_CACHE_TYPE,
    cache_types_for_metrics,
    dependents_of,
    invalidate_plan_for_changed_inputs,
    topological_metrics,
)
from app.services.metric_provenance_service import ALGORITHM_VERSIONS


class DependencyGraphTests(unittest.TestCase):
    def test_all_provenance_metrics_are_in_graph(self):
        missing = set(ALGORITHM_VERSIONS) - set(METRIC_DEPENDENCIES)
        self.assertEqual(missing, set(), msg=f"Mangler i graf: {missing}")

    def test_deps_reference_known_nodes(self):
        known = set(INPUT_NODES) | set(METRIC_DEPENDENCIES)
        for metric, deps in METRIC_DEPENDENCIES.items():
            unknown = set(deps) - known
            self.assertEqual(
                unknown,
                set(),
                msg=f"{metric} har ukjente deps: {unknown}",
            )

    def test_fit_series_change_affects_power_and_splits(self):
        affected = dependents_of(["fit_series"])
        self.assertIn("average_power", affected)
        self.assertIn("negative_split_percent", affected)
        self.assertIn("decoupling_percent", affected)
        self.assertIn("avg_efficiency_factor", affected)

    def test_epoc_change_affects_tss(self):
        affected = dependents_of(["epoc"])
        self.assertEqual(affected, {"training_stress_score"})

    def test_power_change_cascades_to_ef(self):
        affected = dependents_of(["average_power"])
        self.assertIn("avg_efficiency_factor", affected)

    def test_invalidate_plan(self):
        plan = invalidate_plan_for_changed_inputs(["epoc", "fit_series"])
        self.assertIn("training_stress_score", plan["metrics_to_recompute"])
        self.assertIn("tss", plan["cache_types_to_invalidate"])
        self.assertIn("power", plan["cache_types_to_invalidate"])

    def test_topological_order_places_power_before_ef(self):
        order = topological_metrics()
        self.assertLess(order.index("average_power"), order.index("avg_efficiency_factor"))

    def test_cache_types_for_metrics(self):
        self.assertEqual(
            cache_types_for_metrics(["training_stress_score", "running_economy"]),
            {"tss"},
        )
        self.assertEqual(set(METRIC_TO_CACHE_TYPE), {"training_stress_score", "average_power"})


class CacheInvalidateActivityTests(unittest.TestCase):
    def test_invalidate_memory_tss_and_power(self):
        mgr = CacheManager(max_size=10, use_redis=False)
        mgr.set_tss("42", 100.0)
        mgr.set_power("42", {"average_power": 250})
        mgr.set_tss("99", 50.0)

        result = mgr.invalidate_activity("42")
        self.assertTrue(result["tss"])
        self.assertTrue(result["power"])
        self.assertIsNone(mgr.get_tss("42"))
        self.assertIsNone(mgr.get_power("42"))
        self.assertEqual(mgr.get_tss("99"), 50.0)

    def test_invalidate_only_tss(self):
        mgr = CacheManager(max_size=10, use_redis=False)
        mgr.set_tss("1", 10.0)
        mgr.set_power("1", {"average_power": 200})
        mgr.invalidate_activity("1", cache_types=["tss"])
        self.assertIsNone(mgr.get_tss("1"))
        self.assertIsNotNone(mgr.get_power("1"))


if __name__ == "__main__":
    unittest.main()
