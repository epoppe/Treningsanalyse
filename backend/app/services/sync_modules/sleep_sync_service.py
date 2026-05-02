from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import logging

from sqlalchemy.sql import func

from ...database.models.health_data_missing import HealthDataMissing
from ...database.models.sleep import Sleep
from ...database.models.sync_state import SyncState

logger = logging.getLogger(__name__)


class SleepSyncService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    async def sync_sleep_data(self, start_date: datetime, end_date: datetime):
        sleep_state = self.sync_service.db.query(SyncState).filter_by(key="sleep").first()
        sleep_start_date = start_date
        if sleep_state and sleep_state.last_synced_date:
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

        logger.info(f"Starter søvn-synk: {sleep_start_date.date()} -> {end_date.date()}")
        current_date = sleep_start_date
        saved = 0
        while current_date <= end_date:
            if current_date.date() in existing_sleep_dates or current_date.date() in sleep_missing_dates:
                current_date += timedelta(days=1)
                continue
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

                    def to_sec(minutes):
                        if minutes is None:
                            return None
                        return float(minutes) * 60.0

                    row.total_sleep_time = to_sec(data.get("sleep_time")) or to_sec(data.get("total_sleep"))
                    row.deep_sleep_time = to_sec(data.get("deep_sleep"))
                    row.light_sleep_time = to_sec(data.get("light_sleep"))
                    row.rem_sleep_time = to_sec(data.get("rem_sleep"))
                    row.awake_time = to_sec(data.get("awake_time"))
                    row.sleep_score = data.get("sleep_score")
                    row.updated_at = func.now()
                    saved += 1
                else:
                    try:
                        existing = self.sync_service.db.query(HealthDataMissing).filter_by(
                            data_type="sleep", missing_date=current_date.date()
                        ).first()
                        if not existing:
                            self.sync_service.db.add(
                                HealthDataMissing(data_type="sleep", missing_date=current_date.date())
                            )
                            self.sync_service.db.commit()
                        sleep_missing_dates.add(current_date.date())
                    except Exception as add_exc:
                        logger.debug(f"Kunne ikke lagre søvn manglende dato {current_date.date()}: {add_exc}")
            except Exception as exc:
                logger.debug(f"Søvn-dag feilet {current_date.date()}: {exc}")
            current_date += timedelta(days=1)

        if saved > 0:
            self.sync_service.db.commit()
            if not sleep_state:
                sleep_state = SyncState(key="sleep")
                self.sync_service.db.add(sleep_state)
            sleep_state.last_synced_date = end_date.date()
            sleep_state.last_synced_at = datetime.utcnow()
            self.sync_service.db.commit()
            logger.info(f"Søvn-synk lagret {saved} dager")

