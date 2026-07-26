from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple, Optional
import asyncio
import logging
from sqlalchemy.orm import Session

from .garmin_client import GarminClient
from .analysis_service import AnalysisService
from ..storage import DataStorage
from ..config import settings
from ..database.models.activity import Activity, GarminPerformanceMetric
from ..database.models.lactate_threshold_history import LactateThresholdHistory
from ..database.models.sync_state import SyncState
from .sync_modules.fit_sync_service import FitSyncService
from .sync_modules.hrv_sync_service import HRVSyncService
from .sync_modules.resting_heart_rate_sync_service import RestingHeartRateSyncService
from .sync_modules.sleep_sync_service import SleepSyncService
from .sync_modules.stress_sync_service import StressSyncService
from .sync_modules.weather_sync_service import WeatherSyncService
from .sync_modules.activity_sync_service import (
    ACTIVITY_SYNC_COMMIT_BATCH_SIZE,
    ActivitySyncService,
    parse_activity_start_from_json,
)
from .sync_modules.metrics_service import SyncMetricsService
from .met_weather_service import MetWeatherService
from .frost_weather_service import FrostWeatherService
from .activity_data_validation import (
    normalize_ground_contact_time_ms,
    normalize_stride_length_meters,
    validate_and_repair_activity,
)
from .body_battery_service import BodyBatteryService
from ..utils.activity_filters import is_running_activity

logger = logging.getLogger(__name__)

