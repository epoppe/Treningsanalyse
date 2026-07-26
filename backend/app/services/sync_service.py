from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple, Optional
import logging
from sqlalchemy.orm import Session

from .garmin_client import GarminClient
from .analysis_service import AnalysisService
from ..storage import DataStorage
from ..config import settings
from ..database.models.activity import Activity
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
from .sync_modules.performance_sync_service import PerformanceSyncService
from .sync_modules.metrics_service import SyncMetricsService
from .met_weather_service import MetWeatherService
from .frost_weather_service import FrostWeatherService
from .body_battery_service import BodyBatteryService

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
        self.performance_sync = PerformanceSyncService(self)
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
        return self.performance_sync._apply_activity_summary_metrics(activity, metrics)

    def _fill_grade_adjusted_speed_from_fit(self, activity: Activity) -> bool:
        return self.performance_sync._fill_grade_adjusted_speed_from_fit(activity)

    async def sync_garmin_performance_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        ignore_sync_state: bool = False,
    ) -> dict:
        return await self.performance_sync.sync_garmin_performance_metrics(
            start_date,
            end_date,
            force_refresh_recent=force_refresh_recent,
            ignore_sync_state=ignore_sync_state,
        )

    async def sync_training_effect_data(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        ignore_sync_state: bool = False,
    ) -> dict:
        return await self.performance_sync.sync_training_effect_data(
            start_date,
            end_date,
            force_refresh_recent=force_refresh_recent,
            ignore_sync_state=ignore_sync_state,
        )

    async def sync_training_effect_for_missing(self, force: bool = False) -> dict:
        return await self.performance_sync.sync_training_effect_for_missing(force=force)

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
