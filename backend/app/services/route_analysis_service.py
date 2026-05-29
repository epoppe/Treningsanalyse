from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
import math
from typing import Any, Optional

import numpy as np
import pandas as pd
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database.models.activity import Activity, ActivityRouteFingerprint, ActivityRouteMatch
from ..storage import DataStorage
from ..utils.activity_filters import apply_running_activity_filter

logger = logging.getLogger(__name__)

METHOD_VERSION = "route-match-v1"
SAMPLE_POINTS = 100
MIN_GPS_POINTS = 20
MAX_MEAN_DISTANCE_M = 75.0
MAX_P90_DISTANCE_M = 150.0
MAX_ENDPOINT_DISTANCE_M = 250.0
MAX_DISTANCE_RATIO = 0.08


@dataclass
class RouteComparison:
    same_route: bool
    similarity_score: float
    reverse_direction: bool
    mean_distance_m: float
    p90_distance_m: float
    start_distance_m: float
    end_distance_m: float
    distance_ratio: float
    overlap_quality: float


class RouteAnalysisService:
    """Analyserer GPS-spor fra FIT/parquet og lagrer sammenlignbare løperuter."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def analyze_activity(self, activity_id: str | int, db: Session) -> dict[str, Any]:
        activity = db.query(Activity).filter_by(activity_id=str(activity_id)).first()
        if not activity:
            return {"status": "not_found", "activity_id": str(activity_id)}

        fingerprint = self._build_fingerprint(activity)
        if fingerprint is None:
            self._delete_route_analysis(str(activity.activity_id), db)
            db.commit()
            return {
                "status": "skipped",
                "activity_id": str(activity.activity_id),
                "reason": "missing_or_low_quality_gps",
            }

        stored_fingerprint = self._upsert_fingerprint(activity, fingerprint, db)
        comparisons = self._compare_with_existing(stored_fingerprint, db)
        group_key = self._assign_route_group(stored_fingerprint, comparisons, db)
        db.commit()

        same_route_count = sum(1 for comparison in comparisons if comparison["same_route"])
        return {
            "status": "ok",
            "activity_id": str(activity.activity_id),
            "route_group_key": group_key,
            "same_route_count": same_route_count,
            "comparison_count": len(comparisons),
            "quality_score": stored_fingerprint.quality_score,
        }

    def analyze_all_running_routes(self, db: Session, limit: Optional[int] = None) -> dict[str, Any]:
        query = apply_running_activity_filter(db.query(Activity).order_by(Activity.start_time.asc()))
        if limit:
            query = query.limit(limit)
        activities = query.all()

        results = []
        for activity in activities:
            try:
                results.append(self.analyze_activity(activity.activity_id, db))
            except Exception as exc:
                logger.warning("Ruteanalyse feilet for aktivitet %s: %s", activity.activity_id, exc)
                db.rollback()
                results.append(
                    {
                        "status": "error",
                        "activity_id": str(activity.activity_id),
                        "message": str(exc),
                    }
                )

        return {
            "status": "ok",
            "total_activities": len(activities),
            "analyzed": sum(1 for result in results if result["status"] == "ok"),
            "skipped": sum(1 for result in results if result["status"] == "skipped"),
            "errors": sum(1 for result in results if result["status"] == "error"),
            "results": results,
        }

    def get_activity_matches(
        self,
        activity_id: str | int,
        db: Session,
        *,
        same_route_only: bool = True,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        activity_id_str = str(activity_id)
        query = db.query(ActivityRouteMatch).filter(
            or_(
                ActivityRouteMatch.activity_id == activity_id_str,
                ActivityRouteMatch.matched_activity_id == activity_id_str,
            )
        )
        if same_route_only:
            query = query.filter(ActivityRouteMatch.same_route.is_(True))

        matches = query.order_by(ActivityRouteMatch.similarity_score.desc()).limit(limit).all()
        activity_ids = {
            match.matched_activity_id if match.activity_id == activity_id_str else match.activity_id
            for match in matches
        }
        activities = {
            activity.activity_id: activity
            for activity in db.query(Activity).filter(Activity.activity_id.in_(activity_ids)).all()
        }

        payload = []
        for match in matches:
            other_id = match.matched_activity_id if match.activity_id == activity_id_str else match.activity_id
            other_activity = activities.get(other_id)
            payload.append(
                {
                    "activityId": other_id,
                    "activityName": other_activity.activity_name if other_activity else None,
                    "startTime": other_activity.start_time.isoformat() if other_activity and other_activity.start_time else None,
                    "distance": other_activity.distance if other_activity else None,
                    "sameRoute": match.same_route,
                    "similarityScore": match.similarity_score,
                    "reverseDirection": match.reverse_direction,
                    "meanDistanceM": match.mean_distance_m,
                    "p90DistanceM": match.p90_distance_m,
                    "startDistanceM": match.start_distance_m,
                    "endDistanceM": match.end_distance_m,
                    "distanceRatio": match.distance_ratio,
                    "overlapQuality": match.overlap_quality,
                }
            )
        return payload

    def list_route_groups(
        self,
        db: Session,
        *,
        min_activities: int = 2,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows = (
            db.query(ActivityRouteFingerprint)
            .filter(ActivityRouteFingerprint.route_group_key.isnot(None))
            .all()
        )
        grouped: dict[str, list[ActivityRouteFingerprint]] = {}
        for row in rows:
            grouped.setdefault(row.route_group_key, []).append(row)

        activity_ids = [row.activity_id for group_rows in grouped.values() for row in group_rows]
        activities = {
            activity.activity_id: activity
            for activity in db.query(Activity).filter(Activity.activity_id.in_(activity_ids)).all()
        }

        groups = []
        for group_key, group_rows in grouped.items():
            if len(group_rows) < min_activities:
                continue
            group_activities = [activities.get(row.activity_id) for row in group_rows]
            group_activities = [activity for activity in group_activities if activity is not None]
            group_activities.sort(key=lambda activity: activity.start_time or datetime.min, reverse=True)
            groups.append(
                {
                    "routeGroupKey": group_key,
                    "activityCount": len(group_rows),
                    "latestStartTime": group_activities[0].start_time.isoformat() if group_activities and group_activities[0].start_time else None,
                    "activities": [
                        {
                            "activityId": activity.activity_id,
                            "activityName": activity.activity_name,
                            "startTime": activity.start_time.isoformat() if activity.start_time else None,
                            "distance": activity.distance,
                        }
                        for activity in group_activities[:10]
                    ],
                }
            )

        groups.sort(key=lambda group: (group["activityCount"], group["latestStartTime"] or ""), reverse=True)
        return groups[:limit]

    def _build_fingerprint(self, activity: Activity) -> Optional[dict[str, Any]]:
        try:
            details = self.storage.get_activity_details(int(activity.activity_id))
        except (TypeError, ValueError):
            details = self.storage.get_activity_details(activity.activity_id)  # type: ignore[arg-type]

        if details is None or details.empty or not {"latitude", "longitude"}.issubset(details.columns):
            return None

        points_df = details[["latitude", "longitude", "distance"] if "distance" in details.columns else ["latitude", "longitude"]].copy()
        points_df = points_df.dropna(subset=["latitude", "longitude"])
        points_df = points_df[
            points_df["latitude"].between(-90, 90) & points_df["longitude"].between(-180, 180)
        ]
        if len(points_df) < MIN_GPS_POINTS:
            return None

        coords = points_df[["latitude", "longitude"]].to_numpy(dtype=float)
        sampled = self._sample_points_by_distance(coords, SAMPLE_POINTS)
        route_distance = self._route_distance(activity, points_df, coords)
        route_hash = self._route_hash(sampled)
        quality_score = min(1.0, len(coords) / 200.0)

        return {
            "point_count": len(details),
            "gps_point_count": len(coords),
            "sampled_point_count": len(sampled),
            "route_distance_m": route_distance,
            "start_latitude": float(coords[0][0]),
            "start_longitude": float(coords[0][1]),
            "end_latitude": float(coords[-1][0]),
            "end_longitude": float(coords[-1][1]),
            "centroid_latitude": float(np.mean(coords[:, 0])),
            "centroid_longitude": float(np.mean(coords[:, 1])),
            "bbox_min_latitude": float(np.min(coords[:, 0])),
            "bbox_min_longitude": float(np.min(coords[:, 1])),
            "bbox_max_latitude": float(np.max(coords[:, 0])),
            "bbox_max_longitude": float(np.max(coords[:, 1])),
            "quality_score": quality_score,
            "route_hash": route_hash,
            "sampled_points": [[round(float(lat), 7), round(float(lon), 7)] for lat, lon in sampled],
            "calculated_at": datetime.now(timezone.utc),
            "method_version": METHOD_VERSION,
        }

    def _upsert_fingerprint(self, activity: Activity, data: dict[str, Any], db: Session) -> ActivityRouteFingerprint:
        row = db.query(ActivityRouteFingerprint).filter_by(activity_id=str(activity.activity_id)).first()
        if row is None:
            row = ActivityRouteFingerprint(activity_id=str(activity.activity_id))
            db.add(row)

        existing_group_key = row.route_group_key
        for key, value in data.items():
            setattr(row, key, value)
        row.route_group_key = existing_group_key
        db.flush()
        return row

    def _compare_with_existing(self, fingerprint: ActivityRouteFingerprint, db: Session) -> list[dict[str, Any]]:
        existing = (
            db.query(ActivityRouteFingerprint)
            .filter(ActivityRouteFingerprint.activity_id != fingerprint.activity_id)
            .filter(ActivityRouteFingerprint.sampled_points.isnot(None))
            .all()
        )
        comparisons = []
        for other in existing:
            comparison = self._compare_fingerprints(fingerprint, other)
            self._upsert_match(fingerprint.activity_id, other.activity_id, comparison, db)
            comparisons.append({"activity_id": other.activity_id, **comparison.__dict__})
        db.flush()
        return comparisons

    def _compare_fingerprints(
        self,
        first: ActivityRouteFingerprint,
        second: ActivityRouteFingerprint,
    ) -> RouteComparison:
        first_points = np.array(first.sampled_points or [], dtype=float)
        second_points = np.array(second.sampled_points or [], dtype=float)
        if len(first_points) == 0 or len(second_points) == 0:
            return RouteComparison(False, 0.0, False, math.inf, math.inf, math.inf, math.inf, math.inf, 0.0)

        count = min(len(first_points), len(second_points))
        first_points = self._sample_points(first_points, count)
        second_points = self._sample_points(second_points, count)

        forward = self._point_distances_m(first_points, second_points)
        reverse = self._point_distances_m(first_points, second_points[::-1])
        use_reverse = float(np.mean(reverse)) < float(np.mean(forward))
        distances = reverse if use_reverse else forward

        mean_distance = float(np.mean(distances))
        p90_distance = float(np.percentile(distances, 90))
        if use_reverse:
            start_distance = self._haversine_m(first_points[0], second_points[-1])
            end_distance = self._haversine_m(first_points[-1], second_points[0])
        else:
            start_distance = self._haversine_m(first_points[0], second_points[0])
            end_distance = self._haversine_m(first_points[-1], second_points[-1])

        first_distance = first.route_distance_m or 0.0
        second_distance = second.route_distance_m or 0.0
        max_distance = max(first_distance, second_distance, 1.0)
        distance_ratio = abs(first_distance - second_distance) / max_distance
        overlap_quality = max(0.0, 1.0 - (p90_distance / MAX_P90_DISTANCE_M))
        score = self._similarity_score(mean_distance, p90_distance, max(start_distance, end_distance), distance_ratio)
        same_route = (
            mean_distance <= MAX_MEAN_DISTANCE_M
            and p90_distance <= MAX_P90_DISTANCE_M
            and start_distance <= MAX_ENDPOINT_DISTANCE_M
            and end_distance <= MAX_ENDPOINT_DISTANCE_M
            and distance_ratio <= MAX_DISTANCE_RATIO
        )

        return RouteComparison(
            same_route=same_route,
            similarity_score=score,
            reverse_direction=use_reverse,
            mean_distance_m=mean_distance,
            p90_distance_m=p90_distance,
            start_distance_m=float(start_distance),
            end_distance_m=float(end_distance),
            distance_ratio=float(distance_ratio),
            overlap_quality=float(overlap_quality),
        )

    def _upsert_match(self, first_id: str, second_id: str, comparison: RouteComparison, db: Session) -> None:
        activity_id, matched_activity_id = sorted([str(first_id), str(second_id)])
        row = (
            db.query(ActivityRouteMatch)
            .filter_by(activity_id=activity_id, matched_activity_id=matched_activity_id)
            .first()
        )
        if row is None:
            row = ActivityRouteMatch(activity_id=activity_id, matched_activity_id=matched_activity_id)
            db.add(row)

        row.same_route = comparison.same_route
        row.similarity_score = comparison.similarity_score
        row.reverse_direction = comparison.reverse_direction
        row.mean_distance_m = comparison.mean_distance_m
        row.p90_distance_m = comparison.p90_distance_m
        row.start_distance_m = comparison.start_distance_m
        row.end_distance_m = comparison.end_distance_m
        row.distance_ratio = comparison.distance_ratio
        row.overlap_quality = comparison.overlap_quality
        row.calculated_at = datetime.now(timezone.utc)
        row.method_version = METHOD_VERSION

    def _assign_route_group(
        self,
        fingerprint: ActivityRouteFingerprint,
        comparisons: list[dict[str, Any]],
        db: Session,
    ) -> str:
        same_route_ids = [comparison["activity_id"] for comparison in comparisons if comparison["same_route"]]
        if not same_route_ids:
            fingerprint.route_group_key = f"route:{fingerprint.activity_id}"
            db.flush()
            return fingerprint.route_group_key

        matched_fingerprints = (
            db.query(ActivityRouteFingerprint)
            .filter(ActivityRouteFingerprint.activity_id.in_(same_route_ids))
            .all()
        )
        existing_keys = sorted({row.route_group_key for row in matched_fingerprints if row.route_group_key})
        group_key = existing_keys[0] if existing_keys else f"route:{min([fingerprint.activity_id] + same_route_ids)}"

        fingerprint.route_group_key = group_key
        for row in matched_fingerprints:
            row.route_group_key = group_key

        for stale_key in existing_keys[1:]:
            db.query(ActivityRouteFingerprint).filter_by(route_group_key=stale_key).update(
                {"route_group_key": group_key},
                synchronize_session=False,
            )

        db.flush()
        return group_key

    def _delete_route_analysis(self, activity_id: str, db: Session) -> None:
        db.query(ActivityRouteMatch).filter(
            or_(
                ActivityRouteMatch.activity_id == activity_id,
                ActivityRouteMatch.matched_activity_id == activity_id,
            )
        ).delete(synchronize_session=False)
        db.query(ActivityRouteFingerprint).filter_by(activity_id=activity_id).delete(synchronize_session=False)

    def _route_distance(self, activity: Activity, points_df: pd.DataFrame, coords: np.ndarray) -> Optional[float]:
        if activity.distance:
            return float(activity.distance)
        if "distance" in points_df.columns and points_df["distance"].notna().any():
            distances = points_df["distance"].dropna()
            if not distances.empty:
                return float(distances.max() - distances.min())
        if len(coords) < 2:
            return None
        return float(np.sum(self._point_distances_m(coords[:-1], coords[1:])))

    def _route_hash(self, sampled: np.ndarray) -> str:
        normalized = ";".join(f"{lat:.4f},{lon:.4f}" for lat, lon in sampled)
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    def _sample_points(self, points: np.ndarray, count: int) -> np.ndarray:
        if len(points) <= count:
            return points
        indexes = np.linspace(0, len(points) - 1, count).round().astype(int)
        return points[indexes]

    def _sample_points_by_distance(self, points: np.ndarray, count: int) -> np.ndarray:
        if len(points) <= count:
            return points

        segment_distances = self._point_distances_m(points[:-1], points[1:])
        cumulative = np.concatenate(([0.0], np.cumsum(segment_distances)))
        total_distance = cumulative[-1]
        if total_distance <= 0:
            return self._sample_points(points, count)

        targets = np.linspace(0.0, total_distance, count)
        sampled_lat = np.interp(targets, cumulative, points[:, 0])
        sampled_lon = np.interp(targets, cumulative, points[:, 1])
        return np.column_stack((sampled_lat, sampled_lon))

    def _point_distances_m(self, first: np.ndarray, second: np.ndarray) -> np.ndarray:
        lat1 = np.radians(first[:, 0])
        lon1 = np.radians(first[:, 1])
        lat2 = np.radians(second[:, 0])
        lon2 = np.radians(second[:, 1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        return 6371000.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    def _haversine_m(self, first: np.ndarray, second: np.ndarray) -> float:
        return float(self._point_distances_m(np.array([first]), np.array([second]))[0])

    def _similarity_score(
        self,
        mean_distance_m: float,
        p90_distance_m: float,
        endpoint_distance_m: float,
        distance_ratio: float,
    ) -> float:
        mean_score = max(0.0, 1.0 - mean_distance_m / MAX_MEAN_DISTANCE_M)
        p90_score = max(0.0, 1.0 - p90_distance_m / MAX_P90_DISTANCE_M)
        endpoint_score = max(0.0, 1.0 - endpoint_distance_m / MAX_ENDPOINT_DISTANCE_M)
        distance_score = max(0.0, 1.0 - distance_ratio / MAX_DISTANCE_RATIO)
        return round((0.45 * mean_score + 0.25 * p90_score + 0.15 * endpoint_score + 0.15 * distance_score), 4)
