import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine

from app.database.models import Base
from app.database.models.activity import Activity, ActivityRouteFingerprint, ActivityRouteMatch, ActivityType
from app.routers.route_analysis import get_route_matches, list_route_groups, recalculate_routes
from app.services.route_analysis_service import RouteAnalysisService
from app.storage import DataStorage


class RouteAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        from sqlalchemy.orm import sessionmaker

        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.storage = DataStorage(str(Path(self.tmpdir.name) / "data"))
        self.running_type = ActivityType(type_key="running", type_name="Loping")
        self.db.add(self.running_type)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _route(self, offset_lat=0.0, reverse=False):
        points = []
        for i in range(80):
            lat = 59.9200 + offset_lat + i * 0.00002
            lon = 10.7300 + i * 0.00004
            points.append((lat, lon))
        if reverse:
            points = list(reversed(points))
        return points

    def _add_run(self, activity_id, points, start_offset_days=0):
        start = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc) + timedelta(days=start_offset_days)
        self.db.add(
            Activity(
                activity_id=str(activity_id),
                activity_name=f"Run {activity_id}",
                start_time=start,
                distance=9000,
                duration=2700,
                activity_type_id=self.running_type.id,
            )
        )
        self.db.commit()

        records = []
        for idx, (lat, lon) in enumerate(points):
            records.append(
                {
                    "activity_id": int(activity_id),
                    "timestamp": start + timedelta(seconds=idx * 30),
                    "latitude": lat,
                    "longitude": lon,
                    "distance": idx * 110.0,
                    "speed": 3.3,
                    "heart_rate": 150,
                    "cadence": 170,
                    "temperature": 12,
                    "altitude": 100.0,
                }
            )
        self.storage.save_activity_details(records)

    def test_route_analysis_stores_fingerprints_and_same_route_match(self):
        self._add_run(100, self._route(), 0)
        self._add_run(200, self._route(offset_lat=0.00005), 1)

        service = RouteAnalysisService(self.storage)
        first = service.analyze_activity("100", self.db)
        second = service.analyze_activity("200", self.db)

        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "ok")
        self.assertEqual(self.db.query(ActivityRouteFingerprint).count(), 2)

        match = self.db.query(ActivityRouteMatch).one()
        self.assertTrue(match.same_route)
        self.assertGreater(match.similarity_score, 0.5)
        self.assertLess(match.mean_distance_m, 75)

        groups = service.list_route_groups(self.db)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["activityCount"], 2)

    def test_reverse_route_is_detected_but_not_grouped_as_same_direction_route(self):
        self._add_run(100, self._route(), 0)
        self._add_run(200, self._route(reverse=True), 1)

        service = RouteAnalysisService(self.storage)
        service.analyze_activity("100", self.db)
        result = service.analyze_activity("200", self.db)

        match = self.db.query(ActivityRouteMatch).one()
        self.assertTrue(match.reverse_direction)
        self.assertTrue(match.same_route)
        self.assertEqual(result["same_route_count"], 1)

    def test_geographically_different_run_is_not_same_route(self):
        self._add_run(100, self._route(), 0)
        self._add_run(300, self._route(offset_lat=0.02), 1)

        service = RouteAnalysisService(self.storage)
        service.analyze_activity("100", self.db)
        service.analyze_activity("300", self.db)

        match = self.db.query(ActivityRouteMatch).one()
        self.assertFalse(match.same_route)
        self.assertLess(match.similarity_score, 0.5)

    def test_router_endpoints_use_route_service(self):
        self._add_run(100, self._route(), 0)
        self._add_run(200, self._route(offset_lat=0.00005), 1)

        summary = recalculate_routes(
            activity_id=None,
            limit=None,
            service=RouteAnalysisService(self.storage),
            db=self.db,
        )
        self.assertEqual(summary["analyzed"], 2)

        matches = get_route_matches(
            "100",
            same_route_only=True,
            limit=10,
            service=RouteAnalysisService(self.storage),
            db=self.db,
        )
        self.assertEqual(len(matches["matches"]), 1)

        groups = list_route_groups(
            min_activities=2,
            limit=10,
            service=RouteAnalysisService(self.storage),
            db=self.db,
        )
        self.assertEqual(len(groups["groups"]), 1)


if __name__ == "__main__":
    unittest.main()

