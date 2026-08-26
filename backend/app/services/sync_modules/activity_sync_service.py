"""Importer for aktivitets-synk (liste / JSON / FIT-orkestrering).

Del av SyncService-oppdelingen: coordinator beholder offentlig API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import logging

from ...database.models.activity import Activity, ActivityType
from ...database.models.sync_state import SyncState
from ..activity_field_extraction import (
    extract_activity_list_fields,
    extract_garmin_weather_fields,
    extract_vo2_max_precise,
)
from ..activity_upsert import apply_activity_field_updates
from ..activity_metric_backfill import (
    derive_average_pace_sec_per_km,
    derive_total_steps,
    normalize_garmin_average_pace,
)
from ..sync_run_service import (
    advance_activities_sync_state,
    update_sync_run_checkpoint,
)
from ...utils.activity_filters import is_indoor_type_key

logger = logging.getLogger(__name__)

ACTIVITY_SYNC_COMMIT_BATCH_SIZE = 100


def _link_recommendation_execution(db, activity: Activity) -> None:
    try:
        from ..recommendation_execution_service import RecommendationExecutionService

        db.flush()
        RecommendationExecutionService(db).link_activity(activity, commit=False)
    except Exception:
        logger.debug("Kunne ikke koble aktivitet %s til recommendation ledger", getattr(activity, "activity_id", None), exc_info=True)


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


class ActivitySyncService:
    def __init__(self, sync_service: Any):
        self._sync = sync_service

    # --- proxy til SyncService-ressurser / delte hjelpere ---
    @property
    def db(self):
        return self._sync.db

    @property
    def storage(self):
        return self._sync.storage

    @property
    def garmin_client(self):
        return self._sync.garmin_client

    @property
    def fit_sync(self):
        return self._sync.fit_sync

    @property
    def metrics_service(self):
        return self._sync.metrics_service

    def _parse_fit_data(self, fit_data: bytes):
        return self._sync._parse_fit_data(fit_data)

    def _extract_numeric_value(self, value):
        return self._sync._extract_numeric_value(value)

    def _record_lactate_threshold_history(self, *args, **kwargs):
        return self._sync._record_lactate_threshold_history(*args, **kwargs)

    def _calculate_metrics_for_new_activity(self, activity_id: str) -> dict:
        return self._sync._calculate_metrics_for_new_activity(activity_id)

    async def _update_lactate_threshold_for_all_running_activities(self):
        return await self._sync._update_lactate_threshold_for_all_running_activities()

    async def sync_health_data(self, *args, **kwargs):
        return await self._sync.sync_health_data(*args, **kwargs)

    async def download_fit_data_for_period(self, *args, **kwargs):
        return await self._sync.download_fit_data_for_period(*args, **kwargs)

    async def sync_training_effect_data(self, *args, **kwargs):
        return await self._sync.sync_training_effect_data(*args, **kwargs)

    async def sync_activity_weather(self, *args, **kwargs):
        return await self._sync.sync_activity_weather(*args, **kwargs)

    def _commit_activity_batch(
        self,
        *,
        buffered_parquet_records: Optional[List[Dict[str, Any]]] = None,
        refreshed_parquet_activity_ids: Optional[List[int]] = None,
    ) -> None:
        """Commit én batch: evt. parquet først, deretter DB-transaksjon."""
        if buffered_parquet_records:
            parquet_batch = list(buffered_parquet_records)
            replace_ids = (
                list(refreshed_parquet_activity_ids)
                if refreshed_parquet_activity_ids
                else None
            )
            try:
                logger.info(
                    "Lagrer %s bufrede FIT-records til parquet (batch-commit)...",
                    len(parquet_batch),
                )
                self.storage.save_activity_details(
                    parquet_batch,
                    replace_activity_ids=replace_ids,
                )
            except Exception as e:
                logger.error("Feil ved batch-lagring av FIT-data til parquet: %s", e)
            buffered_parquet_records.clear()
            if refreshed_parquet_activity_ids is not None:
                refreshed_parquet_activity_ids.clear()
        self.db.commit()

    async def sync_json_to_db(self) -> dict:
        """
        Leser alle aktiviteter fra JSON-filer og synkroniserer dem til databasen.
        """
        logger.info("Starter synkronisering fra JSON-filer til database.")

        lactate_threshold_speed: Optional[float] = None
        lactate_threshold_heart_rate: Optional[float] = None
        try:
            if self.garmin_client is not None:
                threshold_info = await self.garmin_client.get_lactate_threshold_info()
                if threshold_info:
                    lactate_threshold_speed = threshold_info.get("speed_mps")
                    lactate_threshold_heart_rate = threshold_info.get("heart_rate_bpm")
                    self._record_lactate_threshold_history(
                        threshold_info, sync_context="json_sync"
                    )
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
        updated_count = 0
        skipped_count = 0  # unchanged
        pending_since_commit = 0
        
        # Ordbok for å cache ActivityType-objekter
        activity_type_cache = {}

        for act_data in json_activities:
            raw_id = act_data.get("activityId")
            if raw_id is None:
                skipped_count += 1
                continue
            activity_id = str(raw_id)

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

            field_payload = {
                "activity_name": act_data.get('activityName'),
                "start_time": start_time,
                "distance": act_data.get('distance'),
                "duration": act_data.get('duration'),
                "moving_duration": list_fields["moving_duration"],
                "elapsed_duration": list_fields["elapsed_duration"],
                "total_steps": total_steps,
                "min_elevation": list_fields["min_elevation"],
                "max_elevation": list_fields["max_elevation"],
                "calories": act_data.get('calories'),
                "vo2_max": act_data.get('vO2MaxValue'),
                "vo2_max_precise": extract_vo2_max_precise(act_data),
                "average_heart_rate": act_data.get('averageHR'),
                "max_heart_rate": act_data.get('maxHR'),
                "min_heart_rate": act_data.get('minHR'),
                "average_speed": avg_speed if avg_speed and avg_speed > 0 else None,
                "average_moving_speed": act_data.get('averageMovingSpeed'),
                "avg_grade_adjusted_speed": act_data.get('avgGradeAdjustedSpeed'),
                "average_pace": avg_pace,
                "activity_type_id": activity_type_obj.id if activity_type_obj else None,
                "average_running_cadence": act_data.get('averageRunningCadenceInStepsPerMinute'),
                "max_running_cadence": list_fields["max_running_cadence"],
                "total_training_effect": act_data.get('aerobicTrainingEffect') or act_data.get('trainingEffect'),
                "total_anaerobic_training_effect": act_data.get('anaerobicTrainingEffect'),
                "training_effect_label": act_data.get('trainingEffectLabel'),
                "aerobic_training_effect_message": act_data.get('aerobicTrainingEffectMessage'),
                "anaerobic_training_effect_message": act_data.get('anaerobicTrainingEffectMessage'),
                "lactate_threshold_heart_rate": lactate_threshold_heart_rate,
                "lactate_threshold_speed": lactate_threshold_speed,
            }

            if activity_id in existing_ids:
                existing = self.db.query(Activity).filter_by(activity_id=activity_id).first()
                if existing is None:
                    existing_ids.discard(activity_id)
                else:
                    changed, _ = apply_activity_field_updates(existing, field_payload, overwrite=False)
                    if changed:
                        updated_count += 1
                    else:
                        skipped_count += 1
                    pending_since_commit += 1
                    if pending_since_commit >= ACTIVITY_SYNC_COMMIT_BATCH_SIZE:
                        self._commit_activity_batch()
                        pending_since_commit = 0
                    continue

            new_activity = Activity(activity_id=activity_id, **field_payload)
            self.db.add(new_activity)
            added_count += 1
            existing_ids.add(activity_id)
            _link_recommendation_execution(self.db, new_activity)

            pending_since_commit += 1
            if pending_since_commit >= ACTIVITY_SYNC_COMMIT_BATCH_SIZE:
                self._commit_activity_batch()
                pending_since_commit = 0

        if pending_since_commit > 0:
            self._commit_activity_batch()
        logger.info(
            "JSON-synk fullført. inserted=%s updated=%s unchanged=%s",
            added_count,
            updated_count,
            skipped_count,
        )
        return {
            "status": "Fullført",
            "added": added_count,
            "added_count": added_count,
            "inserted": added_count,
            "updated": updated_count,
            "updated_count": updated_count,
            "skipped": skipped_count,
            "skipped_count": skipped_count,
            "unchanged_count": skipped_count,
        }

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
        sync_run_id: Optional[int] = None,
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
        sync_result = await self.sync_activities(
            start_date,
            end_date,
            force_refresh_recent,
            ignore_sync_state,
            sync_run_id=sync_run_id,
        )
        
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
        sync_run_id: Optional[int] = None,
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
            updated_count = 0
            skipped_count = 0  # unchanged — bakoverkompatibelt alias
            unchanged_count = 0
            pending_since_commit = 0
            batch_latest_date = None
            batch_last_activity_id: Optional[str] = None
            inserted_activity_ids: List[str] = []
            updated_activity_ids: List[str] = []
            buffered_parquet_records: List[Dict[str, Any]] = []
            refreshed_parquet_activity_ids: List[int] = []

            def _persist_checkpoint() -> None:
                nonlocal batch_latest_date, batch_last_activity_id
                if batch_latest_date is None:
                    return
                try:
                    advance_activities_sync_state(self.db, batch_latest_date)
                    if sync_run_id is not None:
                        update_sync_run_checkpoint(
                            self.db,
                            sync_run_id,
                            {
                                "last_activity_id": batch_last_activity_id,
                                "last_start_date": batch_latest_date.isoformat(),
                                "processed": added_count + updated_count + unchanged_count,
                            },
                            inserted=added_count,
                            updated=updated_count,
                            skipped=unchanged_count,
                        )
                except Exception as checkpoint_exc:
                    logger.warning(
                        "Kunne ikke lagre aktivitetssynk-checkpoint: %s",
                        checkpoint_exc,
                    )
                batch_latest_date = None
                batch_last_activity_id = None

            for act_data in activities_to_save:
                activity_id = str(act_data.get('activityId'))

                if not activity_id:
                    continue
                    
                activity_start_time = parse_activity_start_from_json(act_data)
                is_recent = activity_start_time >= recent_cutoff
                exists = activity_id in existing_ids
                # Overskriv list-felter ved manuell periode-synk eller force-refresh av nylige
                overwrite = bool(ignore_sync_state or (force_refresh_recent and is_recent))

                existing_activity = None
                if exists:
                    existing_activity = self.db.query(Activity).filter_by(activity_id=activity_id).first()
                    if existing_activity is None:
                        exists = False

                act_type_block = act_data.get("activityType") or {}
                activity_type_key = act_type_block.get("typeKey")

                # Hent FIT når ny, overwrite, eller eksisterende mangler detailed_metrics
                needs_fit = (
                    not skip_fit_download
                    and not is_indoor_type_key(activity_type_key)
                    and (
                        not exists
                        or overwrite
                        or (existing_activity is not None and existing_activity.detailed_metrics is None)
                    )
                )

                details_json = None
                if needs_fit:
                    fit_data = await self.garmin_client.get_activity_details(activity_id)
                    if fit_data:
                        details_json = self._parse_fit_data(fit_data)

                        if details_json and 'records' in details_json:
                            parquet_records = self.fit_sync._to_parquet_records(int(activity_id), details_json)

                            if parquet_records:
                                buffered_parquet_records.extend(parquet_records)
                                if exists:
                                    refreshed_parquet_activity_ids.append(int(activity_id))
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
                # Temperatur fra Garmin-listen lagres i Activity-kolonner (lag 2),
                # ikke blandet inn i detailed_metrics (rå FIT-JSON).

                field_payload: Dict[str, Any] = {
                    "activity_name": act_data.get('activityName'),
                    "start_time": start_time,
                    "distance": act_data.get('distance'),
                    "duration": act_data.get('duration'),
                    "moving_duration": list_fields["moving_duration"],
                    "elapsed_duration": list_fields["elapsed_duration"],
                    "total_steps": total_steps,
                    "min_elevation": list_fields["min_elevation"],
                    "max_elevation": list_fields["max_elevation"],
                    "calories": act_data.get('calories'),
                    "vo2_max": act_data.get('vO2MaxValue'),
                    "vo2_max_precise": extract_vo2_max_precise(act_data),
                    "average_heart_rate": act_data.get('averageHR'),
                    "max_heart_rate": act_data.get('maxHR'),
                    "min_heart_rate": act_data.get('minHR'),
                    "average_speed": avg_speed if avg_speed and avg_speed > 0 else None,
                    "average_moving_speed": act_data.get('averageMovingSpeed'),
                    "avg_grade_adjusted_speed": act_data.get('avgGradeAdjustedSpeed'),
                    "average_pace": avg_pace,
                    "activity_type_id": activity_type_obj.id if activity_type_obj else None,
                    "average_running_cadence": act_data.get('averageRunningCadenceInStepsPerMinute'),
                    "max_running_cadence": list_fields["max_running_cadence"],
                    "total_training_effect": act_data.get('aerobicTrainingEffect') or act_data.get('trainingEffect'),
                    "total_anaerobic_training_effect": act_data.get('anaerobicTrainingEffect'),
                    "training_effect_label": act_data.get('trainingEffectLabel'),
                    "aerobic_training_effect_message": act_data.get('aerobicTrainingEffectMessage'),
                    "anaerobic_training_effect_message": act_data.get('anaerobicTrainingEffectMessage'),
                    "epoc": act_data.get('activityTrainingLoad'),
                    "lactate_threshold_heart_rate": lactate_threshold_heart_rate,
                    "lactate_threshold_speed": lactate_threshold_speed,
                    "total_ascent": elevation_gain,
                    "total_descent": elevation_loss,
                    "temperature": weather_fields.get("temperature"),
                    "weather_condition": weather_fields.get("weather_condition"),
                    "detailed_metrics": details_json,
                }

                if not exists:
                    new_activity = Activity(activity_id=activity_id, **{
                        k: v for k, v in field_payload.items() if k != "detailed_metrics" or v is not None
                    })
                    new_activity.detailed_metrics = details_json
                    self.db.add(new_activity)
                    added_count += 1
                    inserted_activity_ids.append(activity_id)
                    existing_ids.add(activity_id)
                    _link_recommendation_execution(self.db, new_activity)
                else:
                    changed, changed_fields = apply_activity_field_updates(
                        existing_activity,
                        field_payload,
                        overwrite=overwrite,
                    )
                    if changed:
                        updated_count += 1
                        updated_activity_ids.append(activity_id)
                        logger.debug(
                            "Oppdaterte aktivitet %s (%s): %s",
                            activity_id,
                            "overwrite" if overwrite else "richer",
                            ", ".join(changed_fields[:12]),
                        )
                    else:
                        unchanged_count += 1
                        skipped_count += 1

                act_date = activity_start_time.date()
                if batch_latest_date is None or act_date > batch_latest_date:
                    batch_latest_date = act_date
                batch_last_activity_id = activity_id

                pending_since_commit += 1
                if pending_since_commit >= ACTIVITY_SYNC_COMMIT_BATCH_SIZE:
                    self._commit_activity_batch(
                        buffered_parquet_records=buffered_parquet_records,
                        refreshed_parquet_activity_ids=refreshed_parquet_activity_ids,
                    )
                    _persist_checkpoint()
                    pending_since_commit = 0

            if pending_since_commit > 0 or buffered_parquet_records:
                self._commit_activity_batch(
                    buffered_parquet_records=buffered_parquet_records,
                    refreshed_parquet_activity_ids=refreshed_parquet_activity_ids,
                )
                _persist_checkpoint()

            # Fyll inn lactate threshold på eldre løpeaktiviteter som mangler verdi.
            # Eksisterende historiske verdier skal bevares.
            try:
                await self._update_lactate_threshold_for_all_running_activities()
            except Exception as e:
                logger.warning(f"Feil ved oppdatering av lactate threshold for løpeaktiviteter: {e}")

            # Endelig SyncState (dekker også tilfeller uten inserts/updates i siste batch)
            try:
                if added_count > 0 or updated_count > 0:
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
                    advance_activities_sync_state(self.db, last_date)
                    if sync_run_id is not None:
                        update_sync_run_checkpoint(
                            self.db,
                            sync_run_id,
                            {
                                "last_activity_id": (
                                    inserted_activity_ids[-1]
                                    if inserted_activity_ids
                                    else (
                                        updated_activity_ids[-1]
                                        if updated_activity_ids
                                        else None
                                    )
                                ),
                                "last_start_date": last_date.isoformat(),
                                "processed": added_count + updated_count + unchanged_count,
                                "complete": True,
                            },
                            inserted=added_count,
                            updated=updated_count,
                            skipped=unchanged_count,
                        )
            except Exception as e:
                logger.warning(f"Kunne ikke oppdatere SyncState for activities: {e}")
            
            summary["total_fetched"] = added_count + updated_count
            summary["added_count"] = added_count
            summary["inserted"] = added_count
            summary["updated_count"] = updated_count
            summary["updated"] = updated_count
            summary["skipped_count"] = skipped_count
            summary["unchanged_count"] = unchanged_count
            summary["activity_ids"] = inserted_activity_ids
            summary["updated_activity_ids"] = updated_activity_ids
            logger.info(
                "Aktivitetssynk: inserted=%s updated=%s unchanged=%s",
                added_count,
                updated_count,
                unchanged_count,
            )
            # Beregn metrics for nye + oppdaterte (rikere data kan påvirke beregninger)
            metrics_ids = list(dict.fromkeys(inserted_activity_ids + updated_activity_ids))
            if skip_fit_download:
                summary["metrics_calculated"] = {"skipped": True, "total_activities": len(metrics_ids)}
            else:
                logger.info("Starter beregning av alle metrics for nye/oppdaterte aktiviteter...")
                metrics_results = []
                self.metrics_service.begin_batch()
                try:
                    for aid in metrics_ids:
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

