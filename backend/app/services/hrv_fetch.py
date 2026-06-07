"""HRV-henting fra Garmin med robust parsing og lokal fallback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, Literal, Optional

from sqlalchemy.orm import Session

from ..database.models import HRV
from ..storage import DataStorage

HrvLiveStatus = Literal[
    "ok",
    "not_found",
    "empty",
    "error",
    "not_authenticated",
    "not_attempted",
]
HrvSource = Literal["garmin_live", "local_db", "local_parquet", "none"]

LOCAL_DB_HRV_REASON = "HRV fra lokal database (synk fra Garmin eller parquet.)"
LOCAL_PARQUET_HRV_REASON = "HRV fra lokal parquet-fil."
NO_RMSSD_HRV_REASON = "HRV-rad uten rmssd i database."
GARMIN_LIVE_HRV_REASON = "HRV hentet live fra Garmin."
NO_HRV_REASON = "Ingen HRV tilgjengelig."
NO_HRV_ACTIVITY_DAY_REASON = "Ingen HRV registrert for aktivitetsdagen."
LIVE_FALLBACK_HRV_REASON = "Bruker lokalt lagret HRV fordi live Garmin ikke ga data."

HRV_SOURCE_REASONS: Dict[HrvSource, str] = {
    "garmin_live": GARMIN_LIVE_HRV_REASON,
    "local_db": LOCAL_DB_HRV_REASON,
    "local_parquet": LOCAL_PARQUET_HRV_REASON,
    "none": NO_HRV_REASON,
}


def hrv_contract_fields(
    *,
    source: HrvSource,
    live_status: HrvLiveStatus,
    available: bool,
    reason: Optional[str] = None,
) -> Dict[str, str]:
    """Felles kontrakt for source, live_status, availability og reason."""
    resolved_reason = reason if reason is not None else HRV_SOURCE_REASONS.get(source, "Ukjent HRV-kilde.")
    return {
        "source": source,
        "live_status": live_status,
        "availability": "supported" if available else "missing",
        "reason": resolved_reason,
    }


@dataclass(frozen=True)
class HrvLiveResult:
    data: Optional[Dict[str, Any]]
    live_status: HrvLiveStatus
    message: Optional[str] = None


@dataclass(frozen=True)
class HrvFetchResult:
    data: Optional[Dict[str, Any]]
    source: HrvSource
    live_status: HrvLiveStatus
    available: bool
    message: Optional[str] = None

    def to_reporting_dict(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            **hrv_contract_fields(
                source=self.source,
                live_status=self.live_status,
                available=self.available,
                reason=self.message,
            ),
            "available": self.available,
        }
        if target_date is not None:
            payload["date"] = target_date.isoformat()
        if self.data:
            summary = self.data.get("hrv_summary")
            if isinstance(summary, dict):
                payload.update(
                    {
                        "last_night_avg": summary.get("last_night_avg"),
                        "last_night_5_min_high": summary.get("last_night_5_min_high"),
                        "weekly_avg": summary.get("weekly_avg"),
                        "status": summary.get("status"),
                        "baseline_low_upper": summary.get("baseline_low_upper"),
                        "baseline_balanced_lower": summary.get("baseline_balanced_lower"),
                        "baseline_balanced_upper": summary.get("baseline_balanced_upper"),
                    }
                )
            else:
                payload.update(self.data)
        return payload


def is_garth_not_found(error: Exception) -> bool:
    text = str(error).lower()
    return "404" in str(error) or "not found" in text or "no data" in text


def normalize_garmin_hrv_raw(raw: Any, validate) -> Optional[Dict[str, Any]]:
    """Normaliserer ulike Garmin HRV-responser til validert {hrv_summary: ...}."""
    if raw is None:
        return None

    if isinstance(raw, list):
        if not raw:
            return None
        raw = raw[0]

    if not isinstance(raw, dict) or not raw:
        return None

    payload: Optional[Dict[str, Any]] = None

    if "hrv_summary" in raw:
        payload = {"hrv_summary": raw.get("hrv_summary")}
    elif "hrvSummary" in raw:
        payload = {"hrv_summary": raw.get("hrvSummary")}
    elif any(key in raw for key in ("last_night_avg", "weekly_avg")):
        payload = {"hrv_summary": raw}
    elif "allMetrics" in raw:
        hrv_metrics = (
            raw.get("allMetrics", {})
            .get("metricsMap", {})
            .get("WELLNESS_HRV_RMSSD", {})
        )
        if hrv_metrics and hrv_metrics.get("value"):
            payload = {
                "hrv_summary": {
                    "last_night_avg": hrv_metrics.get("value"),
                    "last_night_5_min_high": None,
                    "weekly_avg": None,
                    "status": None,
                    "baseline_low_upper": None,
                    "baseline_balanced_lower": None,
                    "baseline_balanced_upper": None,
                }
            }

    if not payload or payload.get("hrv_summary") is None:
        return None

    summary = payload["hrv_summary"]
    if not isinstance(summary, dict) or not summary.get("last_night_avg"):
        return None

    try:
        validated = validate(payload)
        return validated.model_dump()
    except Exception:
        return None


def upsert_hrv_to_db(
    db: Session,
    target_date: date,
    hrv_payload: Dict[str, Any],
) -> Optional[HRV]:
    """Lagrer eller oppdaterer HRV-rad fra Garmin-payload med hrv_summary."""
    summary = hrv_payload.get("hrv_summary") or {}
    last_night_avg = summary.get("last_night_avg")
    if not last_night_avg:
        return None

    measurement_time = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    existing = (
        db.query(HRV)
        .filter(HRV.measurement_date == target_date)
        .order_by(HRV.measurement_time.desc())
        .first()
    )

    if existing:
        existing.rmssd = last_night_avg
        existing.measurement_time = measurement_time
        existing.measurement_type = existing.measurement_type or "during_sleep"
        existing.baseline_balanced_lower = summary.get("baseline_balanced_lower")
        existing.baseline_balanced_upper = summary.get("baseline_balanced_upper")
        existing.baseline_low_upper = summary.get("baseline_low_upper")
        existing.status = summary.get("status")
        existing.updated_at = now
        return existing

    record = HRV(
        measurement_date=target_date,
        measurement_time=measurement_time,
        rmssd=last_night_avg,
        measurement_type="during_sleep",
        baseline_balanced_lower=summary.get("baseline_balanced_lower"),
        baseline_balanced_upper=summary.get("baseline_balanced_upper"),
        baseline_low_upper=summary.get("baseline_low_upper"),
        status=summary.get("status"),
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    return record


def hrv_record_to_api_dict(record: HRV) -> Dict[str, Any]:
    """Formaterer lagret HRV-rad for API-respons uten misvisende placeholder-verdier."""
    has_rmssd = record.rmssd is not None
    return {
        "date": record.measurement_date.isoformat(),
        "last_night_avg": record.rmssd,
        "last_night_5_min_high": None,
        "measurement_time": record.measurement_time.isoformat() if record.measurement_time else None,
        "measurement_type": record.measurement_type,
        "baseline_balanced_lower": record.baseline_balanced_lower,
        "baseline_balanced_upper": record.baseline_balanced_upper,
        "baseline_low_upper": record.baseline_low_upper,
        "status": record.status,
        **hrv_contract_fields(
            source="local_db",
            live_status="not_attempted",
            available=has_rmssd,
            reason=NO_RMSSD_HRV_REASON if not has_rmssd else None,
        ),
    }


def hrv_mcp_recovery_payload(
    record: Optional[HRV],
    *,
    baseline_7d: Optional[float] = None,
    delta_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """MCP recovery_context.hrv med samme kontrakt som router/service."""
    if record and record.rmssd is not None:
        contract = hrv_contract_fields(
            source="local_db",
            live_status="not_attempted",
            available=True,
        )
    else:
        contract = hrv_contract_fields(
            source="none",
            live_status="not_attempted",
            available=False,
            reason=NO_HRV_ACTIVITY_DAY_REASON,
        )
    return {
        "rmssd": record.rmssd if record and record.rmssd is not None else None,
        "status": record.status if record else None,
        "measurement_type": record.measurement_type if record else None,
        "baseline_7d": baseline_7d,
        "delta_pct_vs_previous_7d": delta_pct,
        **contract,
    }


def hrv_record_to_garmin_payload(record: HRV) -> Dict[str, Any]:
    return {
        "hrv_summary": {
            "last_night_avg": record.rmssd,
            "last_night_5_min_high": None,
            "weekly_avg": None,
            "status": record.status,
            "baseline_low_upper": record.baseline_low_upper,
            "baseline_balanced_lower": record.baseline_balanced_lower,
            "baseline_balanced_upper": record.baseline_balanced_upper,
        }
    }


def get_local_hrv_payload(
    target_date: date,
    db: Optional[Session] = None,
    storage: Optional[DataStorage] = None,
) -> tuple[Optional[Dict[str, Any]], HrvSource]:
    if db is not None:
        record = (
            db.query(HRV)
            .filter(
                HRV.measurement_date == target_date,
                HRV.rmssd.isnot(None),
            )
            .order_by(HRV.measurement_time.desc())
            .first()
        )
        if record and record.rmssd is not None:
            return hrv_record_to_garmin_payload(record), "local_db"

    if storage is not None:
        try:
            hrv_df = storage.get_hrv_data()
            if hrv_df is not None and not hrv_df.empty:
                day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                if day_start in hrv_df.index:
                    row = hrv_df.loc[day_start]
                else:
                    day_rows = hrv_df[hrv_df.index.to_series().dt.date == target_date]
                    if day_rows.empty:
                        return None, "none"
                    row = day_rows.iloc[-1]

                last_night_avg = row.get("last_night_avg")
                if last_night_avg is not None and not (isinstance(last_night_avg, float) and last_night_avg != last_night_avg):
                    return {
                        "hrv_summary": {
                            "last_night_avg": last_night_avg,
                            "last_night_5_min_high": row.get("last_night_5_min_high"),
                            "weekly_avg": row.get("weekly_avg"),
                            "status": row.get("status"),
                            "baseline_low_upper": row.get("baseline_low_upper"),
                            "baseline_balanced_lower": row.get("baseline_balanced_lower"),
                            "baseline_balanced_upper": row.get("baseline_balanced_upper"),
                        }
                    }, "local_parquet"
        except Exception:
            return None, "none"

    return None, "none"


def local_hrv_fetch_result(
    target_date: date,
    db: Optional[Session] = None,
    storage: Optional[DataStorage] = None,
) -> Optional[HrvFetchResult]:
    """DB-first: returnerer lokalt lagret HRV uten live Garmin-forsøk."""
    local_data, local_source = get_local_hrv_payload(target_date, db=db, storage=storage)
    if not local_data or local_source == "none":
        return None

    return HrvFetchResult(
        data=local_data,
        source=local_source,
        live_status="not_attempted",
        available=True,
        message=HRV_SOURCE_REASONS.get(local_source),
    )


async def resolve_hrv_for_date(
    garmin_client: Any,
    target_date: date,
    db: Optional[Session] = None,
    storage: Optional[DataStorage] = None,
    *,
    attempt_live: bool = True,
) -> HrvFetchResult:
    """Hent HRV live fra Garmin, med sikker fallback til lokal DB/parquet."""
    live_result: Optional[HrvLiveResult] = None
    if attempt_live and garmin_client is not None:
        request_dt = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
        if hasattr(garmin_client, "fetch_hrv_live"):
            live_result = await garmin_client.fetch_hrv_live(request_dt)
        elif hasattr(garmin_client, "get_hrv_data"):
            live_data = await garmin_client.get_hrv_data(request_dt)
            live_result = (
                HrvLiveResult(data=live_data, live_status="ok")
                if live_data
                else HrvLiveResult(
                    data=None,
                    live_status="not_found",
                    message=f"Ingen live HRV hos Garmin for {target_date.isoformat()}.",
                )
            )
        if live_result and live_result.data:
            return HrvFetchResult(
                data=live_result.data,
                source="garmin_live",
                live_status=live_result.live_status,
                available=True,
            )

    local_data, local_source = get_local_hrv_payload(target_date, db=db, storage=storage)
    if local_data:
        live_status: HrvLiveStatus = live_result.live_status if live_result else "not_attempted"
        return HrvFetchResult(
            data=local_data,
            source=local_source,
            live_status=live_status,
            available=True,
            message=LIVE_FALLBACK_HRV_REASON,
        )

    live_status = live_result.live_status if live_result else "not_attempted"
    message = live_result.message if live_result else "Ingen HRV funnet lokalt eller hos Garmin."
    return HrvFetchResult(
        data=None,
        source="none",
        live_status=live_status,
        available=False,
        message=message,
    )
