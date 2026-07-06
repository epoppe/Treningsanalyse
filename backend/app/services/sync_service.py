from collections import Counter
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, List, Tuple, Optional
import asyncio
import logging
import pandas as pd
from sqlalchemy.orm import Session

from .garmin_client import GarminClient
from .analysis_service import AnalysisService
from ..storage import DataStorage
from ..config import settings
from ..database.models.activity import Activity, ActivityType, GarminPerformanceMetric, ActivityRouteFingerprint
from ..database.models.lactate_threshold_history import LactateThresholdHistory
from ..database.models.sync_state import SyncState
from .sync_modules.fit_sync_service import FitSyncService
from .sync_modules.hrv_sync_service import HRVSyncService
from .sync_modules.resting_heart_rate_sync_service import RestingHeartRateSyncService
from .sync_modules.sleep_sync_service import SleepSyncService
from .sync_modules.stress_sync_service import StressSyncService
from .sync_modules.metrics_service import SyncMetricsService
from .met_weather_service import MetWeatherService
from .frost_weather_service import FrostWeatherService
from .activity_data_validation import (
    normalize_ground_contact_time_ms,
    normalize_stride_length_meters,
    validate_and_repair_activity,
)
from .activity_field_extraction import extract_activity_list_fields, extract_garmin_weather_fields, extract_vo2_max_precise
from .activity_metric_backfill import (
    derive_average_pace_sec_per_km,
    derive_total_steps,
    normalize_garmin_average_pace,
)
from .body_battery_service import BodyBatteryService
from ..utils.activity_filters import is_indoor_type_key, is_running_activity

logger = logging.getLogger(__name__)


