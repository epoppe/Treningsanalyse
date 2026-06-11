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
from ...database.models.sleep import Sleep
from ...database.models.sync_state import SyncState
from ..sleep_data_mapping import apply_sleep_data_to_row

logger = logging.getLogger(__name__)


class SleepSyncService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    async def sync_sleep_data(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
    ):
        sleep_state = self.sync_service.db.query(SyncState).filter_by(key="sleep").first()
        sleep_start_date = start_date
        if sleep_state and sleep_state.last_synced_date and not force_refresh_recent:
            sleep_start_date = max(
                sleep_start_date,
                datetime.combine(sleep_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc)
                + timedelta(days=1),
            )

        existing_sleep_dates = {
            s.sleep_date
            for s in self.sync_service.db.query(Sleep.sleep_date)
            .filter(Sleep.sleep_date >= sleep_start_date.date(), Sleep.sleep_date <= end_date.date())
            .all()
        }
        sleep_missing_dates = {
            r.missing_date
            for r in self.sync_service.db.query(HealthDataMissing.missing_date)
            .filter(
                HealthDataMissing.data_type == "sleep",
                HealthDataMissing.missing_date >= sleep_start_date.date(),
                HealthDataMissing.missing_date <= end_date.date(),
            )
            .all()
        }
        pending_missing_dates: set[date] = set()
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        last_synced_candidate = sleep_start_date.date() - timedelta(days=1)
        sync_state_blocked = False

        logger.info(f"Starter søvn-synk: {sleep_start_date.date()} -> {end_date.date()}")
        current_date = sleep_start_date
        saved = 0
        while current_date <= end_date:
            processed_successfully = False
            is_recent = current_date >= recent_cutoff
            should_skip = current_date.date() in existing_sleep_dates and not (force_refresh_recent and is_recent)
            if should_skip:
                processed_successfully = True
                if not sync_state_blocked:
                    last_synced_candidate = current_date.date()
                current_date += timedelta(days=1)
                continue
            if current_date.date() in sleep_missing_dates:
                if not should_retry_health_data_missing(is_recent, force_refresh_recent):
                    processed_successfully = True
                    if not sync_state_blocked:
                        last_synced_candidate = current_date.date()
                    current_date += timedelta(days=1)
                    continue
                logger.debug(
                    "Prøver søvn på nytt for %s (force_refresh_recent=True).",
                    current_date.date(),
                )
            try:
                data = await self.sync_service.garmin_client.get_sleep_data(current_date)
                if data and any(
                    data.get(k) for k in ["sleep_time", "total_sleep", "deep_sleep", "light_sleep", "rem_sleep", "sleep_score"]
                ):
                    sleep_date = current_date.date()
                    row = self.sync_service.db.query(Sleep).filter_by(sleep_date=sleep_date).first()
                    if not row:
                        row = Sleep(sleep_date=sleep_date, created_at=func.now(), updated_at=func.now())
                        self.sync_service.db.add(row)
                    apply_sleep_data_to_row(row, data)
                    row.updated_at = func.now()
                    existing_sleep_dates.add(sleep_date)
                    clear_health_data_missing(self.sync_service.db, "sleep", sleep_date)
                    sleep_missing_dates.discard(sleep_date)
                    pending_missing_dates.discard(sleep_date)
                    saved += 1
                else:
                    try:
                        if current_date.date() not in sleep_missing_dates and current_date.date() not in pending_missing_dates:
                            self.sync_service.db.add(
                                HealthDataMissing(data_type="sleep", missing_date=current_date.date())
                            )
                            pending_missing_dates.add(current_date.date())
                        sleep_missing_dates.add(current_date.date())
                    except Exception as add_exc:
                        logger.debug(f"Kunne ikke lagre søvn manglende dato {current_date.date()}: {add_exc}")
                processed_successfully = True
            except Exception as exc:
                logger.debug(f"Søvn-dag feilet {current_date.date()}: {exc}")
                if not sync_state_blocked:
                    sync_state_blocked = True
            else:
                if not sync_state_blocked and processed_successfully:
                    last_synced_candidate = current_date.date()
            current_date += timedelta(days=1)

        if last_synced_candidate >= sleep_start_date.date():
            if not sleep_state:
                sleep_state = SyncState(key="sleep")
                self.sync_service.db.add(sleep_state)
            if sleep_state.last_synced_date != last_synced_candidate:
                sleep_state.last_synced_date = last_synced_candidate
                sleep_state.last_synced_at = datetime.now(timezone.utc)

        if saved > 0 or pending_missing_dates or last_synced_candidate >= sleep_start_date.date():
            try:
                self.sync_service.db.commit()
                logger.info(
                    "Søvn-synk ferdig: lagret %s dager, markerte %s manglende, last_synced_date=%s",
                    saved,
                    len(pending_missing_dates),
                    last_synced_candidate if last_synced_candidate >= sleep_start_date.date() else None,
                )
            except Exception as exc:
                self.sync_service.db.rollback()
                logger.warning(f"Kunne ikke committe søvn-synk: {exc}")
