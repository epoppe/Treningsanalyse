"""Importer for aktivitetsvær (Frost/MET).

Del av SyncService-oppdelingen: coordinator beholder offentlig API,
denne klassen eier vær-sampling og lagring.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import logging
import math
from typing import Any, Dict, List, Optional

import pandas as pd

from ...database.models.activity import Activity, ActivityRouteFingerprint
from ...database.models.sync_state import SyncState

logger = logging.getLogger(__name__)


class WeatherSyncService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    @property
    def db(self):
        return self.sync_service.db

    @property
    def storage(self):
        return self.sync_service.storage

    @property
    def weather_service(self):
        return self.sync_service.weather_service

    @property
    def frost_weather_service(self):
        return self.sync_service.frost_weather_service

    def activity_weather_altitude(self, activity: Activity) -> Optional[float]:
        values = [
            float(value)
            for value in (activity.min_elevation, activity.max_elevation)
            if value is not None
        ]
        if not values:
            return None
        return sum(values) / len(values)

    def activity_route_fingerprint(self, activity_id: str) -> Optional[ActivityRouteFingerprint]:
        return (
            self.db.query(ActivityRouteFingerprint)
            .filter_by(activity_id=str(activity_id))
            .first()
        )

    def get_activity_details_frame(self, activity_id: str) -> Optional[pd.DataFrame]:
        try:
            try:
                details = self.storage.get_activity_details(int(activity_id))
            except (TypeError, ValueError):
                details = self.storage.get_activity_details(activity_id)  # type: ignore[arg-type]
        except Exception as exc:
            logger.debug(
                "Kunne ikke hente aktivitetsdetaljer for værsampling %s: %s",
                activity_id,
                exc,
            )
            return None

        if details is None or details.empty:
            return None
        return details.copy()

    def build_weather_sample_points(
        self,
        activity: Activity,
        *,
        interval_minutes: int = 15,
    ) -> List[Dict[str, Any]]:
        details = self.get_activity_details_frame(str(activity.activity_id))
        if details is not None and {"timestamp", "latitude", "longitude"}.issubset(details.columns):
            valid = details.dropna(subset=["timestamp", "latitude", "longitude"]).copy()
            if not valid.empty:
                valid["timestamp"] = pd.to_datetime(valid["timestamp"], errors="coerce", utc=True)
                valid = valid.dropna(subset=["timestamp"]).sort_values("timestamp")
                if not valid.empty:
                    detail_points = [
                        {
                            "target_time": row.timestamp.to_pydatetime().astimezone(timezone.utc),
                            "latitude": float(row.latitude),
                            "longitude": float(row.longitude),
                        }
                        for row in valid.itertuples(index=False)
                    ]
                    start_time = detail_points[0]["target_time"]
                    end_time = detail_points[-1]["target_time"]
                    sample_targets: List[datetime] = []
                    current_time = start_time
                    interval = timedelta(minutes=interval_minutes)
                    while current_time <= end_time:
                        sample_targets.append(current_time)
                        current_time += interval
                    if sample_targets and sample_targets[-1] != end_time:
                        sample_targets.append(end_time)
                    elif not sample_targets:
                        sample_targets = [start_time]

                    selected: List[Dict[str, Any]] = []
                    used_keys = set()
                    for target_time in sample_targets:
                        nearest = min(
                            detail_points,
                            key=lambda point: abs(
                                (point["target_time"] - target_time).total_seconds()
                            ),
                        )
                        sample = {
                            "target_time": target_time,
                            "latitude": nearest["latitude"],
                            "longitude": nearest["longitude"],
                        }
                        key = (
                            sample["target_time"].isoformat(),
                            round(sample["latitude"], 5),
                            round(sample["longitude"], 5),
                        )
                        if key in used_keys:
                            continue
                        used_keys.add(key)
                        selected.append(sample)
                    if selected:
                        return selected

        activity_time = activity.start_time
        if activity_time is None:
            return []
        if activity_time.tzinfo is None:
            activity_time = activity_time.replace(tzinfo=timezone.utc)

        route = self.activity_route_fingerprint(str(activity.activity_id))
        if route is not None:
            latitude = route.start_latitude or route.centroid_latitude
            longitude = route.start_longitude or route.centroid_longitude
            if latitude is not None and longitude is not None:
                return [
                    {
                        "target_time": activity_time,
                        "latitude": float(latitude),
                        "longitude": float(longitude),
                    }
                ]

        return []

    async def get_weather_for_sample_point(
        self,
        *,
        target_time: datetime,
        latitude: float,
        longitude: float,
        altitude: Optional[float],
    ) -> Optional[Dict[str, Any]]:
        weather = None
        if self.frost_weather_service.enabled:
            weather = await self.frost_weather_service.get_weather_snapshot(
                target_time=target_time,
                latitude=latitude,
                longitude=longitude,
            )
        if weather is None:
            weather = await self.weather_service.get_weather_snapshot(
                target_time=target_time,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
            )
        return weather

    @staticmethod
    def aggregate_weather_snapshots(
        snapshots: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not snapshots:
            return None

        result: Dict[str, Any] = {}
        for field in ("temperature", "wind_speed", "humidity"):
            values = [
                float(snapshot[field])
                for snapshot in snapshots
                if snapshot.get(field) is not None
            ]
            if values:
                result[field] = sum(values) / len(values)

        directions = [
            float(snapshot["wind_direction"])
            for snapshot in snapshots
            if snapshot.get("wind_direction") is not None
        ]
        if directions:
            if len(directions) == 1:
                result["wind_direction"] = directions[0]
            else:
                sin_sum = sum(math.sin(math.radians(direction)) for direction in directions)
                cos_sum = sum(math.cos(math.radians(direction)) for direction in directions)
                angle = math.degrees(
                    math.atan2(sin_sum / len(directions), cos_sum / len(directions))
                )
                if angle < 0:
                    angle += 360.0
                result["wind_direction"] = angle

        conditions = [
            snapshot.get("weather_condition")
            for snapshot in snapshots
            if snapshot.get("weather_condition")
        ]
        if conditions:
            result["weather_condition"] = Counter(conditions).most_common(1)[0][0]

        return result if result else None

    def apply_garmin_list_weather_if_missing(self, activity: Activity) -> bool:
        """Ingen JSON-fallback: temperatur settes i Activity-kolonner ved sync."""
        return False

    async def sync_activity_weather_for_activity(
        self,
        activity_id: str,
        *,
        force_refresh: bool = False,
    ) -> bool:
        activity = self.db.query(Activity).filter_by(activity_id=str(activity_id)).first()
        if activity is None:
            return False

        has_api_weather = any(
            value is not None
            for value in (
                activity.wind_speed,
                activity.wind_direction,
                activity.humidity,
            )
        )
        has_garmin_temp = activity.temperature is not None
        if (has_api_weather or has_garmin_temp) and not force_refresh:
            return False

        activity_time = activity.start_time
        if activity_time is None:
            logger.debug("Vær hoppet over %s: mangler start_time", activity_id)
            return False
        if activity_time.tzinfo is None:
            activity_time = activity_time.replace(tzinfo=timezone.utc)

        sample_points = self.build_weather_sample_points(activity)
        if not sample_points:
            logger.debug("Vær hoppet over %s: ingen GPS-punkter for sampling", activity_id)
            return self.apply_garmin_list_weather_if_missing(activity)

        snapshots: List[Dict[str, Any]] = []
        altitude = self.activity_weather_altitude(activity)
        for sample in sample_points:
            weather = await self.get_weather_for_sample_point(
                target_time=sample["target_time"],
                latitude=float(sample["latitude"]),
                longitude=float(sample["longitude"]),
                altitude=altitude,
            )
            if weather:
                snapshots.append(weather)

        weather = self.aggregate_weather_snapshots(snapshots)
        changed = False
        if weather:
            for source_key, attr in (
                ("temperature", "temperature"),
                ("wind_speed", "wind_speed"),
                ("wind_direction", "wind_direction"),
                ("humidity", "humidity"),
                ("weather_condition", "weather_condition"),
            ):
                value = weather.get(source_key)
                if value is not None and getattr(activity, attr, None) != value:
                    setattr(activity, attr, value)
                    changed = True
        elif not has_garmin_temp:
            changed = self.apply_garmin_list_weather_if_missing(activity)

        if changed:
            self.db.commit()
        elif not weather and not has_garmin_temp:
            if not self.frost_weather_service.enabled:
                logger.debug(
                    "Vær-API ga ingen data for %s (sett FROST_CLIENT_ID for historisk vær; "
                    "MET locationforecast dekker kun fremtidige tidspunkter)",
                    activity_id,
                )
        return changed

    async def sync_activity_weather(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        ignore_sync_state: bool = False,
    ) -> dict:
        effective_start = start_date
        if not ignore_sync_state:
            try:
                state = self.db.query(SyncState).filter_by(key="activity_weather").first()
                if state and state.last_synced_date and not force_refresh_recent:
                    effective_start = max(
                        effective_start,
                        datetime.combine(
                            state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc
                        )
                        + timedelta(days=1),
                    )
            except Exception as exc:
                logger.debug("Kunne ikke lese SyncState for activity_weather: %s", exc)

        if effective_start > end_date:
            return {
                "status": "Fullført",
                "updated_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
            }

        activities = (
            self.db.query(Activity)
            .filter(Activity.start_time >= effective_start, Activity.start_time <= end_date)
            .order_by(Activity.start_time.asc())
            .all()
        )

        updated_count = 0
        skipped_count = 0
        failed_count = 0
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)

        for activity in activities:
            activity_time = activity.start_time
            if activity_time is None:
                skipped_count += 1
                continue
            if activity_time.tzinfo is None:
                activity_time = activity_time.replace(tzinfo=timezone.utc)
            is_recent = activity_time >= recent_cutoff
            has_weather = any(
                value is not None
                for value in (
                    activity.temperature,
                    activity.wind_speed,
                    activity.wind_direction,
                    activity.weather_condition,
                )
            )
            if has_weather and not (force_refresh_recent and is_recent):
                skipped_count += 1
                continue

            try:
                changed = await self.sync_activity_weather_for_activity(
                    str(activity.activity_id),
                    force_refresh=force_refresh_recent and is_recent,
                )
                if changed:
                    updated_count += 1
                else:
                    skipped_count += 1
            except Exception as exc:
                logger.warning(
                    "Kunne ikke synkronisere vær for aktivitet %s: %s",
                    activity.activity_id,
                    exc,
                )
                failed_count += 1

        try:
            state = self.db.query(SyncState).filter_by(key="activity_weather").first()
            if not state:
                state = SyncState(key="activity_weather")
                self.db.add(state)
            state.last_synced_date = end_date.date()
            state.last_synced_at = datetime.now(timezone.utc)
            self.db.commit()
        except Exception as exc:
            logger.warning("Kunne ikke oppdatere SyncState for activity_weather: %s", exc)

        return {
            "status": "Fullført",
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "period": {"start": str(effective_start.date()), "end": str(end_date.date())},
        }
