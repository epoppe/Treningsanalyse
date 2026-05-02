from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import asyncio
import logging

from ...database.models import Stress
from ...database.models.health_data_missing import HealthDataMissing
from ...database.models.sync_state import SyncState

logger = logging.getLogger(__name__)


class StressSyncService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    async def sync_stress_data(self, start_date: datetime, end_date: datetime):
        stress_state = self.sync_service.db.query(SyncState).filter_by(key="stress").first()
        stress_start_date = max(start_date, datetime(2020, 1, 1, tzinfo=timezone.utc))
        if stress_state and stress_state.last_synced_date:
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

        missing_count = max(
            0, (end_date - stress_start_date).days + 1 - len(existing_stress_dates) - len(stress_missing_dates)
        )
        logger.info(
            f"Starter stress-synk: {stress_start_date.date()} -> {end_date.date()} (mangler {missing_count} dager)"
        )

        current_date = stress_start_date
        saved = 0
        while current_date <= end_date:
            if current_date.date() in existing_stress_dates or current_date.date() in stress_missing_dates:
                current_date += timedelta(days=1)
                continue
            try:
                stress_data = await self.sync_service.garmin_client.get_stress_data(current_date)
                if stress_data and (stress_data.get("stress_time") or stress_data.get("rest_time")):
                    def to_sec(minutes):
                        if minutes is None:
                            return None
                        return float(minutes) * 60.0

                    row = Stress(
                        stress_date=current_date.date(),
                        stress_level=stress_data.get("stress_level"),
                        total_time=to_sec(stress_data.get("total_time")),
                        stress_time=to_sec(stress_data.get("stress_time")),
                        rest_time=to_sec(stress_data.get("rest_time")),
                        low_stress_time=to_sec(stress_data.get("low_stress_time")),
                        medium_stress_time=to_sec(stress_data.get("medium_stress_time")),
                        high_stress_time=to_sec(stress_data.get("high_stress_time")),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    self.sync_service.db.add(row)
                    saved += 1
                else:
                    try:
                        existing = self.sync_service.db.query(HealthDataMissing).filter_by(
                            data_type="stress", missing_date=current_date.date()
                        ).first()
                        if not existing:
                            self.sync_service.db.add(
                                HealthDataMissing(data_type="stress", missing_date=current_date.date())
                            )
                            self.sync_service.db.commit()
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
            stress_state.last_synced_at = datetime.utcnow()
            self.sync_service.db.commit()
            logger.info(f"Stress-synk lagret {saved} dager")

