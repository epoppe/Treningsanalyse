"""Importer for Garmin performance- og Training Effect-synk.

Del av SyncService-oppdelingen: coordinator beholder offentlig API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import asyncio
import logging

from ...database.models.activity import Activity, GarminPerformanceMetric
from ...database.models.sync_state import SyncState
from ..activity_data_validation import (
    normalize_ground_contact_time_ms,
    normalize_stride_length_meters,
    validate_and_repair_activity,
)
from ..body_battery_service import BodyBatteryService
from ...utils.activity_filters import is_running_activity

logger = logging.getLogger(__name__)


class PerformanceSyncService:
    def __init__(self, sync_service: Any):
        self._sync = sync_service

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
    def analysis_service(self):
        return self._sync.analysis_service

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
            from ..health_metric_backfill import backfill_activity_vo2_precise_in_range

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

