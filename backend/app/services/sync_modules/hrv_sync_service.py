from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
import asyncio
import logging

from ...database.models.health_data_missing import HealthDataMissing
from ...database.models.sync_state import SyncState
from ...database.models.sleep import HRV
from ...services.hrv_fetch import get_local_hrv_payload, resolve_hrv_for_date, upsert_hrv_to_db

logger = logging.getLogger(__name__)


class HRVSyncService:
    def __init__(self, sync_service: Any):
        self.sync_service = sync_service

    def normalize_hrv_data(self, hrv_data: dict, calendar_date: str) -> Optional[dict]:
        if not hrv_data or "hrv_summary" not in hrv_data:
            logger.debug("HRV-data mangler hrv_summary for %s", calendar_date)
            return None
        summary = hrv_data["hrv_summary"]
        if summary is None:
            logger.debug("hrv_summary er None for %s", calendar_date)
            return None
        last_night_avg = summary.get("last_night_avg") if summary else None
        if not last_night_avg:
            logger.debug("Ingen last_night_avg for %s, hopper over", calendar_date)
            return None
        return {
            "date": calendar_date,
            "last_night_avg": last_night_avg,
            "last_night_5_min_high": summary.get("last_night_5_min_high") if summary else None,
            "baseline_low_upper": summary.get("baseline_low_upper") if summary else None,
            "baseline_balanced_lower": summary.get("baseline_balanced_lower") if summary else None,
            "baseline_balanced_upper": summary.get("baseline_balanced_upper") if summary else None,
            "status": summary.get("status") if summary else None,
        }

    def _mark_hrv_missing(
        self,
        missing_day: date,
        hrv_missing_dates: set[date],
        pending_missing_dates: set[date],
    ) -> None:
        if missing_day in hrv_missing_dates or missing_day in pending_missing_dates:
            return
        try:
            self.sync_service.db.add(
                HealthDataMissing(data_type="hrv", missing_date=missing_day)
            )
            pending_missing_dates.add(missing_day)
            hrv_missing_dates.add(missing_day)
        except Exception as add_exc:
            logger.debug(f"Kunne ikke lagre HRV manglende dato {missing_day}: {add_exc}")

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

        existing_dates: set[date] = set()
        try:
            hrv_df = self.sync_service.storage.get_hrv_data()
            if hrv_df is not None and not hrv_df.empty:
                start_filter = datetime.combine(start_date.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
                end_filter = datetime.combine(end_date.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
                filtered_hrv_df = hrv_df[(hrv_df.index >= start_filter) & (hrv_df.index <= end_filter)]
                existing_dates.update(filtered_hrv_df.index.to_series().dt.date)
        except Exception as exc:
            logger.warning(f"Kunne ikke lese eksisterende HRV-datoer fra parquet: {exc}")

        try:
            db_dates = {
                row.measurement_date
                for row in self.sync_service.db.query(HRV.measurement_date)
                .filter(
                    HRV.measurement_date >= hrv_start_date.date(),
                    HRV.measurement_date <= end_date.date(),
                    HRV.rmssd.isnot(None),
                )
                .all()
            }
            existing_dates.update(db_dates)
        except Exception as exc:
            logger.warning(f"Kunne ikke lese eksisterende HRV-datoer fra database: {exc}")

        logger.info(
            "Fant %s eksisterende HRV-datoer innenfor perioden (parquet + database).",
            len(existing_dates),
        )

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
        last_synced_candidate = hrv_start_date.date() - timedelta(days=1)
        sync_state_blocked = False

        current_date = hrv_start_date
        while current_date <= end_date:
            processed_successfully = False
            date_str = current_date.strftime("%Y-%m-%d")
            is_recent = current_date >= recent_cutoff
            should_skip = current_date.date() in existing_dates and not (force_refresh_recent and is_recent)
            if should_skip:
                logger.debug(f"Hopper over HRV-data for {date_str} (finnes allerede).")
                local_payload, _local_source = get_local_hrv_payload(
                    current_date.date(),
                    db=self.sync_service.db,
                    storage=self.sync_service.storage,
                )
                if local_payload and _local_source == "local_parquet":
                    upsert_hrv_to_db(
                        self.sync_service.db,
                        current_date.date(),
                        local_payload,
                    )
                processed_successfully = True
                if not sync_state_blocked:
                    last_synced_candidate = current_date.date()
                current_date += timedelta(days=1)
                continue
            if current_date.date() in hrv_missing_dates:
                logger.debug(f"Hopper over HRV-data for {date_str} (ingen data sist gang).")
                processed_successfully = True
                if not sync_state_blocked:
                    last_synced_candidate = current_date.date()
                current_date += timedelta(days=1)
                continue
            elif current_date.date() in existing_dates and force_refresh_recent and is_recent:
                logger.debug(f"Oppdaterer eksisterende HRV-data for {date_str} (force_refresh_recent=True).")
            try:
                resolved = await resolve_hrv_for_date(
                    self.sync_service.garmin_client,
                    current_date.date(),
                    db=self.sync_service.db,
                    storage=self.sync_service.storage,
                )
                if resolved.available and resolved.data:
                    if resolved.source == "garmin_live":
                        normalized_hrv = self.normalize_hrv_data(resolved.data, date_str)
                        if normalized_hrv:
                            all_hrv_data.append(normalized_hrv)
                            upsert_hrv_to_db(
                                self.sync_service.db,
                                current_date.date(),
                                resolved.data,
                            )
                            existing_dates.add(current_date.date())
                        elif get_local_hrv_payload(current_date.date(), db=self.sync_service.db, storage=self.sync_service.storage)[0]:
                            logger.debug(
                                "Live Garmin HRV for %s var ugyldig, men lokal HRV finnes — markeres ikke som manglende.",
                                date_str,
                            )
                            existing_dates.add(current_date.date())
                        else:
                            self._mark_hrv_missing(
                                current_date.date(),
                                hrv_missing_dates,
                                pending_missing_dates,
                            )
                    else:
                        logger.debug(
                            "Bruker lokal HRV for %s (%s) etter live_status=%s.",
                            date_str,
                            resolved.source,
                            resolved.live_status,
                        )
                        if resolved.source == "local_parquet":
                            upsert_hrv_to_db(
                                self.sync_service.db,
                                current_date.date(),
                                resolved.data,
                            )
                        existing_dates.add(current_date.date())
                else:
                    local_payload, _local_source = get_local_hrv_payload(
                        current_date.date(),
                        db=self.sync_service.db,
                        storage=self.sync_service.storage,
                    )
                    if local_payload:
                        logger.debug(
                            "Live Garmin mangler HRV for %s, men lokal kopi finnes — markeres ikke som manglende.",
                            date_str,
                        )
                        existing_dates.add(current_date.date())
                    else:
                        self._mark_hrv_missing(
                            current_date.date(),
                            hrv_missing_dates,
                            pending_missing_dates,
                        )
                processed_successfully = True
                await asyncio.sleep(1)
            except Exception as exc:
                logger.error(f"Feil under henting av HRV-data for {date_str}: {exc}")
                if not sync_state_blocked:
                    sync_state_blocked = True
            else:
                if not sync_state_blocked and processed_successfully:
                    last_synced_candidate = current_date.date()
            current_date += timedelta(days=1)

        if all_hrv_data:
            logger.info(f"Fant {len(all_hrv_data)} nye dager med HRV-data. Lagrer...")
            self.sync_service.storage.save_hrv_data(all_hrv_data)
        else:
            logger.info("Ingen nye HRV-data å lagre.")

        if last_synced_candidate >= hrv_start_date.date():
            if "hrv_state" not in locals():
                hrv_state = self.sync_service.db.query(SyncState).filter_by(key="hrv").first()
            if not hrv_state:
                hrv_state = SyncState(key="hrv")
                self.sync_service.db.add(hrv_state)
            if hrv_state.last_synced_date != last_synced_candidate:
                hrv_state.last_synced_date = last_synced_candidate
                hrv_state.last_synced_at = datetime.now(timezone.utc)

        if all_hrv_data or pending_missing_dates or last_synced_candidate >= hrv_start_date.date():
            try:
                self.sync_service.db.commit()
                logger.info(
                    "HRV-synk ferdig: lagret %s dager, markerte %s manglende, last_synced_date=%s",
                    len(all_hrv_data),
                    len(pending_missing_dates),
                    last_synced_candidate if last_synced_candidate >= hrv_start_date.date() else None,
                )
            except Exception as exc:
                self.sync_service.db.rollback()
                logger.warning(f"Kunne ikke committe HRV-synk: {exc}")