class SyncService:
    def __init__(
        self, 
        garmin_client: GarminClient, 
        storage: DataStorage,
        db_session: Session
    ):
        self.garmin_client = garmin_client
        self.storage = storage
        self.db = db_session
        self.analysis_service = AnalysisService(storage)
        self.fit_sync = FitSyncService(self)
        self.hrv_sync = HRVSyncService(self)
        self.rhr_sync = RestingHeartRateSyncService(self)
        self.sleep_sync = SleepSyncService(self)
        self.stress_sync = StressSyncService(self)
        self.weather_sync = WeatherSyncService(self)
        self.activity_sync = ActivitySyncService(self)
        self.metrics_service = SyncMetricsService(self)
        self.weather_service = MetWeatherService(settings.MET_API_USER_AGENT)
        self.frost_weather_service = FrostWeatherService(settings.FROST_CLIENT_ID)

    def _record_lactate_threshold_history(
        self,
        threshold_info: Optional[Dict[str, Any]],
        sync_context: str,
    ) -> Optional[LactateThresholdHistory]:
        """Lagrer terskelobservasjon for denne synken slik at utvikling kan spores over tid."""
        if not threshold_info:
            return None

        has_speed = threshold_info.get("speed_mps") is not None
        has_raw_speed = threshold_info.get("raw_speed_mps") is not None
        has_heart_rate = threshold_info.get("heart_rate_bpm") is not None
        if not (has_speed or has_raw_speed or has_heart_rate):
            return None

        observed_at = datetime.now(timezone.utc)

        record = LactateThresholdHistory(
            observed_at=observed_at,
            source=threshold_info.get("source") or "unknown",
            sync_context=sync_context,
            lactate_threshold_speed=threshold_info.get("speed_mps"),
            lactate_threshold_heart_rate=threshold_info.get("heart_rate_bpm"),
            raw_lactate_threshold_speed=threshold_info.get("raw_speed_mps"),
            is_fallback=bool(threshold_info.get("is_fallback", False)),
        )
        self.db.add(record)
        self.db.commit()
        return record

    def _extract_numeric_value(self, value) -> Optional[float]:
        """Ekstraherer numerisk verdi fra FIT-data som kan inneholde enheter."""
        return self.fit_sync.extract_numeric_value(value)

    def _parse_fit_data(self, fit_data: bytes) -> Optional[dict]:
        """Parser FIT-data fra bytes til strukturert JSON."""
        return self.fit_sync.parse_fit_data(fit_data)

    def _commit_activity_batch(
        self,
        *,
        buffered_parquet_records: Optional[List[Dict[str, Any]]] = None,
        refreshed_parquet_activity_ids: Optional[List[int]] = None,
    ) -> None:
        return self.activity_sync._commit_activity_batch(
            buffered_parquet_records=buffered_parquet_records,
            refreshed_parquet_activity_ids=refreshed_parquet_activity_ids,
        )

    async def sync_json_to_db(self) -> dict:
        return await self.activity_sync.sync_json_to_db()

    def _calculate_missing_periods(
        self,
        start_date_req: datetime,
        end_date_req: datetime,
        max_days_per_request: int = 90,
    ) -> List[Tuple[datetime, datetime]]:
        return self.activity_sync._calculate_missing_periods(
            start_date_req, end_date_req, max_days_per_request=max_days_per_request
        )

    async def sync_activities_with_fit_data(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        fit_data_limit: int = 100,
        ignore_sync_state: bool = False,
        fit_download_mode: str = "chunked",
        sync_run_id: Optional[int] = None,
    ) -> dict:
        return await self.activity_sync.sync_activities_with_fit_data(
            start_date,
            end_date,
            force_refresh_recent=force_refresh_recent,
            fit_data_limit=fit_data_limit,
            ignore_sync_state=ignore_sync_state,
            fit_download_mode=fit_download_mode,
            sync_run_id=sync_run_id,
        )

    async def sync_activities(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        ignore_sync_state: bool = False,
        skip_fit_download: bool = False,
        sync_run_id: Optional[int] = None,
    ) -> dict:
        return await self.activity_sync.sync_activities(
            start_date,
            end_date,
            force_refresh_recent=force_refresh_recent,
            ignore_sync_state=ignore_sync_state,
            skip_fit_download=skip_fit_download,
            sync_run_id=sync_run_id,
        )

    def _normalize_hrv_data(self, hrv_data: dict, calendar_date: str) -> Optional[dict]:
        """Normaliserer HRV-data til en flat struktur for lagring."""
        return self.hrv_sync.normalize_hrv_data(hrv_data, calendar_date)

    async def sync_health_data(self, start_date: datetime, end_date: datetime, force_refresh_recent: bool = False):
        """Synkroniserer helsedata (HRV, Body Battery) for en gitt periode, inkrementelt."""
        # HRV-data er kun tilgjengelig fra 2023 og fremover
        hrv_start_date = max(start_date, datetime(2023, 1, 1, tzinfo=timezone.utc))
        
        if hrv_start_date > end_date:
            logger.info(f"HRV-synkronisering hoppes over - perioden {start_date.date()} til {end_date.date()} er før 2023")
            return
        
        logger.info(f"Starter synkronisering av helsedata fra {hrv_start_date.date()} til {end_date.date()} (HRV fra 2023)")
        
        if not await self.garmin_client.initialize():
            logger.error("Kunne ikke initialisere Garmin-klient for helsedata-synk.")
            return

        await self.hrv_sync.sync_hrv_data(hrv_start_date, end_date, force_refresh_recent)

        try:
            await self.rhr_sync.sync_resting_heart_rate_data(start_date, end_date, force_refresh_recent)
        except Exception as e:
            logger.warning(f"Hvilepuls synk feilet: {e}")

        # Body Battery inkrementell synk via database
        try:
            bb_service = BodyBatteryService(self.garmin_client)
            # Finn startdato for BB (inkrementell)
            bb_state = self.db.query(SyncState).filter_by(key="body_battery").first()
            bb_start_date = hrv_start_date
            if bb_state and bb_state.last_synced_date:
                bb_start_date = max(bb_start_date, datetime.combine(bb_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1))
            bb_start_str = bb_start_date.strftime('%Y-%m-%d')
            bb_end_str = end_date.strftime('%Y-%m-%d')
            logger.info(f"Synkroniserer Body Battery inkrementelt: {bb_start_str} -> {bb_end_str}")
            bb_result = await bb_service.sync_body_battery_data_to_database(self.db, bb_start_str, bb_end_str)
            if (bb_result.get("synced_records", 0) + bb_result.get("updated_records", 0)) > 0:
                # Oppdater sync state
                try:
                    if not bb_state:
                        bb_state = SyncState(key="body_battery")
                        self.db.add(bb_state)
                    bb_state.last_synced_date = datetime.strptime(bb_end_str, '%Y-%m-%d').date()
                    bb_state.last_synced_at = datetime.now(timezone.utc)
                    self.db.commit()
                except Exception as e:
                    logger.warning(f"Kunne ikke oppdatere Body Battery sync state: {e}")
        except Exception as e:
            logger.warning(f"Body Battery synk feilet, fortsetter: {e}")

        try:
            await self.sleep_sync.sync_sleep_data(hrv_start_date, end_date, force_refresh_recent)
        except Exception as e:
            logger.warning(f"Søvn synk feilet: {e}")

        try:
            await self.stress_sync.sync_stress_data(start_date, end_date, force_refresh_recent)
        except Exception as e:
            logger.warning(f"Stress synk feilet: {e}")

    async def _download_and_store_fit_file(self, activity_id: int):
        """Hjelpefunksjon for å laste ned og lagre en FIT-fil for en gitt aktivitet."""
        return await self.fit_sync.download_and_store_fit_file(activity_id)

    async def download_fit_data_for_activities(self, activity_ids: list = None, limit: int = None):
        """Laster ned FIT-data for spesifikke aktiviteter eller alle aktiviteter uten FIT-data."""
        return await self.fit_sync.download_fit_data_for_activities(activity_ids, limit)

    async def download_fit_data_for_period(self, start_date: datetime, end_date: datetime):
        """Laster ned FIT-data for aktiviteter i en spesifikk periode."""
        return await self.fit_sync.download_fit_data_for_period(start_date, end_date)

    def _activity_weather_altitude(self, activity: Activity) -> Optional[float]:
        return self.weather_sync.activity_weather_altitude(activity)

    def _activity_route_fingerprint(self, activity_id: str):
        return self.weather_sync.activity_route_fingerprint(activity_id)

    def _get_activity_details_frame(self, activity_id: str):
        return self.weather_sync.get_activity_details_frame(activity_id)

    def _build_weather_sample_points(self, activity: Activity, *, interval_minutes: int = 15):
        return self.weather_sync.build_weather_sample_points(
            activity, interval_minutes=interval_minutes
        )

    async def _get_weather_for_sample_point(self, **kwargs):
        return await self.weather_sync.get_weather_for_sample_point(**kwargs)

    def _aggregate_weather_snapshots(self, snapshots: List[Dict[str, Any]]):
        return self.weather_sync.aggregate_weather_snapshots(snapshots)

    def _apply_garmin_list_weather_if_missing(self, activity: Activity) -> bool:
        return self.weather_sync.apply_garmin_list_weather_if_missing(activity)

    async def sync_activity_weather_for_activity(
        self,
        activity_id: str,
        *,
        force_refresh: bool = False,
    ) -> bool:
        return await self.weather_sync.sync_activity_weather_for_activity(
            activity_id, force_refresh=force_refresh
        )

    async def sync_activity_weather(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        ignore_sync_state: bool = False,
    ) -> dict:
        return await self.weather_sync.sync_activity_weather(
            start_date,
            end_date,
            force_refresh_recent=force_refresh_recent,
            ignore_sync_state=ignore_sync_state,
        )

    def _apply_activity_summary_metrics(self, activity: Activity, metrics: Dict[str, Any]) -> bool:
        """Lagrer utvidede Garmin activity-service-felter på aktiviteten."""
        field_map = {
            "vo2_max": "vo2_max",
            "vo2_max_precise": "vo2_max_precise",
            "average_heart_rate": "average_heart_rate",
            "max_heart_rate": "max_heart_rate",
            "min_heart_rate": "min_heart_rate",
            "average_moving_speed": "average_moving_speed",
            "avg_grade_adjusted_speed": "avg_grade_adjusted_speed",
            "ground_contact_time": "ground_contact_time",
            "stride_length": "stride_length",
            "vertical_oscillation": "vertical_oscillation",
            "vertical_ratio": "vertical_ratio",
            "begin_potential_stamina": "begin_potential_stamina",
            "end_potential_stamina": "end_potential_stamina",
            "min_available_stamina": "min_available_stamina",
            "recovery_time": "recovery_time",
            "activity_body_battery_delta": "activity_body_battery_delta",
            "training_load": "epoc",
            "aerobic_training_effect": "total_training_effect",
            "anaerobic_training_effect": "total_anaerobic_training_effect",
            "training_effect_label": "training_effect_label",
            "aerobic_training_effect_message": "aerobic_training_effect_message",
            "anaerobic_training_effect_message": "anaerobic_training_effect_message",
            "elevation_gain": "total_ascent",
            "elevation_loss": "total_descent",
            "moving_duration": "moving_duration",
            "elapsed_duration": "elapsed_duration",
            "min_elevation": "min_elevation",
            "max_elevation": "max_elevation",
            "total_steps": "total_steps",
            "max_running_cadence": "max_running_cadence",
        }
        changed = False
        for source_key, attr in field_map.items():
            value = metrics.get(source_key)
            if value is None:
                continue
            if attr == "stride_length":
                value = normalize_stride_length_meters(value)
            elif attr == "ground_contact_time":
                value = normalize_ground_contact_time_ms(value)
            if value is not None and getattr(activity, attr, None) != value:
                setattr(activity, attr, value)
                changed = True
        repair = validate_and_repair_activity(activity, storage=self.storage)
        if repair.changed:
            changed = True
            for fix in repair.fixes:
                logger.info("Aktivitet %s: %s", activity.activity_id, fix)
        if activity.avg_grade_adjusted_speed is None:
            if self._fill_grade_adjusted_speed_from_fit(activity):
                changed = True
        return changed

    def _fill_grade_adjusted_speed_from_fit(self, activity: Activity) -> bool:
        """Utled grade-adjusted speed fra FIT når Garmin summary mangler feltet."""
        if activity.avg_grade_adjusted_speed is not None:
            return False
        try:
            result = self.analysis_service.calculate_grade_adjusted_speed(
                int(activity.activity_id),
                self.db,
            )
        except (TypeError, ValueError):
            return False
        return bool(result and result.get("calculation_method") not in {None, "stored"})

    async def sync_garmin_performance_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        ignore_sync_state: bool = False,
    ) -> dict:
        """Synkroniserer dagsbaserte Garmin performance-metrikker til databasen."""
        effective_start = start_date
        if not ignore_sync_state:
            try:
                state = self.db.query(SyncState).filter_by(key="garmin_performance_metrics").first()
                if state and state.last_synced_date and not force_refresh_recent:
                    effective_start = max(
                        effective_start,
                        datetime.combine(state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1),
                    )
            except Exception as e:
                logger.debug(f"Kunne ikke lese SyncState for garmin_performance_metrics: {e}")

        if effective_start > end_date:
            return {"status": "Fullført", "updated_count": 0, "skipped_count": 0, "failed_count": 0}

        if not await self.garmin_client.initialize():
            return {"status": "Feil", "message": "Kunne ikke autentisere mot Garmin"}

        recent_cutoff = datetime.now(timezone.utc).date() - timedelta(days=7)
        current_day = effective_start.date()
        end_day = end_date.date()
        updated_count = 0
        skipped_count = 0
        failed_count = 0

        while current_day <= end_day:
            row_date = datetime.combine(current_day, datetime.min.time(), tzinfo=timezone.utc)
            existing = self.db.query(GarminPerformanceMetric).filter_by(date=row_date).first()
            is_recent = current_day >= recent_cutoff
            if existing and not (force_refresh_recent and is_recent):
                skipped_count += 1
                current_day += timedelta(days=1)
                continue

            try:
                data = await self.garmin_client.get_daily_garmin_performance_metrics(current_day)
                if not data:
                    skipped_count += 1
                    current_day += timedelta(days=1)
                    continue

                row = existing or GarminPerformanceMetric(date=row_date)
                if existing is None:
                    self.db.add(row)

                fields = [
                    "vo2_max", "vo2_max_precise", "fitness_age", "max_met_category",
                    "altitude_acclimation", "previous_altitude_acclimation",
                    "heat_acclimation_percentage", "previous_heat_acclimation_percentage",
                    "current_altitude", "heat_trend", "altitude_trend",
                    "monthly_load_aerobic_low", "monthly_load_aerobic_high",
                    "monthly_load_anaerobic", "monthly_load_aerobic_low_target_min",
                    "monthly_load_aerobic_low_target_max", "monthly_load_aerobic_high_target_min",
                    "monthly_load_aerobic_high_target_max", "monthly_load_anaerobic_target_min",
                    "monthly_load_anaerobic_target_max", "training_balance_feedback_phrase",
                    "training_status", "training_status_feedback_phrase", "sport", "sub_sport",
                    "fitness_trend", "fitness_trend_sport", "acwr_percent", "acwr_status",
                    "acwr_status_feedback", "daily_training_load_acute",
                    "daily_training_load_chronic", "daily_acute_chronic_workload_ratio",
                    "load_tunnel_min", "load_tunnel_max", "endurance_score",
                    "endurance_classification", "hill_score", "hill_endurance_score",
                    "hill_strength_score", "raw_maxmet", "raw_training_load_balance",
                    "raw_training_status", "raw_endurance_score", "raw_hill_score",
                ]
                for field in fields:
                    setattr(row, field, data.get(field))
                row.calculated_at = datetime.now(timezone.utc)
                updated_count += 1
            except Exception as e:
                logger.warning(f"Kunne ikke synkronisere Garmin performance metrics for {current_day}: {e}")
                failed_count += 1

            current_day += timedelta(days=1)

        self.db.commit()
        if updated_count > 0:
            try:
                state = self.db.query(SyncState).filter_by(key="garmin_performance_metrics").first()
                if not state:
                    state = SyncState(key="garmin_performance_metrics")
                    self.db.add(state)
                state.last_synced_date = end_day
                state.last_synced_at = datetime.now(timezone.utc)
                self.db.commit()
            except Exception as e:
                logger.warning(f"Kunne ikke oppdatere SyncState for garmin_performance_metrics: {e}")

        return {
            "status": "Fullført",
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "period": {"start": str(effective_start.date()), "end": str(end_day)},
        }

    async def sync_training_effect_data(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        ignore_sync_state: bool = False,
    ) -> dict:
        """
        Synkroniserer Training Effect data for aktiviteter i en gitt periode.

        Args:
            start_date: Startdato for synkronisering
            end_date: Sluttdato for synkronisering
            force_refresh_recent: Om nylige data skal oppdateres selv om de eksisterer
            ignore_sync_state: Bruk hele perioden (ikke inkrementell), viktig ved full resync
        """
        effective_start = start_date
        if not ignore_sync_state:
            try:
                te_state = self.db.query(SyncState).filter_by(key="training_effect").first()
                if te_state and te_state.last_synced_date and not force_refresh_recent:
                    effective_start = max(
                        effective_start,
                        datetime.combine(te_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
                    )
            except Exception as e:
                logger.debug(f"Kunne ikke lese SyncState for training_effect: {e}")

        logger.info(f"Starter Training Effect synkronisering for perioden {effective_start.date()} til {end_date.date()}")
        
        try:
            if not await self.garmin_client.initialize():
                logger.error("Kunne ikke initialisere Garmin-klient for Training Effect synkronisering.")
                return {"status": "Feil", "message": "Kunne ikke autentisere mot Garmin"}
            
            # Finn alltid siste aktivitet (globalt) og tving oppdatering for den,
            # uavhengig av valgt periode. Dette sikrer komplette verdier på nyeste økt.
            latest_activity = self.db.query(Activity).order_by(Activity.start_time.desc()).first()
            latest_activity_id = str(latest_activity.activity_id) if latest_activity else None

            # Hent aktiviteter fra databasen i den gitte perioden
            activities = self.db.query(Activity).filter(
                Activity.start_time >= effective_start,
                Activity.start_time <= end_date
            ).order_by(Activity.start_time.desc()).all()
            
            logger.info(f"Fant {len(activities)} aktiviteter i perioden {start_date.date()} til {end_date.date()}")
            
            # Beregn grensen for "nylige" data (siste 2 dager)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
            
            updated_count = 0
            skipped_count = 0
            failed_count = 0
            bb_service = BodyBatteryService(self.garmin_client)
            
            for i, activity in enumerate(activities, 1):
                activity_id = str(activity.activity_id)
                activity_start_time = activity.start_time
                
                # Sjekk om aktiviteten er nylig og om vi skal force refresh
                # Sørg for at begge datetimes har samme timezone-oppsett
                if activity_start_time.tzinfo is None:
                    activity_start_time = activity_start_time.replace(tzinfo=timezone.utc)
                is_recent = activity_start_time >= recent_cutoff
                # Ikke hopp over hvis dette er aller siste aktivitet (skal alltid oppdateres)
                is_latest = (latest_activity_id is not None and activity_id == latest_activity_id)
                # Behandle 0 som manglende – gyldig TE er 1.0–5.0
                has_valid_aerobic_te = (
                    activity.total_training_effect is not None and activity.total_training_effect > 0
                )
                has_valid_anaerobic_te = (
                    activity.total_anaerobic_training_effect is not None
                    and activity.total_anaerobic_training_effect > 0
                )
                missing_activity_body_battery = (
                    activity.activity_body_battery_delta is None
                    or activity.body_battery_start is None
                    or activity.body_battery_start < 0
                )
                # vo2_max_precise kommer ofte fra activitylist uten full activity-service-fetch.
                has_extended_summary = (
                    activity.begin_potential_stamina is not None
                    or activity.min_available_stamina is not None
                    or activity.avg_grade_adjusted_speed is not None
                    or (
                        activity.activity_body_battery_delta is not None
                        and activity.body_battery_start is not None
                        and activity.body_battery_start >= 0
                    )
                )
                missing_grade_adjusted_speed = (
                    is_running_activity(activity)
                    and activity.avg_grade_adjusted_speed is None
                    and (activity.total_ascent or 0) >= 10
                )
                # Skip kun når TE og utvidede summary-/recovery-felter allerede finnes.
                if (
                    has_valid_aerobic_te
                    and has_valid_anaerobic_te
                    and has_extended_summary
                    and not missing_activity_body_battery
                    and not missing_grade_adjusted_speed
                    and not (force_refresh_recent and is_recent)
                    and not is_latest
                ):
                    skipped_count += 1
                    continue
                
                logger.debug(
                    "Prosesserer Training Effect for aktivitet %s (%s/%s)",
                    activity_id,
                    i,
                    len(activities),
                )

                try:
                    summary_metrics = await self.garmin_client.get_activity_summary_metrics(activity_id)
                    if summary_metrics:
                        self._apply_activity_summary_metrics(activity, summary_metrics)
                    await bb_service.enrich_activity_body_battery_from_wellness(activity)
                    updated_count += 1
                except Exception as e:
                    logger.warning(
                        "Feil ved henting av Training Effect for aktivitet %s: %s",
                        activity_id,
                        e,
                    )
                    failed_count += 1
            
            # Lagre endringene til databasen
            self.db.commit()

            # Oppdater SyncState for training_effect
            try:
                if updated_count > 0:
                    te_state = self.db.query(SyncState).filter_by(key="training_effect").first()
                    if not te_state:
                        te_state = SyncState(key="training_effect")
                        self.db.add(te_state)
                    te_state.last_synced_date = end_date.date()
                    te_state.last_synced_at = datetime.now(timezone.utc)
                    self.db.commit()
            except Exception as e:
                logger.warning(f"Kunne ikke oppdatere SyncState for training_effect: {e}")
            
            result = {
                "status": "Fullført",
                "message": f"Training Effect synkronisering fullført: {updated_count} oppdatert, {skipped_count} hoppet over, {failed_count} feilet",
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "total_processed": len(activities)
            }
            
            logger.info(f"Training Effect synkronisering fullført: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Feil under Training Effect synkronisering: {e}")
            return {"status": "Feil", "message": str(e)}

    async def sync_training_effect_for_missing(self, force: bool = False) -> dict:
        """
        Henter Training Effect fra Garmin for aktiviteter som mangler eller har 0.
        Gyldig TE er 1.0–5.0. Brukes for å fikse aktiviteter som viser 0 i frontend.
        """
        from sqlalchemy import or_, desc
        try:
            if not await self.garmin_client.initialize():
                return {"status": "Feil", "message": "Kunne ikke autentisere mot Garmin"}
            if force:
                activities = self.db.query(Activity).order_by(desc(Activity.start_time)).all()
            else:
                activities = self.db.query(Activity).filter(
                    or_(
                        or_(
                            Activity.total_training_effect.is_(None),
                            Activity.total_training_effect <= 0,
                        ),
                        or_(
                            Activity.total_anaerobic_training_effect.is_(None),
                            Activity.total_anaerobic_training_effect <= 0,
                        ),
                    )
                ).order_by(desc(Activity.start_time)).all()
            updated = 0
            failed = 0
            bb_service = BodyBatteryService(self.garmin_client)
            for i, act in enumerate(activities, 1):
                try:
                    summary_metrics = await self.garmin_client.get_activity_summary_metrics(str(act.activity_id))
                    if summary_metrics:
                        self._apply_activity_summary_metrics(act, summary_metrics)
                    if await bb_service.enrich_activity_body_battery_from_wellness(act):
                        updated += 1
                    elif summary_metrics:
                        updated += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"TE feil for {act.activity_id}: {e}")
                    failed += 1
            self.db.commit()
            return {
                "status": "Fullført",
                "message": f"{updated} oppdatert, {failed} feilet",
                "updated_count": updated,
                "failed_count": failed,
                "total_processed": len(activities),
            }
        except Exception as e:
            logger.error(f"Feil ved TE-for-missing sync: {e}", exc_info=True)
            return {"status": "Feil", "message": str(e)}

    def _calculate_metrics_for_new_activity(self, activity_id: str) -> dict:
        """
        Beregner og lagrer ALLE beregnede verdier for en ny aktivitet.
        Sjekker først om verdier allerede finnes i databasen for å unngå unødvendige beregninger.
        Returnerer en ordbok med resultater.
        """
        return self.metrics_service.calculate_metrics_for_new_activity(activity_id)

    async def _update_lactate_threshold_for_all_running_activities(self):
        """
        Fyller inn lactate threshold på løpeaktiviteter som mangler verdi.
        Eksisterende verdier beholdes slik at historiske terskelendringer kan spores over tid.
        """
        await self.metrics_service.update_lactate_threshold_for_all_running_activities()
