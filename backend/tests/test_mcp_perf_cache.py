"""Tester for ytelses-cachene i PPAP/MCP: load-serie bygges én gang per vindu."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Activity, ActivityType
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.mcp_derived_metrics_service import McpDerivedMetricsService


class LoadSeriesCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{self._tmp.name}/t.db")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        rt = ActivityType(type_key="running", type_name="Running")
        self.db.add(rt)
        self.db.flush()
        base = datetime.now(timezone.utc)
        for i in range(20):
            d = base - timedelta(days=i * 2)
            self.db.add(Activity(
                activity_id=f"T-{i}", activity_name=f"Run {i}", start_time=d,
                duration=3000, distance=10000, epoc=70 + i, activity_type_id=rt.id,
            ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def _spy_build(self, ppap):
        calls = {"n": 0}
        original = ppap._build_load_series

        def wrapper(start_date, end_date):
            calls["n"] += 1
            return original(start_date, end_date)

        ppap._build_load_series = wrapper
        return calls

    def test_prime_then_lookups_build_once(self):
        ppap = PpapMetricsService(self.db)
        calls = self._spy_build(ppap)
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=29)
        ppap.prime_load_series(start, end)
        self.assertEqual(calls["n"], 1)
        # Alle daglige oppslag i vinduet skal gjenbruke serien (ingen ny bygging)
        day = start
        while day <= end:
            ppap.get_ctl(day)
            ppap.get_atl(day)
            ppap.get_tsb(day)
            day += timedelta(days=1)
        self.assertEqual(calls["n"], 1)

    def test_ensure_rebuilds_only_outside_covered_range(self):
        ppap = PpapMetricsService(self.db)
        calls = self._spy_build(ppap)
        end = datetime.now(timezone.utc).date()
        ppap.ensure_load_series(end)
        self.assertEqual(calls["n"], 1)
        # Innenfor dekket område: ingen ny bygging
        ppap.ensure_load_series(end - timedelta(days=10))
        self.assertEqual(calls["n"], 1)
        # Langt utenfor dekket område (eldre enn warmup): ny bygging
        ppap.ensure_load_series(end - timedelta(days=ppap.LOAD_WARMUP_DAYS + 5))
        self.assertEqual(calls["n"], 2)

    def test_daily_timeseries_primes_load_series_once(self):
        service = McpDerivedMetricsService(self.db, None)
        calls = self._spy_build(service._ppap)
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=29)
        res = service.query_timeseries("fitness.tsb", start_date=start, end_date=end, limit=30)
        self.assertEqual(res["status"], "ok")
        # Hele 30-dagers tidsserien skal bygge load-serien nøyaktig én gang
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
