import unittest

from app.services.metric_evidence import MetricEvidence, attach_evidence, confidence_from_sample_count


class MetricEvidenceTests(unittest.TestCase):
    def test_clamps_confidence(self):
        evidence = MetricEvidence.wrap(42.0, source_type="heuristic", confidence=1.5)
        self.assertEqual(evidence.confidence, 1.0)

    def test_to_dict_rounds_confidence(self):
        evidence = MetricEvidence.wrap(
            55.0,
            source_type="derived",
            confidence=0.6789,
            sample_count=10,
            method="stable_easy_runs",
            limitations=["not_measured"],
        )
        payload = evidence.to_dict()
        self.assertEqual(payload["value"], 55.0)
        self.assertEqual(payload["source_type"], "derived")
        self.assertEqual(payload["confidence"], 0.679)
        self.assertEqual(payload["limitations"], ["not_measured"])

    def test_attach_evidence_preserves_value(self):
        payload = {"score": 80}
        attach_evidence(
            payload,
            "score",
            MetricEvidence.wrap(80, source_type="garmin", confidence=0.9, sample_count=1),
        )
        self.assertEqual(payload["score"], 80)
        self.assertIn("evidence", payload)

    def test_confidence_from_sample_count(self):
        self.assertEqual(confidence_from_sample_count(0), 0.0)
        self.assertGreater(confidence_from_sample_count(3), 0.4)
        self.assertEqual(confidence_from_sample_count(14), 1.0)


if __name__ == "__main__":
    unittest.main()
