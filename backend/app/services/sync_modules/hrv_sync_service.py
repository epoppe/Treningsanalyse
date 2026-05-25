from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
import asyncio
import logging

from ...database.models.health_data_missing import HealthDataMissing
from ...database.models.sync_state import SyncState

logger = logging.getLogger(__name__)


class HRVSyncService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    def normalize_hrv_data(self, hrv_data: dict, calendar_date: str) -> Optional[dict]:
        if not hrv_data or "hrv_summary" not in hrv_data:
            logger.warning(f"HRV-data mangler eller har ingen 'hrv_summary' for {calendar_date}: {hrv_data}")
            return None
        summary = hrv_data["hrv_summary"]
        if summary is None:
            logger.warning(f"hrv_summary er None for {calendar_date}")
            return None
        weekly_avg = summary.get("weekly_avg", 0) if summary else 0
        last_night_avg = summary.get("last_night_avg") if summary else None
        if not last_night_avg:
            logger.info(f"Ingen last_night_avg verdi for {calendar_date}, hopper over")
            return None
        return {
            "date": calendar_date,
            "last_night_avg": last_night_avg,
            "last_night_5_min_high": summary.get("last_night_5_min_high", 0) if summary else 0,
            "baseline_low_upper": summary.get("baseline_low_upper", weekly_avg * 0.8 if weekly_avg else 0)
            if summary
            else 0,
            "baseline_balanced_lower": summary.get("baseline_balanced_lower", weekly_avg * 0.9 if weekly_avg else 0)
            if summary
            else 0,
            "baseline_balanced_upper": summary.get("baseline_balanced_upper", weekly_avg * 1.1 if weekly_avg else 0)
            if summary
            else 0,
            "status": summary.get("status") if summary else None,
        }

    async def sync_hrv_data(self, start_date: datetime, end_date: datetime, force_refresh_recent: bool = False):
        hrv_start_date = max(start_date, datetime(2023, 1, 1, tzinfo=timezone.utc))
        if hrv_start_date > end_date:
            logger.info(
                f"HRV-synkronisering hoppes over - perioden {start_date.date()} til {end_date.date()} er før 2023"
            )
            return

        logger.info(f"Starter HRV-synkronisering fra {hrv_start_date.date()} til {end_date.date()} (HRV fra 2023)")
        all_hrv_data = []
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)

        try:
            hrv_df = self.sync_service.storage.get_hrv_data()
            if hrv_df is not None and not hrv_df.empty:
                start_filter = datetime.combine(start_date.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
                end_filter = datetime.combine(end_date.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
                filtered_hrv_df = hrv_df[(hrv_df.index >= start_filter) & (hrv_df.index <= end_filter)]
                existing_dates = set(filtered_hrv_df.index.to_series().dt.date)
                logger.info(f"Fant {len(existing_dates)} eksisterende HRV-datoer innenfor det ønskede tidsrommet.")
            else:
                existing_dates = set()
                logger.info("Ingen eksisterende HRV-data funnet.")
        except Exception as exc:
            logger.warning(f"Kunne ikke lese eksisterende HRV-datoer, fortsetter uten duplikatsjekk. Feil: {exc}")
            existing_dates = set()

        try:
            hrv_state = self.sync_service.db.query(SyncState).filter_by(key="hrv").first()
            if hrv_state and hrv_state.last_synced_date:
                hrv_start_effective = datetime.combine(hrv_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc)
                if not force_refresh_recent:
                    hrv_start_date = max(hrv_start_date, hrv_start_effective + timedelta(days=1))
        except Exception:
            pass

        hrv_missing_dates = {
            r.missing_date
            for r in self.sync_service.db.query(HealthDataMissing.missing_date)
            .filter(
                HealthDataMissing.data_type == "hrv",
                HealthDataMissing.missing_date >= hrv_start_date.date(),
                HealthDataMissing.missing_date <= end_date.date(),
            )
            .all()
        }
        pending_missing_dates: set[date] = set()

        current_date = hrv_start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            is_recent = current_date >= recent_cutoff
            should_skip = current_date.date() in existing_dates and not (force_refresh_recent and is_recent)
            if should_skip:
                logger.info(f"Hopper over HRV-data for {date_str} (finnes allerede).")
                current_date += timedelta(days=1)
                continue
            if current_date.date() in hrv_missing_dates:
                logger.info(f"Hopper over HRV-data for {date_str} (ingen data sist gang).")
                current_date += timedelta(days=1)
                continue
            elif current_date.date() in existing_dates and force_refresh_recent and is_recent:
                logger.info(f"Oppdaterer eksisterende HRV-data for {date_str} (force_refresh_recent=True).")
            try:
                hrv_data = await self.sync_service.garmin_client.get_hrv_data_alternative(current_date)
                if hrv_data:
                    normalized_hrv = self.normalize_hrv_data(hrv_data, date_str)
                    if normalized_hrv:
                        all_hrv_data.append(normalized_hrv)
                else:
                    try:
                        if current_date.date() not in hrv_missing_dates and current_date.date() not in pending_missing_dates:
                            self.sync_service.db.add(
                                HealthDataMissing(data_type="hrv", missing_date=current_date.date())
                            )
                            pending_missing_dates.add(current_date.date())
                        hrv_missing_dates.add(current_date.date())
                    except Exception as add_exc:
                        logger.debug(f"Kunne ikke lagre HRV manglende dato {date_str}: {add_exc}")
                await asyncio.sleep(1)
            except Exception as exc:
                logger.error(f"Feil under henting av HRV-data for {date_str}: {exc}")
            current_date += timedelta(days=1)

        if all_hrv_data:
            logger.info(f"Fant {len(all_hrv_data)} nye dager med HRV-data. Lagrer...")
            self.sync_service.storage.save_hrv_data(all_hrv_data)
            try:
                last_date = max(datetime.strptime(d["date"], "%Y-%m-%d").date() for d in all_hrv_data)
                if "hrv_state" not in locals():
                    hrv_state = self.sync_service.db.query(SyncState).filter_by(key="hrv").first()
                if not hrv_state:
                    hrv_state = SyncState(key="hrv")
                    self.sync_service.db.add(hrv_state)
                hrv_state.last_synced_date = last_date
                hrv_state.last_synced_at = datetime.now(timezone.utc)
                self.sync_service.db.commit()
            except Exception as exc:
                logger.warning(f"Kunne ikke oppdatere HRV sync state: {exc}")
        else:
            logger.info("Ingen nye HRV-data å lagre.")

        if pending_missing_dates:
            try:
                self.sync_service.db.commit()
            except Exception as exc:
                self.sync_service.db.rollback()
                logger.warning(f"Kunne ikke committe manglende HRV-datoer: {exc}")
