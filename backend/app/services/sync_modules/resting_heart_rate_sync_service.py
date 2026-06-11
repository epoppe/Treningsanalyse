from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
import logging

from sqlalchemy.sql import func

from ...database.models.health_data_missing import HealthDataMissing
from ...services.health_data_missing_helpers import (
    clear_health_data_missing,
    should_retry_health_data_missing,
)
from ...database.models.sleep import RestingHeartRate
from ...database.models.sync_state import SyncState

logger = logging.getLogger(__name__)


class RestingHeartRateSyncService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    async def sync_resting_heart_rate_data(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
    ) -> None:
        rhr_state = self.sync_service.db.query(SyncState).filter_by(key="resting_heart_rate").first()
        rhr_start_date = start_date
        if rhr_state and rhr_state.last_synced_date and not force_refresh_recent:
            rhr_start_date = max(
                rhr_start_date,
                datetime.combine(rhr_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc)
                + timedelta(days=1),
            )

        existing_rhr_dates = {
            row.measurement_date
            for row in self.sync_service.db.query(RestingHeartRate.measurement_date)
            .filter(
                RestingHeartRate.measurement_date >= rhr_start_date.date(),
                RestingHeartRate.measurement_date <= end_date.date(),
            )
            .all()
        }
        rhr_missing_dates = {
            row.missing_date
            for row in self.sync_service.db.query(HealthDataMissing.missing_date)
            .filter(
                HealthDataMissing.data_type == "resting_heart_rate",
                HealthDataMissing.missing_date >= rhr_start_date.date(),
                HealthDataMissing.missing_date <= end_date.date(),
            )
            .all()
        }
        pending_missing_dates: set[date] = set()
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        last_synced_candidate = rhr_start_date.date() - timedelta(days=1)
        sync_state_blocked = False

        if rhr_start_date.date() > end_date.date():
            logger.info(
                "Hvilepuls-synk hoppes over: start %s er etter slutt %s (sync state er à jour)",
                rhr_start_date.date(),
                end_date.date(),
            )
            return

        logger.info(f"Starter hvilepuls-synk: {rhr_start_date.date()} -> {end_date.date()}")
        current_date = rhr_start_date
        saved = 0
        while current_date <= end_date:
            processed_successfully = False
            is_recent = current_date >= recent_cutoff
            should_skip = current_date.date() in existing_rhr_dates and not (force_refresh_recent and is_recent)
            if should_skip:
                processed_successfully = True
                if not sync_state_blocked:
                    last_synced_candidate = current_date.date()
                current_date += timedelta(days=1)
                continue
            if current_date.date() in rhr_missing_dates:
                if not should_retry_health_data_missing(is_recent, force_refresh_recent):
                    processed_successfully = True
                    if not sync_state_blocked:
                        last_synced_candidate = current_date.date()
                    current_date += timedelta(days=1)
                    continue
                logger.debug(
                    "Prøver hvilepuls på nytt for %s (force_refresh_recent=True).",
                    current_date.date(),
                )
            try:
                data = await self.sync_service.garmin_client.get_resting_heart_rate_data(current_date)
                if data and data.get("resting_heart_rate") is not None:
                    measurement_date = current_date.date()
                    row = self.sync_service.db.query(RestingHeartRate).filter_by(measurement_date=measurement_date).first()
                    if not row:
                        row = RestingHeartRate(
                            measurement_date=measurement_date,
                            created_at=func.now(),
                            updated_at=func.now(),
                        )
                        self.sync_service.db.add(row)

                    row.resting_heart_rate = float(data["resting_heart_rate"])
                    row.measurement_method = data.get("measurement_method") or "automatic"
                    row.updated_at = func.now()
                    existing_rhr_dates.add(measurement_date)
                    clear_health_data_missing(self.sync_service.db, "resting_heart_rate", measurement_date)
                    rhr_missing_dates.discard(measurement_date)
                    pending_missing_dates.discard(measurement_date)
                    saved += 1
                else:
                    try:
                        if current_date.date() not in rhr_missing_dates and current_date.date() not in pending_missing_dates:
                            self.sync_service.db.add(
                                HealthDataMissing(
                                    data_type="resting_heart_rate",
                                    missing_date=current_date.date(),
                                )
                            )
                            pending_missing_dates.add(current_date.date())
                        rhr_missing_dates.add(current_date.date())
                    except Exception as add_exc:
                        logger.debug(f"Kunne ikke lagre manglende hvilepulsdato {current_date.date()}: {add_exc}")
                processed_successfully = True
            except Exception as exc:
                logger.debug(f"Hvilepuls-dag feilet {current_date.date()}: {exc}")
                if not sync_state_blocked:
                    sync_state_blocked = True
            else:
                if not sync_state_blocked and processed_successfully:
                    last_synced_candidate = current_date.date()
            current_date += timedelta(days=1)

        if last_synced_candidate >= rhr_start_date.date():
            if not rhr_state:
                rhr_state = SyncState(key="resting_heart_rate")
                self.sync_service.db.add(rhr_state)
            if rhr_state.last_synced_date != last_synced_candidate:
                rhr_state.last_synced_date = last_synced_candidate
                rhr_state.last_synced_at = datetime.now(timezone.utc)

        if saved > 0 or pending_missing_dates or last_synced_candidate >= rhr_start_date.date():
            try:
                self.sync_service.db.commit()
                logger.info(
                    "Hvilepuls-synk ferdig: lagret %s dager, markerte %s manglende, last_synced_date=%s",
                    saved,
                    len(pending_missing_dates),
                    last_synced_candidate if last_synced_candidate >= rhr_start_date.date() else None,
                )
            except Exception as exc:
                self.sync_service.db.rollback()
                logger.warning(f"Kunne ikke committe hvilepuls-synk: {exc}")
