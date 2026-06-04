from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import asyncio
import logging
import re
import zipfile
import io
import xml.etree.ElementTree as ET

import polars as pl
from dateutil import parser as date_parser
from fitparse import FitFile
from sqlalchemy import and_

from ...database.models.activity import Activity
from ...services.route_analysis_service import RouteAnalysisService
from ...services.activity_data_validation import (
    max_hr_from_fit_records,
    validate_and_repair_activity,
)
from ...config import data_path

logger = logging.getLogger(__name__)


class FitSyncService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    def extract_numeric_value(self, value) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r"[-+]?(?:\d*\.\d+|\d+)", value)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
        return None

    def parse_fit_data(self, fit_data: bytes) -> Optional[dict]:
        if not fit_data:
            return None
        try:
            if fit_data.startswith(b"PK"):
                logger.info("FIT-data er en ZIP-fil, ekstrakterer FIT-fil...")
                try:
                    with zipfile.ZipFile(io.BytesIO(fit_data), "r") as zip_file:
                        fit_files = [name for name in zip_file.namelist() if name.lower().endswith(".fit")]
                        tcx_files = [name for name in zip_file.namelist() if name.lower().endswith(".tcx")]
                        if not fit_files and tcx_files:
                            tcx_filename = tcx_files[0]
                            logger.info(f"Ekstrakterer TCX-fil: {tcx_filename}")
                            return self.parse_tcx_data(zip_file.read(tcx_filename))
                        if not fit_files:
                            logger.warning("Ingen FIT- eller TCX-fil funnet i ZIP-arkivet")
                            return None
                        fit_filename = fit_files[0]
                        logger.info(f"Ekstrakterer FIT-fil: {fit_filename}")
                        fit_data = zip_file.read(fit_filename)
                except zipfile.BadZipFile:
                    logger.warning("Kunne ikke åpne som ZIP-fil, prøver som rå FIT-data")
                except Exception as exc:
                    logger.error(f"Feil ved ekstraksjon av ZIP-fil: {exc}")
                    return None

            fitfile = FitFile(io.BytesIO(fit_data))
            records = []
            total_ascent = None
            total_descent = None
            session_max_hr = None
            session_min_hr = None

            for message in fitfile.get_messages("session"):
                for field in message.fields:
                    if field.name == "total_ascent":
                        total_ascent = field.value
                    elif field.name == "total_descent":
                        total_descent = field.value
                    elif field.name == "max_heart_rate":
                        session_max_hr = self.extract_numeric_value(field.value)
                    elif field.name == "min_heart_rate":
                        session_min_hr = self.extract_numeric_value(field.value)

            for record in fitfile.get_messages("record"):
                parsed_record = {}
                for field in record.fields:
                    value = field.value
                    if field.name in ["position_lat", "position_long"] and value is not None:
                        value = value * (180 / (2**31))
                    elif hasattr(value, "isoformat"):
                        value = value.isoformat()
                    parsed_record[field.name] = value
                records.append(parsed_record)

            result = {"records": records}
            if total_ascent is not None:
                result["total_ascent"] = total_ascent
            if total_descent is not None:
                result["total_descent"] = total_descent
            if session_max_hr is not None:
                result["max_heart_rate"] = session_max_hr
            if session_min_hr is not None:
                result["min_heart_rate"] = session_min_hr

            logger.info(
                f"Parsed {len(records)} FIT-records, total_ascent={total_ascent}, total_descent={total_descent}"
            )
            return result
        except ImportError:
            logger.error("fitparse-biblioteket er ikke installert. Kan ikke parse FIT-data.")
            return None

    def parse_tcx_data(self, tcx_data: bytes) -> Optional[dict]:
        if not tcx_data:
            return None
        try:
            root = ET.fromstring(tcx_data)
            records = []
            total_ascent = 0.0
            total_descent = 0.0
            previous_altitude = None

            def local_name(tag: str) -> str:
                return tag.rsplit("}", 1)[-1]

            def child_text(element, name: str) -> Optional[str]:
                for child in list(element):
                    if local_name(child.tag) == name:
                        return child.text
                return None

            def nested_text(element, path: list[str]) -> Optional[str]:
                current = element
                for part in path:
                    current = next((child for child in list(current) if local_name(child.tag) == part), None)
                    if current is None:
                        return None
                return current.text

            for trackpoint in root.iter():
                if local_name(trackpoint.tag) != "Trackpoint":
                    continue
                timestamp = child_text(trackpoint, "Time")
                latitude = nested_text(trackpoint, ["Position", "LatitudeDegrees"])
                longitude = nested_text(trackpoint, ["Position", "LongitudeDegrees"])
                if not timestamp:
                    continue

                altitude = child_text(trackpoint, "AltitudeMeters")
                altitude_value = self.extract_numeric_value(altitude)
                if previous_altitude is not None and altitude_value is not None:
                    diff = altitude_value - previous_altitude
                    if diff > 0:
                        total_ascent += diff
                    elif diff < 0:
                        total_descent += abs(diff)
                if altitude_value is not None:
                    previous_altitude = altitude_value

                record = {
                    "timestamp": timestamp,
                    "position_lat": self.extract_numeric_value(latitude),
                    "position_long": self.extract_numeric_value(longitude),
                    "distance": self.extract_numeric_value(child_text(trackpoint, "DistanceMeters")),
                    "enhanced_altitude": altitude_value,
                    "heart_rate": self.extract_numeric_value(nested_text(trackpoint, ["HeartRateBpm", "Value"])),
                    "cadence": self.extract_numeric_value(child_text(trackpoint, "Cadence")),
                }
                records.append(record)

            result = {"records": records}
            if total_ascent > 0:
                result["total_ascent"] = total_ascent
            if total_descent > 0:
                result["total_descent"] = total_descent
            logger.info("Parsed %s TCX-trackpoints, total_ascent=%s, total_descent=%s", len(records), total_ascent, total_descent)
            return result
        except Exception as exc:
            logger.warning("Kunne ikke parse TCX-data: %s", exc)
            return None
        except BaseException as exc:
            logger.warning(f"Kunne ikke parse FIT-data: {exc}")
            return None

    def _to_parquet_records(self, activity_id: int, details_json: dict) -> list[dict]:
        parquet_records = []
        for record in details_json.get("records", []):
            timestamp = record.get("timestamp")
            if timestamp:
                if isinstance(timestamp, str):
                    timestamp = date_parser.parse(timestamp)
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                elif hasattr(timestamp, "tzinfo") and timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                elif not hasattr(timestamp, "tzinfo"):
                    timestamp = datetime.fromisoformat(str(timestamp)).replace(tzinfo=timezone.utc)

            parquet_record = {
                "activity_id": int(activity_id),
                "timestamp": timestamp,
                "latitude": self.extract_numeric_value(record.get("position_lat")),
                "longitude": self.extract_numeric_value(record.get("position_long")),
                "distance": self.extract_numeric_value(record.get("distance")),
                "speed": self.extract_numeric_value(record.get("enhanced_speed") or record.get("speed")),
                "heart_rate": self.extract_numeric_value(record.get("heart_rate")),
                "cadence": self.extract_numeric_value(record.get("cadence")),
                "temperature": self.extract_numeric_value(record.get("temperature")),
                "altitude": self.extract_numeric_value(record.get("enhanced_altitude") or record.get("altitude")),
            }
            if parquet_record["timestamp"] is not None:
                parquet_records.append(parquet_record)
        return parquet_records

    @staticmethod
    def _aggregate_metrics_counts(metrics_calculated: dict, metrics_result: dict | None) -> None:
        if not metrics_result:
            return
        if metrics_result.get("negative_split_calculated"):
            metrics_calculated["negative_split"] += 1
        if metrics_result.get("decoupling_calculated"):
            metrics_calculated["decoupling"] += 1
        if metrics_result.get("hrv_calculated"):
            metrics_calculated["hrv_available"] += 1

    async def download_and_store_fit_file(self, activity_id: int) -> tuple[bool, dict | None]:
        try:
            logger.info(f"Laster ned FIT-data for aktivitet {activity_id}...")
            fit_data = await self.sync_service.garmin_client.get_activity_details(activity_id)
            if not fit_data:
                logger.warning(f"Ingen FIT-data tilgjengelig for aktivitet {activity_id}")
                return False, None

            details_json = self.parse_fit_data(fit_data)
            if not details_json or "records" not in details_json:
                logger.warning(f"Kunne ikke parse FIT-data for aktivitet {activity_id}")
                return False, None

            parquet_records = self._to_parquet_records(activity_id, details_json)
            if not parquet_records:
                logger.warning(f"Ingen gyldige FIT-records funnet for aktivitet {activity_id}")
                return False, None

            self.sync_service.storage.save_activity_details(parquet_records)
            logger.info(f"Lagret {len(parquet_records)} FIT-records for aktivitet {activity_id}")

            metrics_result = None
            activity = self.sync_service.db.query(Activity).filter_by(activity_id=activity_id).first()
            if activity:
                activity.detailed_metrics = details_json
                fit_max = details_json.get("max_heart_rate") or max_hr_from_fit_records(details_json)
                if fit_max is not None:
                    avg = activity.average_heart_rate
                    if avg is None or fit_max >= avg:
                        activity.max_heart_rate = fit_max
                fit_min = details_json.get("min_heart_rate")
                if fit_min is not None:
                    activity.min_heart_rate = fit_min
                validate_and_repair_activity(activity, storage=self.sync_service.storage)
                self.sync_service.db.commit()
                logger.info(f"Oppdaterte database med FIT-data for aktivitet {activity_id}")

                logger.info(f"Beregner metrics for aktivitet {activity_id} etter FIT-data nedlasting...")
                metrics_result = self.sync_service._calculate_metrics_for_new_activity(str(activity_id))
                logger.info(
                    "Metrics-beregning for aktivitet %s: Negative split=%s, Decoupling=%s",
                    activity_id,
                    metrics_result.get("negative_split_calculated"),
                    metrics_result.get("decoupling_calculated"),
                )
                try:
                    route_result = RouteAnalysisService(self.sync_service.storage).analyze_activity(str(activity_id), self.sync_service.db)
                    logger.info("Ruteanalyse for aktivitet %s: %s", activity_id, route_result)
                except Exception as exc:
                    logger.warning("Kunne ikke beregne ruteanalyse for aktivitet %s: %s", activity_id, exc)
                try:
                    weather_changed = await self.sync_service.sync_activity_weather_for_activity(
                        str(activity_id),
                        force_refresh=True,
                    )
                    logger.info(
                        "Værberikelse for aktivitet %s: %s (temp=%s, vind=%s)",
                        activity_id,
                        weather_changed,
                        activity.temperature,
                        activity.wind_speed,
                    )
                except Exception as exc:
                    logger.warning("Kunne ikke berike vær for aktivitet %s: %s", activity_id, exc)
            return True, metrics_result
        except Exception as exc:
            logger.error(f"Feil ved nedlasting av FIT-data for aktivitet {activity_id}: {exc}")
            return False, None

    def get_existing_fit_ids(self) -> set[int]:
        try:
            path = data_path("activity_details.parquet")
            existing_parquet_df = pl.read_parquet(str(path))
            return set(existing_parquet_df["activity_id"].unique())
        except Exception:
            return set()

    async def download_fit_data_for_activities(self, activity_ids: list | None = None, limit: int | None = None):
        if not await self.sync_service.garmin_client.initialize():
            logger.error("Kunne ikke initialisere Garmin-klient for FIT-nedlasting.")
            return {"status": "Feil", "message": "Kunne ikke initialisere Garmin-klient"}
        try:
            if activity_ids is None:
                existing_fit_activity_ids = self.get_existing_fit_ids()
                query = self.sync_service.db.query(Activity.activity_id, Activity.detailed_metrics).order_by(
                    Activity.activity_id.desc()
                )
                if limit:
                    query = query.limit(limit * 3)
                all_activities = query.all()
                activity_ids = []
                for activity in all_activities:
                    has_parquet_data = activity.activity_id in existing_fit_activity_ids
                    has_db_details = (
                        activity.detailed_metrics is not None
                        and activity.detailed_metrics != {}
                        and "records" in str(activity.detailed_metrics)
                    )
                    if not (has_parquet_data and has_db_details):
                        activity_ids.append(activity.activity_id)
                        if limit and len(activity_ids) >= limit:
                            break
                logger.info(
                    f"Fant {len(activity_ids)} aktiviteter som mangler FIT-data (av totalt {len(all_activities)} sjekket)"
                )
                logger.info(f"Første 10 aktiviteter som mangler data: {activity_ids[:10]}")

            if not activity_ids:
                return {"status": "Fullført", "message": "Ingen aktiviteter mangler FIT-data"}

            success_count = 0
            total_count = len(activity_ids)
            metrics_calculated = {"negative_split": 0, "decoupling": 0, "hrv_available": 0}

            for i, activity_id in enumerate(activity_ids):
                logger.info(f"Prosesserer aktivitet {activity_id} ({i + 1}/{total_count})")
                ok, metrics_result = await self.download_and_store_fit_file(activity_id)
                if ok:
                    success_count += 1
                    self._aggregate_metrics_counts(metrics_calculated, metrics_result)
                await asyncio.sleep(0.5)

            message = f"Lastet ned FIT-data for {success_count} av {total_count} aktiviteter"
            logger.info(message)
            logger.info(
                f"📊 Metrics beregnet: Negative split={metrics_calculated['negative_split']}, "
                f"Decoupling={metrics_calculated['decoupling']}, HRV={metrics_calculated['hrv_available']}"
            )
            return {
                "status": "Fullført",
                "message": message,
                "success_count": success_count,
                "total_count": total_count,
                "metrics_calculated": metrics_calculated,
            }
        except Exception as exc:
            logger.error(f"Feil under FIT-data nedlasting: {exc}")
            return {"status": "Feil", "message": str(exc)}

    async def download_fit_data_for_period(self, start_date: datetime, end_date: datetime):
        if not await self.sync_service.garmin_client.initialize():
            logger.error("Kunne ikke initialisere Garmin-klient for FIT-nedlasting.")
            return {"status": "Feil", "message": "Kunne ikke initialisere Garmin-klient"}
        try:
            existing_fit_activity_ids = self.get_existing_fit_ids()
            activities_in_period = (
                self.sync_service.db.query(Activity.activity_id, Activity.start_time, Activity.activity_name)
                .filter(and_(Activity.start_time >= start_date, Activity.start_time <= end_date))
                .order_by(Activity.start_time.desc())
                .all()
            )
            logger.info(
                f"Fant {len(activities_in_period)} aktiviteter i perioden {start_date.date()} til {end_date.date()}"
            )
            missing_fit_activities = []
            for activity in activities_in_period:
                has_parquet_data = activity.activity_id in existing_fit_activity_ids
                db_activity = self.sync_service.db.query(Activity.detailed_metrics).filter_by(
                    activity_id=activity.activity_id
                ).first()
                has_db_details = (
                    db_activity
                    and db_activity.detailed_metrics is not None
                    and db_activity.detailed_metrics != {}
                    and "records" in str(db_activity.detailed_metrics)
                )
                if not (has_parquet_data and has_db_details):
                    missing_fit_activities.append(activity)

            logger.info(f"Av disse mangler {len(missing_fit_activities)} aktiviteter FIT-data")
            if not missing_fit_activities:
                return {"status": "Fullført", "message": "Alle aktiviteter i perioden har allerede FIT-data"}

            success_count = 0
            total_count = len(missing_fit_activities)
            metrics_calculated = {"negative_split": 0, "decoupling": 0, "hrv_available": 0}
            for i, activity in enumerate(missing_fit_activities):
                logger.info(
                    f"Prosesserer aktivitet {activity.activity_id} ({i + 1}/{total_count}) - "
                    f"{activity.start_time.strftime('%Y-%m-%d')} - {activity.activity_name}"
                )
                ok, metrics_result = await self.download_and_store_fit_file(activity.activity_id)
                if ok:
                    success_count += 1
                    self._aggregate_metrics_counts(metrics_calculated, metrics_result)
                await asyncio.sleep(1)

            message = (
                f"Lastet ned FIT-data for {success_count} av {total_count} aktiviteter i perioden "
                f"{start_date.date()} til {end_date.date()}"
            )
            logger.info(message)
            logger.info(
                f"📊 Metrics beregnet: Negative split={metrics_calculated['negative_split']}, "
                f"Decoupling={metrics_calculated['decoupling']}, HRV={metrics_calculated['hrv_available']}"
            )
            return {
                "status": "Fullført",
                "message": message,
                "success_count": success_count,
                "total_count": total_count,
                "period": f"{start_date.date()} til {end_date.date()}",
                "metrics_calculated": metrics_calculated,
            }
        except Exception as exc:
            logger.error(f"Feil under FIT-data nedlasting for periode: {exc}")
            return {"status": "Feil", "message": str(exc)}
