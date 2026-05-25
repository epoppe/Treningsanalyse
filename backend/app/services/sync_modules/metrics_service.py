from __future__ import annotations

from datetime import datetime
from typing import Any
import logging

from sqlalchemy import or_

from ...database.models.activity import Activity, ActivityType

logger = logging.getLogger(__name__)


class SyncMetricsService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    def calculate_metrics_for_new_activity(self, activity_id: str) -> dict:
        results = {
            "activity_id": activity_id,
            "tss_calculated": False,
            "power_calculated": False,
            "running_economy_calculated": False,
            "negative_split_calculated": False,
            "decoupling_calculated": False,
            "efficiency_calculated": False,
            "fatigue_resistance_calculated": False,
            "performance_snapshots_updated": False,
            "hrv_calculated": False,
            "errors": [],
        }
        try:
            activity_id_int = int(activity_id)
            activity = self.sync_service.db.query(Activity).filter_by(activity_id=activity_id).first()
            if not activity:
                results["errors"].append("Aktivitet ikke funnet i database")
                return results

            if activity.training_stress_score is None:
                try:
                    from ..training_stress_service import TrainingStressService

                    tss_service = TrainingStressService(self.sync_service.db)
                    tss = tss_service.calculate_tss_for_activity(activity)
                    if tss is not None:
                        activity.training_stress_score = tss
                        results["tss_calculated"] = True
                        logger.info(f"✅ Beregnet TSS for aktivitet {activity_id}: {tss}")
                except Exception as exc:
                    logger.warning(f"Feil ved beregning av TSS for aktivitet {activity_id}: {exc}")
                    results["errors"].append(f"TSS feil: {str(exc)}")

            if activity.activity_type and activity.activity_type.type_key == "running":
                if activity.average_power is None:
                    try:
                        from ..power_service import PowerService

                        power_service = PowerService(self.sync_service.storage)
                        power_data = power_service.calculate_activity_power(activity_id_int, self.sync_service.db)
                        if power_data:
                            results["power_calculated"] = True
                            logger.info(
                                f"✅ Beregnet power for aktivitet {activity_id}: {power_data.get('average_power_watts')}W"
                            )
                    except Exception as exc:
                        logger.warning(f"Feil ved beregning av power for aktivitet {activity_id}: {exc}")
                        results["errors"].append(f"Power feil: {str(exc)}")

            if activity.activity_type and "running" in activity.activity_type.type_key:
                if activity.running_economy is None:
                    try:
                        if (
                            activity.average_speed
                            and activity.average_heart_rate
                            and activity.average_speed > 0
                            and activity.average_heart_rate > 0
                        ):
                            speed_kmh = activity.average_speed * 3.6
                            running_economy = (speed_kmh / activity.average_heart_rate) * 100
                            activity.running_economy = round(running_economy, 2)
                            results["running_economy_calculated"] = True
                            logger.info(f"✅ Beregnet løpsøkonomi for aktivitet {activity_id}: {running_economy}")
                    except Exception as exc:
                        logger.warning(f"Feil ved beregning av løpsøkonomi for aktivitet {activity_id}: {exc}")
                        results["errors"].append(f"Running economy feil: {str(exc)}")

            if activity.negative_split_percent is None:
                try:
                    negative_split_result = self.sync_service.analysis_service.calculate_negative_split(
                        activity_id_int, self.sync_service.db
                    )
                    if negative_split_result and "negative_split_percent" in negative_split_result:
                        results["negative_split_calculated"] = True
                        logger.info(
                            "✅ Beregnet negative split for aktivitet %s: %s%%",
                            activity_id,
                            negative_split_result.get("negative_split_percent"),
                        )
                except Exception as exc:
                    logger.debug(f"Kunne ikke beregne negative split for aktivitet {activity_id}: {exc}")

            if (
                activity.decoupling_percent is None
                or activity.avg_efficiency_factor is None
                or activity.decoupling_suitability_flag is None
            ):
                try:
                    efficiency_result = self.sync_service.analysis_service.calculate_efficiency_metrics(
                        activity_id_int, self.sync_service.db
                    )
                    if efficiency_result and "decoupling_percent" in efficiency_result:
                        results["decoupling_calculated"] = True
                        results["efficiency_calculated"] = True
                        logger.info(
                            "✅ Beregnet EF/decoupling for aktivitet %s: EF=%s decoupling=%s%%",
                            activity_id,
                            efficiency_result.get("avg_efficiency_factor"),
                            efficiency_result.get("decoupling_percent"),
                        )
                except Exception as exc:
                    logger.debug(f"Kunne ikke beregne EF/decoupling for aktivitet {activity_id}: {exc}")

            try:
                from ..performance_metrics_service import PerformanceMetricsService

                performance_service = PerformanceMetricsService(
                    self.sync_service.db,
                    self.sync_service.storage,
                )
                fatigue = performance_service.calculate_fatigue_resistance_for_activity(activity)
                if fatigue:
                    results["fatigue_resistance_calculated"] = True
                    logger.info(
                        "✅ Beregnet fatigue resistance for aktivitet %s: %s",
                        activity_id,
                        fatigue.get("fatigue_resistance_score"),
                    )
                performance_service.recalculate_performance_snapshots()
                results["performance_snapshots_updated"] = True
            except Exception as exc:
                logger.debug(f"Kunne ikke oppdatere performance metrics for aktivitet {activity_id}: {exc}")

            try:
                if activity.start_time and activity.start_time.year >= 2023:
                    hrv_data = self.sync_service.analysis_service.get_hrv_for_activity_date(
                        activity_id_int, self.sync_service.db
                    )
                    if hrv_data and hrv_data.get("last_night_avg"):
                        results["hrv_calculated"] = True
                        logger.debug(f"HRV-data tilgjengelig for aktivitet {activity_id}: {hrv_data.get('last_night_avg')}ms")
            except Exception as exc:
                logger.debug(f"HRV-sjekk for aktivitet {activity_id}: {exc}")

            try:
                self.sync_service.db.commit()
                logger.info(f"💾 Lagret alle beregnede verdier for aktivitet {activity_id}")
            except Exception as exc:
                self.sync_service.db.rollback()
                logger.error(f"Feil ved lagring av beregnede verdier for aktivitet {activity_id}: {exc}")
                results["errors"].append(f"Lagringsfeil: {str(exc)}")
        except Exception as exc:
            logger.error(f"Generell feil ved beregning av metrics for aktivitet {activity_id}: {exc}")
            results["errors"].append(f"Generell feil: {str(exc)}")
        return results

    async def update_lactate_threshold_for_all_running_activities(self):
        try:
            current_lactate_threshold = await self.sync_service.garmin_client.get_lactate_threshold_speed()
            if current_lactate_threshold is None:
                logger.debug("Ingen lactate threshold verdi tilgjengelig fra Garmin, hopper over oppdatering")
                return
            logger.info(
                f"🔍 Sjekker manglende lactate threshold verdier. Nåværende verdi fra Garmin: {current_lactate_threshold} m/s"
            )

            running_activities = (
                self.sync_service.db.query(Activity)
                .join(ActivityType)
                .filter(
                    or_(
                        ActivityType.type_key == "running",
                        ActivityType.type_key == "treadmill_running",
                        ActivityType.type_key == "trail_running",
                        ActivityType.type_key == "street_running",
                        ActivityType.parent_type_key == "running",
                    )
                )
                .all()
            )
            if not running_activities:
                logger.debug("Ingen løpeaktiviteter funnet")
                return

            activities_to_update = []
            for activity in running_activities:
                if activity.lactate_threshold_speed is None:
                    activities_to_update.append(activity)
            if not activities_to_update:
                logger.debug(
                    f"Ingen løpeaktiviteter mangler lactate threshold verdi. Bevarer eksisterende historiske verdier ({current_lactate_threshold} m/s nåverdi)"
                )
                return

            logger.info(
                f"📝 Fyller inn lactate threshold for {len(activities_to_update)} løpeaktiviteter til {current_lactate_threshold} m/s"
            )
            updated_count = 0
            for activity in activities_to_update:
                old_value = activity.lactate_threshold_speed
                activity.lactate_threshold_speed = current_lactate_threshold
                updated_count += 1
                if updated_count <= 5:
                    logger.info(
                        f"  - Aktivitet {activity.activity_id} ({activity.start_time.date()}): {old_value} -> {current_lactate_threshold} m/s"
                    )

            self.sync_service.db.commit()
            logger.info(f"✅ Oppdatert lactate threshold for {updated_count} løpeaktiviteter til {current_lactate_threshold} m/s")
        except Exception as exc:
            logger.error(f"Feil ved oppdatering av lactate threshold for løpeaktiviteter: {exc}", exc_info=True)
            self.sync_service.db.rollback()
            raise
