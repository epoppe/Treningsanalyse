from __future__ import annotations

from datetime import datetime
from typing import Any
import logging

from sqlalchemy import and_, or_

from ...database.models.activity import Activity, ActivityType
from ...utils.activity_filters import is_running_activity
from ..activity_data_validation import validate_and_repair_activity

logger = logging.getLogger(__name__)


def _is_derived_running_activity(activity: Activity) -> bool:
    """Løp og tredemølle kan få negative split, decoupling og løpsøkonomi."""
    return is_running_activity(activity, include_treadmill=True)


def tss_needs_refresh(activity: Activity) -> bool:
    """True når TSS bør beregnes på nytt (mangler eller avviker fra EPOC)."""
    if activity.training_stress_score is None:
        return True
    if activity.epoc and float(activity.epoc) > 0:
        expected = round(float(activity.epoc), 1)
        stored = round(float(activity.training_stress_score), 1)
        return abs(stored - expected) > 0.05
    return False


class SyncMetricsService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service
        self._defer_snapshot_recalc = False
        self._snapshot_recalc_pending = False

    def begin_batch(self) -> None:
        """Unngå full performance-snapshot per aktivitet under batch-synk."""
        self._defer_snapshot_recalc = True
        self._snapshot_recalc_pending = False

    def end_batch(self) -> None:
        """Kjør utsatt performance-snapshot én gang etter batch."""
        self._defer_snapshot_recalc = False
        if self._snapshot_recalc_pending:
            self._recalculate_performance_snapshots_once()

    def _recalculate_performance_snapshots_once(self) -> None:
        try:
            from ..performance_metrics_service import PerformanceMetricsService

            performance_service = PerformanceMetricsService(
                self.sync_service.db,
                self.sync_service.storage,
            )
            performance_service.recalculate_performance_snapshots()
            self._snapshot_recalc_pending = False
            logger.info("✅ Performance snapshots oppdatert (batch)")
        except Exception as exc:
            logger.warning(f"Kunne ikke oppdatere performance snapshots: {exc}")

    def refresh_metrics_after_te_sync(self, start_date: datetime, end_date: datetime) -> dict:
        """
        Oppdater TSS etter Training Effect har satt EPOC (TSS = EPOC når tilgjengelig).
        Kalles etter sync_training_effect_data i sync_activities_with_fit_data.
        """
        summary = {"tss_refreshed": 0, "activities_checked": 0}
        activities = (
            self.sync_service.db.query(Activity)
            .filter(
                and_(
                    Activity.start_time >= start_date,
                    Activity.start_time <= end_date,
                )
            )
            .all()
        )
        summary["activities_checked"] = len(activities)
        for activity in activities:
            if not tss_needs_refresh(activity):
                continue
            if self._calculate_tss(activity, str(activity.activity_id)):
                summary["tss_refreshed"] += 1
        try:
            self.sync_service.db.commit()
        except Exception as exc:
            self.sync_service.db.rollback()
            logger.error(f"Feil ved lagring etter TE-metrics refresh: {exc}")
        if summary["tss_refreshed"] > 0:
            self._recalculate_performance_snapshots_once()
        return summary

    def _calculate_tss(self, activity: Activity, activity_id: str) -> bool:
        try:
            from ..training_stress_service import TrainingStressService

            tss_service = TrainingStressService(self.sync_service.db)
            tss = tss_service.calculate_tss_for_activity(activity)
            if tss is None:
                return False
            activity.training_stress_score = tss
            logger.info(
                "✅ Oppdatert TSS for aktivitet %s: %s (EPOC=%s)",
                activity_id,
                tss,
                activity.epoc,
            )
            return True
        except Exception as exc:
            logger.warning(f"Feil ved TSS-oppdatering for aktivitet {activity_id}: {exc}")
            return False

    def calculate_metrics_for_new_activity(
        self,
        activity_id: str,
        *,
        skip_snapshot_recalc: bool = False,
    ) -> dict:
        results = {
            "activity_id": activity_id,
            "tss_calculated": False,
            "power_calculated": False,
            "running_economy_calculated": False,
            "negative_split_calculated": False,
            "decoupling_calculated": False,
            "grade_adjusted_speed_calculated": False,
            "efficiency_calculated": False,
            "fatigue_resistance_calculated": False,
            "performance_snapshots_updated": False,
            "hrv_calculated": False,
            "data_validated": False,
            "validation_fixes": [],
            "errors": [],
            "skip_reasons": [],
        }
        try:
            activity_id_int = int(activity_id)
            activity = self.sync_service.db.query(Activity).filter_by(activity_id=activity_id).first()
            if not activity:
                results["errors"].append("Aktivitet ikke funnet i database")
                return results

            validation = validate_and_repair_activity(
                activity,
                storage=self.sync_service.storage,
            )
            if validation.changed:
                results["data_validated"] = True
                results["validation_fixes"] = validation.fixes
                if validation.warnings:
                    results["validation_warnings"] = validation.warnings

            if tss_needs_refresh(activity):
                if self._calculate_tss(activity, activity_id):
                    results["tss_calculated"] = True

            if _is_derived_running_activity(activity):
                if activity.average_power is None:
                    try:
                        from ..power_service import PowerService

                        power_service = PowerService(self.sync_service.storage)
                        # Ikke commit her – calculate_metrics_for_new_activity committer atomisk til slutt.
                        power_data = power_service.calculate_activity_power(
                            activity_id_int, self.sync_service.db, commit=False
                        )
                        if power_data:
                            results["power_calculated"] = True
                            logger.debug(
                                "Beregnet power for aktivitet %s: %sW",
                                activity_id,
                                power_data.get("average_power_watts"),
                            )
                    except Exception as exc:
                        logger.warning(f"Feil ved beregning av power for aktivitet {activity_id}: {exc}")
                        results["errors"].append(f"Power feil: {str(exc)}")

            if _is_derived_running_activity(activity):
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
                            logger.debug(
                                "Beregnet løpsøkonomi for aktivitet %s: %s",
                                activity_id,
                                running_economy,
                            )
                    except Exception as exc:
                        logger.warning(f"Feil ved beregning av løpsøkonomi for aktivitet {activity_id}: {exc}")
                        results["errors"].append(f"Running economy feil: {str(exc)}")

            if _is_derived_running_activity(activity) and activity.negative_split_percent is None:
                try:
                    negative_split_result = self.sync_service.analysis_service.calculate_negative_split(
                        activity_id_int,
                        self.sync_service.db,
                        persist=False,
                    )
                    if negative_split_result and "negative_split_percent" in negative_split_result:
                        results["negative_split_calculated"] = True
                        logger.debug(
                            "Beregnet negative split for aktivitet %s: %s%%",
                            activity_id,
                            negative_split_result.get("negative_split_percent"),
                        )
                except Exception as exc:
                    from fastapi import HTTPException

                    if isinstance(exc, HTTPException):
                        results["skip_reasons"].append(f"negative_split:{exc.detail}")
                    logger.debug(f"Kunne ikke beregne negative split for aktivitet {activity_id}: {exc}")

            if _is_derived_running_activity(activity) and activity.avg_grade_adjusted_speed is None:
                try:
                    gap_result = self.sync_service.analysis_service.calculate_grade_adjusted_speed(
                        activity_id_int,
                        self.sync_service.db,
                        persist=False,
                    )
                    if gap_result and gap_result.get("avg_grade_adjusted_speed") is not None:
                        if gap_result.get("calculation_method") != "stored":
                            results["grade_adjusted_speed_calculated"] = True
                        logger.debug(
                            "Grade-adjusted speed for aktivitet %s: %s m/s (%s)",
                            activity_id,
                            gap_result.get("avg_grade_adjusted_speed"),
                            gap_result.get("calculation_method"),
                        )
                except Exception as exc:
                    logger.debug(
                        "Kunne ikke beregne grade-adjusted speed for aktivitet %s: %s",
                        activity_id,
                        exc,
                    )

            if _is_derived_running_activity(activity) and (
                activity.decoupling_percent is None
                or activity.avg_efficiency_factor is None
                or activity.decoupling_suitability_flag is None
            ):
                try:
                    efficiency_result = self.sync_service.analysis_service.calculate_efficiency_metrics(
                        activity_id_int,
                        self.sync_service.db,
                        persist=False,
                    )
                    if efficiency_result and "decoupling_percent" in efficiency_result:
                        results["decoupling_calculated"] = True
                        results["efficiency_calculated"] = True
                        logger.debug(
                            "Beregnet EF/decoupling for aktivitet %s: EF=%s decoupling=%s%%",
                            activity_id,
                            efficiency_result.get("avg_efficiency_factor"),
                            efficiency_result.get("decoupling_percent"),
                        )
                except Exception as exc:
                    from fastapi import HTTPException

                    if isinstance(exc, HTTPException):
                        results["skip_reasons"].append(f"decoupling:{exc.detail}")
                    logger.debug(f"Kunne ikke beregne EF/decoupling for aktivitet {activity_id}: {exc}")

            if _is_derived_running_activity(activity):
                try:
                    from ..performance_metrics_service import PerformanceMetricsService

                    performance_service = PerformanceMetricsService(
                        self.sync_service.db,
                        self.sync_service.storage,
                    )
                    # Ikke commit her – atomisk commit skjer til slutt i denne metoden.
                    fatigue = performance_service.calculate_fatigue_resistance_for_activity(
                        activity, commit=False
                    )
                    if fatigue:
                        results["fatigue_resistance_calculated"] = True
                        logger.debug(
                            "Beregnet fatigue resistance for aktivitet %s: %s",
                            activity_id,
                            fatigue.get("fatigue_resistance_score"),
                        )
                    if skip_snapshot_recalc or self._defer_snapshot_recalc:
                        self._snapshot_recalc_pending = True
                        results["performance_snapshots_updated"] = False
                    else:
                        performance_service.recalculate_performance_snapshots(commit=False)
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
            try:
                self.sync_service.db.rollback()
            except Exception:
                pass
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
