from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import asyncio
import logging
import re
import zipfile
import io

import polars as pl
from dateutil import parser as date_parser
from fitparse import FitFile
from sqlalchemy import and_

from ...database.models.activity import Activity
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
                        fit_files = [name for name in zip_file.namelist() if name.endswith(".fit")]
                        if not fit_files:
                            logger.warning("Ingen FIT-fil funnet i ZIP-arkivet")
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

            for message in fitfile.get_messages("session"):
                for field in message.fields:
                    if field.name == "total_ascent":
                        total_ascent = field.value
                    elif field.name == "total_descent":
                        total_descent = field.value

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

            logger.info(
                f"Parsed {len(records)} FIT-records, total_ascent={total_ascent}, total_descent={total_descent}"
            )
            return result
        except ImportError:
            logger.error("fitparse-biblioteket er ikke installert. Kan ikke parse FIT-data.")
            return None
        except Exception as exc:
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

    async def download_and_store_fit_file(self, activity_id: int) -> bool:
        try:
            logger.info(f"Laster ned FIT-data for aktivitet {activity_id}...")
            fit_data = await self.sync_service.garmin_client.get_activity_details(activity_id)
            if not fit_data:
                logger.warning(f"Ingen FIT-data tilgjengelig for aktivitet {activity_id}")
                return False

            details_json = self.parse_fit_data(fit_data)
            if not details_json or "records" not in details_json:
                logger.warning(f"Kunne ikke parse FIT-data for aktivitet {activity_id}")
                return False

            parquet_records = self._to_parquet_records(activity_id, details_json)
            if not parquet_records:
                logger.warning(f"Ingen gyldige FIT-records funnet for aktivitet {activity_id}")
                return False

            self.sync_service.storage.save_activity_details(parquet_records)
            logger.info(f"Lagret {len(parquet_records)} FIT-records for aktivitet {activity_id}")

            activity = self.sync_service.db.query(Activity).filter_by(activity_id=activity_id).first()
            if activity:
                activity.detailed_metrics = details_json
                self.sync_service.db.commit()
                logger.info(f"Oppdaterte database med FIT-data for aktivitet {activity_id}")

                logger.info(f"Beregner metrics for aktivitet {activity_id} etter FIT-data nedlasting...")
                metrics_result = self.sync_service._calculate_metrics_for_new_activity(str(activity_id))
                logger.info(
                    "Metrics-beregning for aktivitet %s: Negative split=%s, Decoupling=%s",
                    activity_id,
                    metrics_result["negative_split_calculated"],
                    metrics_result["decoupling_calculated"],
                )
            return True
        except Exception as exc:
            logger.error(f"Feil ved nedlasting av FIT-data for aktivitet {activity_id}: {exc}")
            return False

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
                if await self.download_and_store_fit_file(activity_id):
                    success_count += 1
                    try:
                        metrics_result = self.sync_service._calculate_metrics_for_new_activity(str(activity_id))
                        if metrics_result["negative_split_calculated"]:
                            metrics_calculated["negative_split"] += 1
                        if metrics_result["decoupling_calculated"]:
                            metrics_calculated["decoupling"] += 1
                        if metrics_result["hrv_calculated"]:
                            metrics_calculated["hrv_available"] += 1
                    except Exception as exc:
                        logger.warning(f"Kunne ikke sjekke metrics for aktivitet {activity_id}: {exc}")
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
                if await self.download_and_store_fit_file(activity.activity_id):
                    success_count += 1
                    try:
                        metrics_result = self.sync_service._calculate_metrics_for_new_activity(str(activity.activity_id))
                        if metrics_result["negative_split_calculated"]:
                            metrics_calculated["negative_split"] += 1
                        if metrics_result["decoupling_calculated"]:
                            metrics_calculated["decoupling"] += 1
                        if metrics_result["hrv_calculated"]:
                            metrics_calculated["hrv_available"] += 1
                    except Exception as exc:
                        logger.warning(f"Kunne ikke sjekke metrics for aktivitet {activity.activity_id}: {exc}")
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

