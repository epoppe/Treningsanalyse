from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
import asyncio
import logging

from ...database.models import Stress
from ...database.models.health_data_missing import HealthDataMissing
from ...services.health_data_missing_helpers import (
    clear_health_data_missing,
    should_retry_health_data_missing,
)
from ...database.models.sync_state import SyncState

logger = logging.getLogger(__name__)


class StressSyncService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    async def sync_stress_data(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
    ):
        stress_state = self.sync_service.db.query(SyncState).filter_by(key="stress").first()
        stress_start_date = max(start_date, datetime(2020, 1, 1, tzinfo=timezone.utc))
        if stress_state and stress_state.last_synced_date and not force_refresh_recent:
            stress_start_date = max(
                stress_start_date,
                datetime.combine(stress_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc)
                + timedelta(days=1),
            )

        existing_stress_dates = {
            s.stress_date
            for s in self.sync_service.db.query(Stress.stress_date)
            .filter(Stress.stress_date >= stress_start_date.date(), Stress.stress_date <= end_date.date())
            .all()
        }
        stress_missing_dates = {
            r.missing_date
            for r in self.sync_service.db.query(HealthDataMissing.missing_date)
            .filter(
                HealthDataMissing.data_type == "stress",
                HealthDataMissing.missing_date >= stress_start_date.date(),
                HealthDataMissing.missing_date <= end_date.date(),
            )
            .all()
        }
        pending_missing_dates: set[date] = set()
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)

        missing_count = max(
            0, (end_date - stress_start_date).days + 1 - len(existing_stress_dates) - len(stress_missing_dates)
        )
        logger.info(
            f"Starter stress-synk: {stress_start_date.date()} -> {end_date.date()} (mangler {missing_count} dager)"
        )

        current_date = stress_start_date
        saved = 0
        while current_date <= end_date:
            is_recent = current_date >= recent_cutoff
            if current_date.date() in existing_stress_dates and not (force_refresh_recent and is_recent):
                current_date += timedelta(days=1)
                continue
            if current_date.date() in stress_missing_dates:
                if not should_retry_health_data_missing(is_recent, force_refresh_recent):
                    current_date += timedelta(days=1)
                    continue
                logger.debug(
                    "Prøver stress på nytt for %s (force_refresh_recent=True).",
                    current_date.date(),
                )
            try:
                stress_data = await self.sync_service.garmin_client.get_stress_data(current_date)
                if stress_data and (stress_data.get("stress_time") or stress_data.get("rest_time")):
                    def to_sec(minutes):
                        if minutes is None:
                            return None
                        return float(minutes) * 60.0

                    row = (
                        self.sync_service.db.query(Stress)
                        .filter_by(stress_date=current_date.date())
                        .first()
                    )
                    if not row:
                        row = Stress(
                            stress_date=current_date.date(),
                            created_at=datetime.now(timezone.utc),
                        )
                        self.sync_service.db.add(row)

                    row.stress_level = stress_data.get("stress_level")
                    row.total_time = to_sec(stress_data.get("total_time"))
                    row.stress_time = to_sec(stress_data.get("stress_time"))
                    row.rest_time = to_sec(stress_data.get("rest_time"))
                    row.low_stress_time = to_sec(stress_data.get("low_stress_time"))
                    row.medium_stress_time = to_sec(stress_data.get("medium_stress_time"))
                    row.high_stress_time = to_sec(stress_data.get("high_stress_time"))
                    row.updated_at = datetime.now(timezone.utc)
                    existing_stress_dates.add(current_date.date())
                    clear_health_data_missing(self.sync_service.db, "stress", current_date.date())
                    stress_missing_dates.discard(current_date.date())
                    pending_missing_dates.discard(current_date.date())
                    saved += 1
                else:
                    try:
                        if current_date.date() not in stress_missing_dates and current_date.date() not in pending_missing_dates:
                            self.sync_service.db.add(
                                HealthDataMissing(data_type="stress", missing_date=current_date.date())
                            )
                            pending_missing_dates.add(current_date.date())
                        stress_missing_dates.add(current_date.date())
                    except Exception as add_exc:
                        logger.debug(f"Kunne ikke lagre stress manglende dato {current_date.date()}: {add_exc}")
                await asyncio.sleep(0.3)
            except Exception as exc:
                logger.debug(f"Stress-dag feilet {current_date.date()}: {exc}")
            current_date += timedelta(days=1)

        if saved > 0:
            self.sync_service.db.commit()
            if not stress_state:
                stress_state = SyncState(key="stress")
                self.sync_service.db.add(stress_state)
            stress_state.last_synced_date = end_date.date()
            stress_state.last_synced_at = datetime.now(timezone.utc)
            self.sync_service.db.commit()
            logger.info(f"Stress-synk lagret {saved} dager")

        if pending_missing_dates:
            try:
                self.sync_service.db.commit()
            except Exception as exc:
                self.sync_service.db.rollback()
                logger.warning(f"Kunne ikke committe manglende stress-datoer: {exc}")