def parse_activity_start_from_json(act_data: Dict[str, Any]) -> datetime:
    """
    Tolker starttid fra JSON-aktivitet (Garmin API, epoch eller ISO-strenger).
    """
    raw_gmt = act_data.get("startTimeGMT")
    if isinstance(raw_gmt, str) and raw_gmt.strip():
        dt = datetime.fromisoformat(raw_gmt.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    raw = act_data.get("startTimeInSeconds")
    if raw is None:
        raw = act_data.get("startTimeLocal")

    if isinstance(raw, (int, float)):
        dt = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        return dt

    if isinstance(raw, str) and raw.strip():
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    raise ValueError("Mangler gyldig starttid (startTimeGMT / startTimeInSeconds / startTimeLocal)")


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

    def sync_json_to_db(self) -> dict:
        """
        Leser alle aktiviteter fra JSON-filer og synkroniserer dem til databasen.
        """
        logger.info("Starter synkronisering fra JSON-filer til database.")

        lactate_threshold_speed: Optional[float] = None
        lactate_threshold_heart_rate: Optional[float] = None
        try:
            threshold_info = asyncio.run(self.garmin_client.get_lactate_threshold_info())
            if threshold_info:
                lactate_threshold_speed = threshold_info.get("speed_mps")
                lactate_threshold_heart_rate = threshold_info.get("heart_rate_bpm")
                self._record_lactate_threshold_history(threshold_info, sync_context="json_sync")
        except Exception as e:
            logger.warning(f"Kunne ikke hente lactate threshold speed: {e}")

        # 1. Hent alle aktiviteter fra JSON-filene
        json_activities = self.storage.get_activities()
        if not json_activities:
            logger.warning("Fant ingen JSON-filer å synkronisere.")
            return {"status": "Ingen JSON-filer funnet", "added": 0, "skipped": 0}

        # 2. Hent alle eksisterende Garmin-aktivitets-ID-er (PK) for å unngå duplikater
        candidate_ids = [str(act.get("activityId")) for act in json_activities if act.get("activityId") is not None]
        existing_ids = self.storage.get_existing_activity_ids(self.db, candidate_ids)
        logger.info(f"Fant {len(existing_ids)} eksisterende aktiviteter i databasen.")
        
        added_count = 0
        skipped_count = 0
        
        # Ordbok for å cache ActivityType-objekter
        activity_type_cache = {}

        for act_data in json_activities:
            raw_id = act_data.get("activityId")
            if raw_id is None:
                skipped_count += 1
                continue
            activity_id = str(raw_id)

            if activity_id in existing_ids:
                skipped_count += 1
                continue
            
            # Håndter ActivityType
            act_type_block = act_data.get("activityType") or {}
            activity_type_key = act_type_block.get("typeKey")
            activity_type_obj = None
            if activity_type_key:
                if activity_type_key in activity_type_cache:
                    activity_type_obj = activity_type_cache[activity_type_key]
                else:
                    activity_type_obj = self.db.query(ActivityType).filter_by(type_key=activity_type_key).first()
                    if not activity_type_obj:
                        # Opprett ny ActivityType hvis den ikke finnes
                        parent_type_key = act_type_block.get("parentTypeKey", "unknown")
                        activity_type_obj = ActivityType(type_key=activity_type_key, parent_type_key=parent_type_key)
                        self.db.add(activity_type_obj)
                        self.db.flush() # Få ID-en før commit
                    activity_type_cache[activity_type_key] = activity_type_obj
            
            # Konverter pace/speed — Garmin averagePace er min/km, lagres som s/km
            avg_pace = normalize_garmin_average_pace(act_data.get("averagePace"))
            avg_speed = act_data.get("averageSpeed") or 0
            if (not avg_speed or avg_speed <= 0) and avg_pace:
                avg_speed = 1000.0 / avg_pace
            elif not avg_pace and avg_speed and avg_speed > 0:
                avg_pace = derive_average_pace_sec_per_km(average_speed=avg_speed)
            elif not avg_pace:
                avg_pace = derive_average_pace_sec_per_km(
                    distance_m=act_data.get("distance"),
                    duration_s=act_data.get("duration"),
                )

            try:
                start_time = parse_activity_start_from_json(act_data)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning("Hoppet over aktivitet %s uten gyldig starttid: %s", activity_id, e)
                skipped_count += 1
                continue

            list_fields = extract_activity_list_fields(act_data)
            total_steps = list_fields["total_steps"]
            if total_steps is None:
                total_steps = derive_total_steps(
                    distance_m=act_data.get("distance"),
                    average_speed_mps=avg_speed if avg_speed and avg_speed > 0 else None,
                    average_running_cadence_spm=act_data.get("averageRunningCadenceInStepsPerMinute"),
                )

            new_activity = Activity(
                activity_id=activity_id,
                activity_name=act_data.get('activityName'),
                start_time=start_time,
                distance=act_data.get('distance'),
                duration=act_data.get('duration'),
                moving_duration=list_fields["moving_duration"],
                elapsed_duration=list_fields["elapsed_duration"],
                total_steps=total_steps,
                min_elevation=list_fields["min_elevation"],
                max_elevation=list_fields["max_elevation"],
                calories=act_data.get('calories'),
                vo2_max=act_data.get('vO2MaxValue'),
                vo2_max_precise=extract_vo2_max_precise(act_data),
                average_heart_rate=act_data.get('averageHR'),
                max_heart_rate=act_data.get('maxHR'),
                min_heart_rate=act_data.get('minHR'),
                average_speed=avg_speed,
                average_moving_speed=act_data.get('averageMovingSpeed'),
                avg_grade_adjusted_speed=act_data.get('avgGradeAdjustedSpeed'),
                average_pace=avg_pace,
                activity_type_id=activity_type_obj.id if activity_type_obj else None,
                average_running_cadence=act_data.get('averageRunningCadenceInStepsPerMinute'),
                max_running_cadence=list_fields["max_running_cadence"],
                total_training_effect=act_data.get('aerobicTrainingEffect') or act_data.get('trainingEffect'),
                total_anaerobic_training_effect=act_data.get('anaerobicTrainingEffect'),
                training_effect_label=act_data.get('trainingEffectLabel'),
                aerobic_training_effect_message=act_data.get('aerobicTrainingEffectMessage'),
                anaerobic_training_effect_message=act_data.get('anaerobicTrainingEffectMessage'),
                lactate_threshold_heart_rate=lactate_threshold_heart_rate,
                lactate_threshold_speed=lactate_threshold_speed  # Lactate threshold speed
            )
            self.db.add(new_activity)
            added_count += 1
            
        self.db.commit()
        logger.info(f"Synkronisering fullført. La til: {added_count}, hoppet over: {skipped_count}.")
        return {"status": "Fullført", "added": added_count, "skipped": skipped_count}

    def _calculate_missing_periods(
        self,
        start_date_req: datetime,
        end_date_req: datetime,
        max_days_per_request: int = 90
    ) -> List[Tuple[datetime, datetime]]:
        """
        Beregner hvilke tidsperioder som mangler data, basert på ønsket periode
        og eksisterende data. Deler opp i mindre biter.
        """
        min_stored, max_stored = self.storage.get_activity_date_coverage()
        logger.info(f"Ønsket synkroniseringsperiode: {start_date_req} -> {end_date_req}")
        logger.info(f"Eksisterende datadekning: {min_stored} -> {max_stored}")

        periods_to_fetch = []

        # Hvis ingen data finnes, er hele perioden manglende.
        if min_stored is None or max_stored is None:
            logger.info("Ingen eksisterende data. Hele perioden må hentes.")
            periods_to_fetch.append((start_date_req, end_date_req))
        else:
            # 1. Sjekk for manglende data FØR det som allerede er lagret
            if start_date_req < min_stored:
                periods_to_fetch.append((start_date_req, min_stored - timedelta(days=1)))
            
            # 2. Sjekk for manglende data ETTER det som allerede er lagret
            if end_date_req > max_stored:
                periods_to_fetch.append((max_stored + timedelta(days=1), end_date_req))

        if not periods_to_fetch:
            logger.info("Ingen nye tidsperioder å hente. Data er allerede à jour for den forespurte perioden.")
            return []

        # Deler opp de manglende periodene i mindre biter for å unngå for store API-kall
        chunked_periods = []
        for start, end in periods_to_fetch:
            current_start = start
            while current_start <= end:
                chunk_end = min(current_start + timedelta(days=max_days_per_request - 1), end)
                chunked_periods.append((current_start, chunk_end))
                current_start = chunk_end + timedelta(days=1)
        
        logger.info(f"Beregnet {len(chunked_periods)} perioder som skal hentes: {chunked_periods}")
        return chunked_periods

    async def sync_activities_with_fit_data(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        fit_data_limit: int = 100,
        ignore_sync_state: bool = False,
        fit_download_mode: str = "chunked",
    ) -> dict:
        """
        Synkroniserer aktiviteter og laster automatisk ned FIT-data, HRV-data og Training Effect for aktiviteter som mangler det.
        
        Args:
            start_date: Startdato for synkronisering
            end_date: Sluttdato for synkronisering  
            force_refresh_recent: Om nylige data skal oppdateres selv om de eksisterer
            fit_data_limit: Maksimalt antall aktiviteter å laste ned FIT-data for
        """
        logger.info(f"Starter utvidet aktivitetssynkronisering med automatisk FIT-data, HRV og Training Effect nedlasting")
        
        # Først, gjør vanlig aktivitetssynkronisering
        sync_result = await self.sync_activities(start_date, end_date, force_refresh_recent, ignore_sync_state)
        
        # Så, last ned FIT-data for aktiviteter som mangler det (kun for aktiviteter i det valgte tidsrommet)
        fit_result = {"status": "Ikke kjørt", "success_count": 0, "total_count": 0}
        
        # Last ned FIT-data
        days_diff = (end_date - start_date).days
        try:
            if days_diff <= 7 or fit_download_mode == "auto":
                logger.info(f"Starter automatisk FIT-data nedlasting for aktiviteter i perioden {start_date.date()} til {end_date.date()}...")
                fit_result = await self.download_fit_data_for_period(start_date, end_date)
                logger.info(f"FIT-data nedlasting ferdig: {fit_result.get('message', 'Ukjent status')}")
            else:
                # chunked modus for lange perioder
                logger.info(f"Starter chunket FIT-data nedlasting for periode på {days_diff} dager")
                chunk_success = 0
                chunk_total = 0
                metrics_agg = {"negative_split": 0, "decoupling": 0, "hrv_available": 0}
                chunk_start = start_date
                while chunk_start <= end_date:
                    chunk_end = min(chunk_start + timedelta(days=6), end_date)
                    logger.info(f"FIT-chunk: {chunk_start.date()} -> {chunk_end.date()}")
                    chunk_res = await self.download_fit_data_for_period(chunk_start, chunk_end)
                    chunk_success += int(chunk_res.get("success_count", 0))
                    chunk_total += int(chunk_res.get("total_count", 0))
                    m = chunk_res.get("metrics_calculated", {})
                    metrics_agg["negative_split"] += int(m.get("negative_split", 0))
                    metrics_agg["decoupling"] += int(m.get("decoupling", 0))
                    metrics_agg["hrv_available"] += int(m.get("hrv_available", 0))
                    chunk_start = chunk_end + timedelta(days=1)
                fit_result = {
                    "status": "Fullført",
                    "message": f"Chunket FIT-data nedlasting fullført for periode {start_date.date()} til {end_date.date()}",
                    "success_count": chunk_success,
                    "total_count": chunk_total,
                    "metrics_calculated": metrics_agg,
                }
        except Exception as e:
            logger.error(f"Feil under automatisk FIT-data nedlasting: {e}")
            fit_result = {"status": "Feil", "message": str(e), "success_count": 0, "total_count": 0}
        
        # Synkroniser HRV-data for samme periode
        hrv_result = {"status": "Ikke kjørt", "message": "Ikke kjørt"}
        try:
            logger.info(f"Starter automatisk HRV-synkronisering for perioden {start_date.date()} til {end_date.date()}...")
            await self.sync_health_data(start_date, end_date, force_refresh_recent)
            hrv_result = {"status": "Fullført", "message": "HRV-data synkronisert"}
            logger.info("HRV-synkronisering fullført")
        except Exception as e:
            logger.error(f"Feil under HRV-synkronisering: {e}")
            hrv_result = {"status": "Feil", "message": str(e)}
        
        # Synkroniser Training Effect data for samme periode
        te_result = {"status": "Ikke kjørt", "message": "Ikke kjørt"}
        try:
            logger.info(f"Starter automatisk Training Effect synkronisering for perioden {start_date.date()} til {end_date.date()}...")
            te_result = await self.sync_training_effect_data(start_date, end_date, force_refresh_recent)
            logger.info(f"Training Effect synkronisering fullført: {te_result.get('message', 'Ukjent status')}")
        except Exception as e:
            logger.error(f"Feil under Training Effect synkronisering: {e}")
            te_result = {"status": "Feil", "message": str(e)}

        weather_result = {"status": "Ikke kjørt", "message": "Ikke kjørt"}
        try:
            logger.info(
                "Starter automatisk værsynkronisering for perioden %s til %s...",
                start_date.date(),
                end_date.date(),
            )
            weather_result = await self.sync_activity_weather(
                start_date,
                end_date,
                force_refresh_recent=force_refresh_recent,
                ignore_sync_state=ignore_sync_state,
            )
            logger.info("Værsynkronisering fullført: %s", weather_result)
        except Exception as e:
            logger.error(f"Feil under værsynkronisering: {e}")
            weather_result = {"status": "Feil", "message": str(e)}

        # TSS beregnes ofte før EPOC finnes — oppdater når Training Effect er synket
        post_te_metrics = {"status": "Ikke kjørt"}
        if te_result.get("status") != "Feil":
            try:
                post_te_metrics = self.metrics_service.refresh_metrics_after_te_sync(start_date, end_date)
                logger.info(
                    "TSS oppdatert etter Training Effect: %s av %s aktiviteter i perioden",
                    post_te_metrics.get("tss_refreshed"),
                    post_te_metrics.get("activities_checked"),
                )
            except Exception as e:
                logger.error(f"Feil ved oppfriskning av TSS etter Training Effect: {e}")
                post_te_metrics = {"status": "Feil", "message": str(e)}
        
        # Oppdater sammendragstabeller automatisk hvis nye aktiviteter ble synkronisert
        summary_result = {"status": "Ikke kjørt", "message": "Ingen nye aktiviteter"}
        if sync_result.get("total_fetched", 0) > 0:
            try:
                logger.info("Starter automatisk oppdatering av sammendragstabeller...")
                from ..services.summary_service import SummaryService
                summary_service = SummaryService()
                
                # Oppdater sammendrag for perioden som ble synkronisert
                summary_counts = summary_service.bulk_update_summaries(start_date.date(), end_date.date())
                logger.info(
                    "Oppdaterte sammendrag for berørt periode: "
                    f"dag={summary_counts.get('daily_count', 0)}, "
                    f"uke={summary_counts.get('weekly_count', 0)}, "
                    f"måned={summary_counts.get('monthly_count', 0)}, "
                    f"år={summary_counts.get('yearly_count', 0)}"
                )
                
                summary_result = {
                    "status": "Fullført", 
                    "message": (
                        f"Sammendrag oppdatert for perioden {start_date.date()} til {end_date.date()} "
                        f"(dag={summary_counts.get('daily_count', 0)}, "
                        f"uke={summary_counts.get('weekly_count', 0)}, "
                        f"måned={summary_counts.get('monthly_count', 0)}, "
                        f"år={summary_counts.get('yearly_count', 0)})"
                    )
                }
                logger.info("Sammendragstabeller oppdatert automatisk")
            except Exception as e:
                logger.error(f"Feil under automatisk oppdatering av sammendrag: {e}")
                summary_result = {"status": "Feil", "message": str(e)}
        
        # Kombiner resultater
        combined_result = {
            "sync_result": sync_result,
            "fit_data_result": fit_result,
            "hrv_result": hrv_result,
            "te_result": te_result,
            "weather_result": weather_result,
            "post_te_metrics": post_te_metrics,
            "summary_result": summary_result,
            "status": "Fullført med FIT-data, HRV, Training Effect, vær og sammendrag",
            "summary": {
                "activities_synced": sync_result.get("total_fetched", 0),
                "fit_data_downloaded": fit_result.get("success_count", 0),
                "fit_data_attempted": fit_result.get("total_count", 0),
                "hrv_synced": hrv_result.get("status") == "Fullført",
                "te_synced": te_result.get("status") == "Fullført",
                "weather_synced": weather_result.get("status") == "Fullført",
                "summaries_updated": summary_result.get("status") == "Fullført",
                "metrics_calculated": {
                    "from_sync": sync_result.get("metrics_calculated", {}),
                    "from_fit_data": fit_result.get("metrics_calculated", {})
                },
                "sync_status": sync_result.get("status", "Ukjent"),
                "fit_status": fit_result.get("status", "Ukjent"),
                "hrv_status": hrv_result.get("status", "Ukjent"),
                "te_status": te_result.get("status", "Ukjent"),
                "weather_status": weather_result.get("status", "Ukjent"),
                "summary_status": summary_result.get("status", "Ukjent"),
                "post_te_metrics": post_te_metrics,
            }
        }
        
        logger.info(f"Utvidet synkronisering fullført: {combined_result['summary']}")
        return combined_result

    async def sync_activities(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        ignore_sync_state: bool = False,
        skip_fit_download: bool = False,
    ) -> dict:
        """
        Orkestrerer synkronisering av aktiviteter for en gitt tidsperiode og lagrer dem i databasen.

        Med skip_fit_download=True hentes kun aktivitetslisten fra Garmin (metadata),
        uten FIT-nedlasting eller metrics-beregning — raskere for historisk backfill.
        """
        summary = {"total_fetched": 0, "periods_synced": 0, "status": "Startet"}
        
        try:
            if not await self.garmin_client.initialize():
                logger.error("Kunne ikke initialisere Garmin-klient.")
                summary["status"] = "Feil: Kunne ikke autentisere mot Garmin"
                return summary

            # Inkrementell startdato basert på SyncState, med mulighet for å ignorere
            effective_start = start_date
            if not ignore_sync_state:
                try:
                    act_state = self.db.query(SyncState).filter_by(key="activities").first()
                    if act_state and act_state.last_synced_date and not force_refresh_recent:
                        effective_start = max(
                            effective_start,
                            datetime.combine(act_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
                        )
                except Exception as e:
                    logger.debug(f"Kunne ikke lese SyncState for activities: {e}")

            logger.info(f"Henter aktiviteter fra Garmin: {effective_start.date()} -> {end_date.date()}")
            
            activities_raw = await self.garmin_client.get_activities(effective_start, end_date)
            
            # Beregn grensen for "nylige" data (siste 2 dager)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)

            # Inkluder alle aktiviteter, ikke bare de med GPS-data
            # Dette sikrer at styrketrening, indoor cycling, svømming etc. også synkroniseres
            activities_to_save = [
                act for act in activities_raw
                if act.get('activityId') is not None  # Bare sørg for at vi har en gyldig ID
            ]

            candidate_ids = [str(act.get('activityId')) for act in activities_to_save]
            existing_ids = self.storage.get_existing_activity_ids(self.db, candidate_ids)

            if not activities_to_save:
                summary["status"] = "Fant ingen nye aktiviteter med GPS-data hos Garmin."
                logger.info(summary["status"])
                return summary

            logger.info(f"Fant {len(activities_to_save)} aktiviteter hos Garmin. Lagrer til database.")

            lactate_threshold_speed = None
            lactate_threshold_heart_rate = None
            try:
                threshold_info = await self.garmin_client.get_lactate_threshold_info()
                if threshold_info:
                    lactate_threshold_speed = threshold_info.get("speed_mps")
                    lactate_threshold_heart_rate = threshold_info.get("heart_rate_bpm")
                    self._record_lactate_threshold_history(threshold_info, sync_context="activity_sync")
            except Exception as e:
                logger.warning(f"Kunne ikke hente lactate threshold speed: {e}")
            
            activity_type_cache = {}
            added_count = 0
            inserted_activity_ids: List[str] = []
            buffered_parquet_records: List[Dict[str, Any]] = []
            refreshed_parquet_activity_ids: List[int] = []

            for act_data in activities_to_save:
                activity_id = str(act_data.get('activityId'))

                if not activity_id:
                    continue
                    
                # Sjekk om aktiviteten er nylig og om vi skal force refresh
                activity_start_time = parse_activity_start_from_json(act_data)
                is_recent = activity_start_time >= recent_cutoff
                
                # Hvis ignore_sync_state er True (brukt ved manuell synk av valgt periode),
                # skal vi alltid overskrive eksisterende aktiviteter i perioden
                if ignore_sync_state:
                    should_skip = False
                    if activity_id in existing_ids:
                        logger.debug(
                            "Oppdaterer eksisterende aktivitet %s (ignore_sync_state=True, overskriver alltid).",
                            activity_id,
                        )
                        existing_activity = self.db.query(Activity).filter_by(activity_id=activity_id).first()
                        if existing_activity:
                            self.db.delete(existing_activity)
                            refreshed_parquet_activity_ids.append(int(activity_id))
                else:
                    # Normal logikk: hopp over hvis ikke nylig, eller oppdater hvis force_refresh_recent
                    should_skip = (activity_id in existing_ids and 
                                  not (force_refresh_recent and is_recent))
                    
                    if activity_id in existing_ids and force_refresh_recent and is_recent:
                        logger.debug(
                            "Oppdaterer eksisterende aktivitet %s (force_refresh_recent=True).",
                            activity_id,
                        )
                        # Slett eksisterende aktivitet først
                        existing_activity = self.db.query(Activity).filter_by(activity_id=activity_id).first()
                        if existing_activity:
                            self.db.delete(existing_activity)
                            refreshed_parquet_activity_ids.append(int(activity_id))
                
                if should_skip:
                    continue

                act_type_block = act_data.get("activityType") or {}
                activity_type_key = act_type_block.get("typeKey")

                details_json = None
                if not skip_fit_download and not is_indoor_type_key(activity_type_key):
                    # Hent detaljerte data (FIT-fil) for utendørsaktiviteter.
                    fit_data = await self.garmin_client.get_activity_details(activity_id)
                    if fit_data:
                        details_json = self._parse_fit_data(fit_data)

                        if details_json and 'records' in details_json:
                            parquet_records = self.fit_sync._to_parquet_records(int(activity_id), details_json)

                            if parquet_records:
                                buffered_parquet_records.extend(parquet_records)
                            else:
                                logger.warning(f"Ingen gyldige FIT-records funnet for aktivitet {activity_id}")
                        else:
                            logger.warning(f"Ingen FIT-records tilgjengelig for aktivitet {activity_id}")
                    else:
                        logger.warning(f"Ingen FIT-data tilgjengelig for aktivitet {activity_id}")
                elif not skip_fit_download and is_indoor_type_key(activity_type_key):
                    logger.debug(
                        "Hopper over FIT-nedlasting for innendørs aktivitet %s (%s)",
                        activity_id,
                        activity_type_key,
                    )

                # Håndter ActivityType
                activity_type_obj = None
                if activity_type_key:
                    if activity_type_key in activity_type_cache:
                        activity_type_obj = activity_type_cache[activity_type_key]
                    else:
                        activity_type_obj = self.db.query(ActivityType).filter_by(type_key=activity_type_key).first()
                        if not activity_type_obj:
                            parent_type_key = act_type_block.get("parentTypeKey", "unknown")
                            activity_type_obj = ActivityType(type_key=activity_type_key, parent_type_key=parent_type_key)
                            self.db.add(activity_type_obj)
                            self.db.flush()
                        activity_type_cache[activity_type_key] = activity_type_obj

                # Konverter pace/speed — Garmin averagePace er min/km, lagres som s/km
                avg_pace = normalize_garmin_average_pace(act_data.get("averagePace"))
                avg_speed = act_data.get("averageSpeed") or 0
                if (not avg_speed or avg_speed <= 0) and avg_pace:
                    avg_speed = 1000.0 / avg_pace
                elif not avg_pace and avg_speed and avg_speed > 0:
                    avg_pace = derive_average_pace_sec_per_km(average_speed=avg_speed)
                elif not avg_pace:
                    avg_pace = derive_average_pace_sec_per_km(
                        distance_m=act_data.get("distance"),
                        duration_s=act_data.get("duration"),
                    )

                start_time = parse_activity_start_from_json(act_data)
                
                # Hent elevation gain fra Garmin API (kan være i ulike felter)
                elevation_gain = (
                    act_data.get('elevationGain') or 
                    act_data.get('totalElevationGain') or 
                    act_data.get('elevationGainMeters') or
                    None
                )
                elevation_loss = (
                    act_data.get('elevationLoss') or 
                    act_data.get('totalElevationLoss') or 
                    act_data.get('elevationLossMeters') or
                    None
                )
                
                # Hvis elevation gain ikke er i aktivitetslisten, prøv å hente fra FIT-data
                if elevation_gain is None and details_json:
                    elevation_gain = details_json.get('total_ascent') or details_json.get('elevation_gain')
                if elevation_loss is None and details_json:
                    elevation_loss = details_json.get('total_descent') or details_json.get('elevation_loss')
                
                # Hvis elevation gain fortsatt mangler, prøv å hente fra activity-service
                if elevation_gain is None and is_recent:
                    try:
                        epoc_data = await self.garmin_client.get_activity_epoc_data(activity_id)
                        if isinstance(epoc_data, dict):
                            ep_gain = self._extract_numeric_value(epoc_data.get("elevation_gain"))
                            ep_loss = self._extract_numeric_value(epoc_data.get("elevation_loss"))
                            if elevation_gain is None:
                                elevation_gain = ep_gain
                            if elevation_loss is None:
                                elevation_loss = ep_loss
                    except Exception as e:
                        logger.debug(f"Kunne ikke hente elevation gain fra activity-service for {activity_id}: {e}")

                list_fields = extract_activity_list_fields(act_data)
                weather_fields = extract_garmin_weather_fields(act_data)
                total_steps = list_fields["total_steps"]
                if total_steps is None:
                    total_steps = derive_total_steps(
                        distance_m=act_data.get("distance"),
                        average_speed_mps=avg_speed if avg_speed and avg_speed > 0 else None,
                        average_running_cadence_spm=act_data.get("averageRunningCadenceInStepsPerMinute"),
                    )
                if isinstance(details_json, dict):
                    for key in ("minTemperature", "maxTemperature"):
                        if act_data.get(key) is not None:
                            details_json[key] = act_data.get(key)

                new_activity = Activity(
                    activity_id=activity_id,
                    activity_name=act_data.get('activityName'),
                    start_time=start_time,
                    distance=act_data.get('distance'),
                    duration=act_data.get('duration'),
                    moving_duration=list_fields["moving_duration"],
                    elapsed_duration=list_fields["elapsed_duration"],
                    total_steps=total_steps,
                    min_elevation=list_fields["min_elevation"],
                    max_elevation=list_fields["max_elevation"],
                    calories=act_data.get('calories'),
                    vo2_max=act_data.get('vO2MaxValue'),
                    vo2_max_precise=extract_vo2_max_precise(act_data),
                    average_heart_rate=act_data.get('averageHR'),
                    max_heart_rate=act_data.get('maxHR'),
                    min_heart_rate=act_data.get('minHR'),
                    average_speed=avg_speed,
                    average_moving_speed=act_data.get('averageMovingSpeed'),
                    avg_grade_adjusted_speed=act_data.get('avgGradeAdjustedSpeed'),
                    average_pace=avg_pace,
                    activity_type_id=activity_type_obj.id if activity_type_obj else None,
                    average_running_cadence=act_data.get('averageRunningCadenceInStepsPerMinute'),
                    max_running_cadence=list_fields["max_running_cadence"],
                    total_training_effect=act_data.get('aerobicTrainingEffect') or act_data.get('trainingEffect'),
                    total_anaerobic_training_effect=act_data.get('anaerobicTrainingEffect'),
                    training_effect_label=act_data.get('trainingEffectLabel'),
                    aerobic_training_effect_message=act_data.get('aerobicTrainingEffectMessage'),
                    anaerobic_training_effect_message=act_data.get('anaerobicTrainingEffectMessage'),
                    epoc=act_data.get('activityTrainingLoad'),  # EPOC data
                    lactate_threshold_heart_rate=lactate_threshold_heart_rate,
                    lactate_threshold_speed=lactate_threshold_speed,  # Lactate threshold speed
                    total_ascent=elevation_gain,  # Elevation gain i meter
                    total_descent=elevation_loss,  # Elevation loss i meter
                    temperature=weather_fields.get("temperature"),
                    weather_condition=weather_fields.get("weather_condition"),
                    detailed_metrics=details_json
                )
                self.db.add(new_activity)
                added_count += 1
                inserted_activity_ids.append(activity_id)

            if buffered_parquet_records:
                try:
                    logger.info(
                        f"Lagrer {len(buffered_parquet_records)} bufrede FIT-records til parquet i én batch..."
                    )
                    self.storage.save_activity_details(
                        buffered_parquet_records,
                        replace_activity_ids=refreshed_parquet_activity_ids or None,
                    )
                except Exception as e:
                    logger.error(f"Feil ved batch-lagring av FIT-data til parquet: {e}")

            self.db.commit()

            # Fyll inn lactate threshold på eldre løpeaktiviteter som mangler verdi.
            # Eksisterende historiske verdier skal bevares.
            try:
                await self._update_lactate_threshold_for_all_running_activities()
            except Exception as e:
                logger.warning(f"Feil ved oppdatering av lactate threshold for løpeaktiviteter: {e}")

            # Oppdater SyncState for aktiviteter
            try:
                if added_count > 0:
                    # Sett siste synketdato til sluttdatoen vi nettopp ba om, eller siste aktivitet sin dato
                    last_date = end_date.date()
                    try:
                        latest = max(
                            parse_activity_start_from_json(a).date()
                            for a in activities_to_save
                            if a.get('startTimeGMT') or a.get('startTimeInSeconds') or a.get('startTimeLocal')
                        )
                        last_date = latest
                    except Exception:
                        pass
                    act_state = self.db.query(SyncState).filter_by(key="activities").first()
                    if not act_state:
                        act_state = SyncState(key="activities")
                        self.db.add(act_state)
                    act_state.last_synced_date = last_date
                    act_state.last_synced_at = datetime.now(timezone.utc)
                    self.db.commit()
            except Exception as e:
                logger.warning(f"Kunne ikke oppdatere SyncState for activities: {e}")
            
            summary["total_fetched"] = added_count
            summary["activity_ids"] = inserted_activity_ids
            if skip_fit_download:
                summary["metrics_calculated"] = {"skipped": True, "total_activities": len(inserted_activity_ids)}
            else:
                logger.info("Starter beregning av alle metrics for nye aktiviteter...")
                metrics_results = []
                self.metrics_service.begin_batch()
                try:
                    for aid in inserted_activity_ids:
                        metrics_result = self._calculate_metrics_for_new_activity(aid)
                        metrics_results.append(metrics_result)
                finally:
                    self.metrics_service.end_batch()

                successful_tss = sum(1 for r in metrics_results if r["tss_calculated"])
                successful_power = sum(1 for r in metrics_results if r["power_calculated"])
                successful_running_economy = sum(1 for r in metrics_results if r["running_economy_calculated"])
                successful_negative_splits = sum(1 for r in metrics_results if r["negative_split_calculated"])
                successful_decouplings = sum(1 for r in metrics_results if r["decoupling_calculated"])
                successful_hrv = sum(1 for r in metrics_results if r["hrv_calculated"])

                logger.info(
                    "Metrics-beregning fullført for %s aktiviteter: TSS=%s, power=%s, "
                    "løpsøkonomi=%s, negative split=%s, decoupling=%s, HRV=%s",
                    len(metrics_results),
                    successful_tss,
                    successful_power,
                    successful_running_economy,
                    successful_negative_splits,
                    successful_decouplings,
                    successful_hrv,
                )
                summary["metrics_calculated"] = {
                    "tss": successful_tss,
                    "power": successful_power,
                    "running_economy": successful_running_economy,
                    "negative_split": successful_negative_splits,
                    "decoupling": successful_decouplings,
                    "hrv_available": successful_hrv,
                    "total_activities": len(metrics_results),
                }
            summary["status"] = "Fullført"
            logger.info(f"Synkronisering fra Garmin fullført. La til {added_count} nye aktiviteter i databasen.")

        except Exception as e:
            logger.critical(f"En alvorlig feil oppstod under Garmin-synkronisering: {e}", exc_info=True)
            self.db.rollback()  # Rull tilbake endringer ved feil
            summary["status"] = f"Feil: {e}"
        
        return summary 

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
            from .body_battery_service import BodyBatteryService
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
        values = [
            float(value)
            for value in (activity.min_elevation, activity.max_elevation)
            if value is not None
        ]
        if not values:
            return None
        return sum(values) / len(values)

    def _activity_route_fingerprint(self, activity_id: str) -> Optional[ActivityRouteFingerprint]:
        return (
            self.db.query(ActivityRouteFingerprint)
            .filter_by(activity_id=str(activity_id))
            .first()
        )

    def _get_activity_details_frame(self, activity_id: str) -> Optional[pd.DataFrame]:
        try:
            try:
                details = self.storage.get_activity_details(int(activity_id))
            except (TypeError, ValueError):
                details = self.storage.get_activity_details(activity_id)  # type: ignore[arg-type]
        except Exception as exc:
            logger.debug("Kunne ikke hente aktivitetsdetaljer for værsampling %s: %s", activity_id, exc)
            return None

        if details is None or details.empty:
            return None
        return details.copy()

    def _build_weather_sample_points(
        self,
        activity: Activity,
        *,
        interval_minutes: int = 15,
    ) -> List[Dict[str, Any]]:
        details = self._get_activity_details_frame(str(activity.activity_id))
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
                            key=lambda point: abs((point["target_time"] - target_time).total_seconds()),
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

        route = self._activity_route_fingerprint(str(activity.activity_id))
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

    async def _get_weather_for_sample_point(
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

    def _aggregate_weather_snapshots(self, snapshots: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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
                angle = math.degrees(math.atan2(sin_sum / len(directions), cos_sum / len(directions)))
                if angle < 0:
                    angle += 360.0
                result["wind_direction"] = angle

        conditions = [snapshot.get("weather_condition") for snapshot in snapshots if snapshot.get("weather_condition")]
        if conditions:
            result["weather_condition"] = Counter(conditions).most_common(1)[0][0]

        return result if result else None

    def _apply_garmin_list_weather_if_missing(self, activity: Activity) -> bool:
        """Behold Garmin-liste temperatur hvis API-berikelse ikke gir mer."""
        if activity.temperature is not None:
            return False
        metrics = activity.detailed_metrics if isinstance(activity.detailed_metrics, dict) else {}
        for key in ("minTemperature", "maxTemperature"):
            if metrics.get(key) is not None:
                fields = extract_garmin_weather_fields(metrics)
                if fields.get("temperature") is not None:
                    activity.temperature = fields["temperature"]
                    if not activity.weather_condition:
                        activity.weather_condition = fields.get("weather_condition")
                    return True
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

        sample_points = self._build_weather_sample_points(activity)
        if not sample_points:
            logger.debug("Vær hoppet over %s: ingen GPS-punkter for sampling", activity_id)
            return self._apply_garmin_list_weather_if_missing(activity)

        snapshots: List[Dict[str, Any]] = []
        altitude = self._activity_weather_altitude(activity)
        for sample in sample_points:
            weather = await self._get_weather_for_sample_point(
                target_time=sample["target_time"],
                latitude=float(sample["latitude"]),
                longitude=float(sample["longitude"]),
                altitude=altitude,
            )
            if weather:
                snapshots.append(weather)

        weather = self._aggregate_weather_snapshots(snapshots)
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
            changed = self._apply_garmin_list_weather_if_missing(activity)

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
                        datetime.combine(state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc)
                        + timedelta(days=1),
                    )
            except Exception as exc:
                logger.debug("Kunne ikke lese SyncState for activity_weather: %s", exc)

        if effective_start > end_date:
            return {"status": "Fullført", "updated_count": 0, "skipped_count": 0, "failed_count": 0}

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
                logger.warning("Kunne ikke synkronisere vær for aktivitet %s: %s", activity.activity_id, exc)
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
        try:
            from .health_metric_backfill import backfill_activity_vo2_precise_in_range

            backfilled = backfill_activity_vo2_precise_in_range(
                self.db,
                effective_start.date(),
                end_day,
            )
            if backfilled:
                logger.info(
                    "Fylte vo2_max_precise på %s aktiviteter etter performance metrics-synk",
                    backfilled,
                )
        except Exception as e:
            logger.warning(f"Kunne ikke backfille vo2_max_precise etter performance-synk: {e}")

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
