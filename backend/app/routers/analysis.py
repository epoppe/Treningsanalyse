from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, date, timedelta
from ..database.session import get_db
from ..database.models.summaries import DailySummary, WeeklySummary, MonthlySummary
from ..database.models.sync_state import SyncState
from ..services.analysis_service import AnalysisService
from ..storage import DataStorage
from ..dependencies import get_analysis_service, get_db, get_data_storage, get_garmin_client
from ..services.garmin_client import GarminClient
import logging
from ..database.models.activity import Activity
import json

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Analysis"]
)

def filter_summaries_by_activity_types(summaries, activity_types: List[str]):
    """Filtrer sammendrag basert på aktivitetstyper"""
    if not activity_types:
        return summaries
    
    # Mapping mellom engelsk typeKey og norske aktivitetstyper
    activity_type_mapping = {
        'running': 'Løping',
        'treadmill_running': 'Løping',
        'cycling': 'Sykling',
        'indoor_cycling': 'Sykling',
        'gravel_cycling': 'Sykling',
        'mountain_biking': 'Sykling',
        'walking': 'Fotturer',
        'hiking': 'Fotturer',
        'trail_running': 'Løping',
        'lap_swimming': 'Svømming',
        'open_water_swimming': 'Svømming',
        'resort_skiing': 'Alpint',
        'resort_skiing_snowboarding_ws': 'Alpint',
        'cross_country_skiing_ws': 'Langrenn',
        'indoor_cardio': 'Innendørs trening',
        'multi_sport': 'Multisport',
        'other': 'Annet'
    }
    
    # Breakdown i database bruker engelske typeKeys, ikke norske navn
    # Så vi må bruke activity_types direkte (engelsk)
    
    filtered_summaries = []
    for summary in summaries:
        if not summary.activity_types_breakdown:
            continue
        
        # Parse JSON
        try:
            breakdown = json.loads(summary.activity_types_breakdown) if isinstance(summary.activity_types_breakdown, str) else summary.activity_types_breakdown
        except:
            continue
        
        # Sjekk om noen av de ønskede aktivitetstypene finnes (bruk engelske typeKeys)
        if any(activity_type in breakdown for activity_type in activity_types):
            # Beregn andeler for valgte aktivitetstyper
            total_selected = sum(breakdown.get(activity_type, {}).get('count', 0) for activity_type in activity_types)
            total_all = sum(data.get('count', 0) for data in breakdown.values())
            
            if total_selected > 0 and total_all > 0:
                ratio = total_selected / total_all
                
                # Juster verdier basert på andel - men bevar alle andre felt
                summary.total_activities = int(summary.total_activities * ratio)
                summary.total_distance = summary.total_distance * ratio
                summary.total_duration = summary.total_duration * ratio
                summary.total_calories = summary.total_calories * ratio if summary.total_calories else 0
                summary.total_ascent = summary.total_ascent * ratio if summary.total_ascent else 0
                
                # Oppdater activity_types_breakdown til å bare inkludere valgte typer
                filtered_breakdown = {k: v for k, v in breakdown.items() if k in activity_types}
                summary.activity_types_breakdown = json.dumps(filtered_breakdown)
                
                filtered_summaries.append(summary)
    
    return filtered_summaries

@router.get("/daily-summaries")
async def get_daily_summaries(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(30, ge=1, le=365, description="Number of days to return"),
    activity_types: Optional[List[str]] = Query(None, description="Activity types to filter by"),
    db: Session = Depends(get_db)
):
    """Hent daglige sammendrag"""
    try:
        query = db.query(DailySummary)
        
        if start_date:
            query = query.filter(DailySummary.date >= start_date)
        if end_date:
            query = query.filter(DailySummary.date <= end_date)
        
        summaries = query.order_by(DailySummary.date.desc()).limit(limit).all()
        
        # Filtrer basert på aktivitetstyper hvis spesifisert
        if activity_types:
            summaries = filter_summaries_by_activity_types(summaries, activity_types)
        
        return summaries
    except Exception as e:
        logger.error(f"Feil ved henting av daglige sammendrag: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/weekly-summaries")
async def get_weekly_summaries(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(12, ge=1, le=104, description="Number of weeks to return"),
    activity_types: Optional[List[str]] = Query(None, description="Activity types to filter by"),
    db: Session = Depends(get_db)
):
    """Hent ukentlige sammendrag"""
    try:
        query = db.query(WeeklySummary)
        
        if start_date:
            query = query.filter(WeeklySummary.week_start_date >= start_date)
        if end_date:
            query = query.filter(WeeklySummary.week_end_date <= end_date)
        
        summaries = query.order_by(WeeklySummary.week_start_date.desc()).limit(limit).all()
        
        # Filtrer basert på aktivitetstyper hvis spesifisert
        if activity_types:
            summaries = filter_summaries_by_activity_types(summaries, activity_types)
        
        return summaries
    except Exception as e:
        logger.error(f"Feil ved henting av ukentlige sammendrag: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monthly-summaries")
async def get_monthly_summaries(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(12, ge=1, le=60, description="Number of months to return"),
    activity_types: Optional[List[str]] = Query(None, description="Activity types to filter by"),
    db: Session = Depends(get_db)
):
    """Hent månedlige sammendrag"""
    try:
        query = db.query(MonthlySummary)
        
        if start_date:
            query = query.filter(MonthlySummary.month_start_date >= start_date)
        if end_date:
            query = query.filter(MonthlySummary.month_end_date <= end_date)
        
        summaries = query.order_by(MonthlySummary.month_start_date.desc()).limit(limit).all()
        
        # Filtrer basert på aktivitetstyper hvis spesifisert
        if activity_types:
            summaries = filter_summaries_by_activity_types(summaries, activity_types)
        
        return summaries
    except Exception as e:
        logger.error(f"Feil ved henting av månedlige sammendrag: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sleep/range")
async def get_sleep_range_from_db(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Server-first søvn: les fra DB, fyll inn manglende dager fra Garmin og persister før retur."""
    try:
        from ..database.models.sleep import Sleep
        from ..database.models.sync_state import SyncState

        # Standardperiode: siste 30 dager
        today = date.today()
        if end_date is None:
            end_date = today
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        # Hent eksisterende rader i området
        q = db.query(Sleep).filter(Sleep.sleep_date >= start_date, Sleep.sleep_date <= end_date)
        rows = q.order_by(Sleep.sleep_date.asc()).all()
        existing_by_date = {r.sleep_date: r for r in rows}

        # Finn manglende datoer
        missing_dates = []
        cur = start_date
        while cur <= end_date:
            if cur not in existing_by_date:
                missing_dates.append(cur)
            cur += timedelta(days=1)

        # Hent og persister KUN manglende dager (unngå å hente hele intervallet når mesteparten finnes)
        if missing_dates:
            def to_sec(minutes_val: Optional[float]) -> Optional[float]:
                if minutes_val is None:
                    return None
                return float(minutes_val) * 60.0

            saved = 0
            for missing_day in missing_dates:
                one = await garmin_client.get_sleep_data(datetime.combine(missing_day, datetime.min.time()))
                if not one:
                    continue
                if not any(one.get(k) for k in [
                    "sleep_time", "total_sleep", "deep_sleep", "light_sleep", "rem_sleep", "sleep_score"
                ]):
                    continue

                d_date = datetime.strptime(one.get("date"), "%Y-%m-%d").date() if one.get("date") else None
                if d_date is None:
                    d_date = missing_day

                row = existing_by_date.get(d_date)
                if row is None:
                    from sqlalchemy.sql import func as sa_func
                    row = Sleep(sleep_date=d_date, created_at=sa_func.now(), updated_at=sa_func.now())
                    db.add(row)
                    existing_by_date[d_date] = row

                row.total_sleep_time = to_sec(one.get("sleep_time")) or to_sec(one.get("total_sleep"))
                row.deep_sleep_time = to_sec(one.get("deep_sleep"))
                row.light_sleep_time = to_sec(one.get("light_sleep"))
                row.rem_sleep_time = to_sec(one.get("rem_sleep"))
                row.awake_time = to_sec(one.get("awake_time"))
                row.sleep_score = one.get("sleep_score")

                from sqlalchemy.sql import func as sa_func
                row.updated_at = sa_func.now()
                saved += 1

            if saved > 0:
                db.commit()
                # Oppdater SyncState for sleep
                state = db.query(SyncState).filter_by(key="sleep").first()
                if not state:
                    state = SyncState(key="sleep")
                    db.add(state)
                state.last_synced_date = end_date
                state.last_synced_at = datetime.utcnow()
                db.commit()

        # Returner samlet resultat fra DB
        rows = db.query(Sleep).filter(Sleep.sleep_date >= start_date, Sleep.sleep_date <= end_date).order_by(Sleep.sleep_date.asc()).all()
        result = []
        for r in rows:
            result.append({
                "date": r.sleep_date.isoformat(),
                "sleep_time": (r.total_sleep_time/60.0) if r.total_sleep_time is not None else None,
                "total_sleep": (r.total_sleep_time/60.0) if r.total_sleep_time is not None else None,
                "deep_sleep": (r.deep_sleep_time/60.0) if r.deep_sleep_time is not None else None,
                "light_sleep": (r.light_sleep_time/60.0) if r.light_sleep_time is not None else None,
                "rem_sleep": (r.rem_sleep_time/60.0) if r.rem_sleep_time is not None else None,
                "awake_time": (r.awake_time/60.0) if r.awake_time is not None else None,
                "sleep_score": r.sleep_score,
            })
        return result
    except Exception as e:
        logger.error(f"Feil ved henting/persist av søvn: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monthly-comparison")
async def get_monthly_comparison(
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD), default=last day of current month"),
    months: int = Query(12, ge=1, le=36, description="Antall måneder å sammenligne (nåværende vs samme måned i fjor)"),
    activity_types: Optional[List[str]] = Query(None, description="Aktivitetstyper å filtrere på"),
    db: Session = Depends(get_db)
):
    """
    Returnerer server-beregnet månedstabell for de siste N månedene, med sammenligning mot samme måned i fjor.
    """
    try:
        # Sett slutt-dato til siste dag i inneværende måned hvis ikke spesifisert
        from calendar import monthrange
        today = date.today()
        if end_date is None:
            last_day = monthrange(today.year, today.month)[1]
            end_date = date(today.year, today.month, last_day)

        # Hjelpere
        def first_day_of_month(y: int, m: int) -> date:
            return date(y, m, 1)

        def add_months(d: date, delta: int) -> date:
            y = d.year + (d.month - 1 + delta) // 12
            m = (d.month - 1 + delta) % 12 + 1
            return first_day_of_month(y, m)

        end_month_start = first_day_of_month(end_date.year, end_date.month)
        start_month_start = add_months(end_month_start, -(months - 1))
        prev_year_start = add_months(start_month_start, -12)

        # Hent alle relevante månedlige sammendrag i ett spørring (24 måneder)
        query = db.query(MonthlySummary).filter(
            MonthlySummary.month_start_date >= prev_year_start,
            MonthlySummary.month_end_date <= end_date
        ).order_by(MonthlySummary.month_start_date.asc())
        summaries: List[MonthlySummary] = query.all()

        # Filtrer på aktivitetstyper om spesifisert
        if activity_types:
            summaries = filter_summaries_by_activity_types(summaries, activity_types)

        # Map: YYYY-MM -> summary
        def ym_key(d: date) -> str:
            return f"{d.year}-{str(d.month).zfill(2)}"

        by_month = {ym_key(s.month_start_date): s for s in summaries}

        # Bygg resultat for siste N måneder
        results = []
        for i in range(months):
            cur_month_start = add_months(start_month_start, i)
            cur_key = ym_key(cur_month_start)
            prev_key = f"{cur_month_start.year - 1}-{str(cur_month_start.month).zfill(2)}"

            cur = by_month.get(cur_key)
            prev = by_month.get(prev_key)

            def extract_payload(s: MonthlySummary):
                if not s:
                    return None
                return {
                    "total_activities": s.total_activities,
                    "total_distance": s.total_distance,
                    "total_duration": s.total_duration,
                    "avg_heart_rate": s.avg_heart_rate,
                    "avg_pace": s.avg_pace,
                }

            cur_payload = extract_payload(cur)
            prev_payload = extract_payload(prev)

            def pct(a: float, b: float) -> float:
                if b in (None, 0):
                    return 100.0 if (a or 0) > 0 else 0.0
                return ((a or 0) - (b or 0)) / b * 100.0

            deltas = None
            if cur_payload and prev_payload:
                deltas = {
                    "distance_pct": pct(cur_payload["total_distance"] or 0, prev_payload["total_distance"] or 0),
                    "duration_pct": pct(cur_payload["total_duration"] or 0, prev_payload["total_duration"] or 0),
                    "activities_pct": pct(cur_payload["total_activities"] or 0, prev_payload["total_activities"] or 0),
                }

            results.append({
                "year": cur_month_start.year,
                "month": cur_month_start.month,
                "current": cur_payload,
                "previous": prev_payload,
                "deltas": deltas,
            })

        return results
    except Exception as e:
        logger.error(f"Feil ved henting av monthly comparison: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/refresh-summaries")
async def refresh_summaries():
    """Oppdater alle sammendragstabeller basert på aktiviteter i databasen"""
    try:
        from ..services.summary_service import SummaryService
        
        summary_service = SummaryService()
        
        # Beregn alle sammendrag
        daily_count = summary_service.calculate_daily_summaries()
        weekly_count = summary_service.calculate_weekly_summaries()
        monthly_count = summary_service.calculate_monthly_summaries()
        
        logger.info(f"Sammendrag oppdatert: {daily_count} daglige, {weekly_count} ukentlige, {monthly_count} månedlige")
        
        return {
            "message": "Sammendrag er oppdatert med aktiviteter fra databasen",
            "daily_summaries": daily_count,
            "weekly_summaries": weekly_count, 
            "monthly_summaries": monthly_count
        }
    except Exception as e:
        logger.error(f"Feil ved oppdatering av sammendrag: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync-state")
async def get_sync_state(db: Session = Depends(get_db)):
    """Admin: Hent SyncState for alle nøkler."""
    try:
        states = db.query(SyncState).all()
        return [
            {
                "key": s.key,
                "last_synced_date": s.last_synced_date,
                "last_synced_at": s.last_synced_at,
                "meta": s.meta,
            }
            for s in states
        ]
    except Exception as e:
        logger.error(f"Feil ved henting av sync-state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-state/reset/{key}")
async def reset_sync_state(key: str, db: Session = Depends(get_db)):
    """Admin: Nullstill SyncState for en gitt nøkkel."""
    try:
        state = db.query(SyncState).filter_by(key=key).first()
        if not state:
            state = SyncState(key=key)
            db.add(state)
        state.last_synced_date = None
        state.last_synced_at = None
        state.meta = None
        db.commit()
        return {"message": f"SyncState '{key}' er nullstilt."}
    except Exception as e:
        logger.error(f"Feil ved nullstilling av sync-state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary-stats")
async def get_summary_stats(db: Session = Depends(get_db)):
    """Hent oversikt over sammendragstabeller"""
    try:
        daily_count = db.query(DailySummary).count()
        weekly_count = db.query(WeeklySummary).count()
        monthly_count = db.query(MonthlySummary).count()
        
        # Finn datoområder
        daily_range = db.query(
            func.min(DailySummary.date).label('min_date'),
            func.max(DailySummary.date).label('max_date')
        ).first()
        
        weekly_range = db.query(
            func.min(WeeklySummary.week_start_date).label('min_date'),
            func.max(WeeklySummary.week_end_date).label('max_date')
        ).first()
        
        monthly_range = db.query(
            func.min(MonthlySummary.month_start_date).label('min_date'),
            func.max(MonthlySummary.month_end_date).label('max_date')
        ).first()
        
        return {
            "daily": {
                "count": daily_count,
                "date_range": {
                    "start": daily_range.min_date if daily_range else None,
                    "end": daily_range.max_date if daily_range else None
                }
            },
            "weekly": {
                "count": weekly_count,
                "date_range": {
                    "start": weekly_range.min_date if weekly_range else None,
                    "end": weekly_range.max_date if weekly_range else None
                }
            },
            "monthly": {
                "count": monthly_count,
                "date_range": {
                    "start": monthly_range.min_date if monthly_range else None,
                    "end": monthly_range.max_date if monthly_range else None
                }
            }
        }
    except Exception as e:
        logger.error(f"Feil ved henting av sammendragstatistikk: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hrv")
async def get_hrv_data(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    storage: DataStorage = Depends(get_data_storage),
    db: Session = Depends(get_db)
):
    """Hent HRV-data over tid med valgfri datofiltrering. HRV-data er kun tilgjengelig fra 2023 og fremover."""
    try:
        # HRV-data er kun tilgjengelig fra 2023 og fremover
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            if start_dt.year < 2023:
                start_date = "2023-01-01"
                logger.info(f"HRV-startdato justert fra {start_date} til 2023-01-01 (HRV-data kun tilgjengelig fra 2023)")
        
        # Bruk HRVService for å hente data fra databasen
        from ..services.hrv_service import HRVService
        hrv_service = HRVService(storage)
        hrv_data = hrv_service.get_hrv_over_time(db, start_date, end_date)
        return hrv_data
    except Exception as e:
        logger.error(f"Feil ved henting av HRV-data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hrv/statistics")
async def get_hrv_statistics(
    storage: DataStorage = Depends(get_data_storage),
    db: Session = Depends(get_db)
):
    """Hent statistikk over HRV-data i databasen."""
    try:
        from ..services.hrv_service import HRVService
        hrv_service = HRVService(storage)
        statistics = hrv_service.get_hrv_statistics(db)
        return statistics
    except Exception as e:
        logger.error(f"Feil ved henting av HRV-statistikk: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hrv/by-activity/{activity_id}", response_model=dict)
def get_hrv_for_activity(
    activity_id: int,
    analysis_service: AnalysisService = Depends(get_analysis_service),
    db: Session = Depends(get_db)
):
    """
    Henter HRV-data for den dagen en spesifikk aktivitet ble utført.
    """
    try:
        hrv_data = analysis_service.get_hrv_for_activity_date(activity_id, db)
        if hrv_data is None:
            raise HTTPException(status_code=404, detail="Ingen HRV-data funnet for denne aktiviteten")
        return hrv_data
    except HTTPException as e:
        # Re-raise kjente HTTP-feil
        raise e
    except Exception as e:
        logger.error(f"Error fetching HRV data for activity {activity_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/hrv/by-activities")
async def get_hrv_for_multiple_activities(
    activity_ids: str = Query(..., description="Comma-separated list of activity IDs"),
    storage: DataStorage = Depends(get_data_storage),
    db: Session = Depends(get_db)
):
    """Henter HRV-data for flere aktiviteter på en gang fra databasen med bulk-query (optimalisert)."""
    try:
        # Parse activity IDs
        activity_id_list = [int(id.strip()) for id in activity_ids.split(',') if id.strip()]
        
        if not activity_id_list:
            return {"hrv_data": {}}
        
        logger.info(f"📊 HRV Bulk: Henter HRV-data for {len(activity_id_list)} aktiviteter...")
        
        # Bulk-query: Hent alle aktiviteter på en gang
        from ..database.models import Activity, HRV
        from sqlalchemy import func, cast, Date
        
        # Konverter til string for database-query
        activity_id_str_list = [str(id) for id in activity_id_list]
        
        # Hent aktiviteter med deres datoer (bulk query)
        activities = db.query(
            Activity.activity_id,
            Activity.start_time
        ).filter(
            Activity.activity_id.in_(activity_id_str_list)
        ).all()
        
        # Bygg mapping fra activity_id til dato (konverter datetime til date)
        activity_date_map = {}
        for act in activities:
            activity_date = act.start_time.date() if act.start_time else None
            if activity_date:
                activity_date_map[str(act.activity_id)] = activity_date
        
        logger.info(f"📅 Aktivitetsdatoer: {list(activity_date_map.values())[:5]}...")
        
        # Hent alle unike datoer
        unique_dates = list(set(activity_date_map.values()))
        logger.info(f"🔍 Søker etter HRV for {len(unique_dates)} unike datoer")
        
        # Bulk-query: Hent HRV-data for alle relevante datoer på en gang
        hrv_records = db.query(HRV).filter(
            HRV.measurement_date.in_(unique_dates)
        ).all()
        
        logger.info(f"💾 Fant {len(hrv_records)} HRV-records i database")
        
        # Bygg mapping fra dato til HRV-data
        hrv_by_date = {}
        for hrv in hrv_records:
            hrv_by_date[hrv.measurement_date] = {
                "date": hrv.measurement_date.strftime('%Y-%m-%d'),
                "last_night_avg": hrv.rmssd,
                "measurement_time": hrv.measurement_time.isoformat() if hrv.measurement_time else None,
                "measurement_type": hrv.measurement_type
            }
        
        logger.info(f"📊 HRV-dato-map har {len(hrv_by_date)} entries")
        
        # Bygg resultat: Map aktivitets-ID til HRV-data via dato
        hrv_results = {}
        for activity_id in activity_id_list:
            activity_id_str = str(activity_id)
            activity_date = activity_date_map.get(activity_id_str)
            
            if activity_date and activity_date in hrv_by_date:
                # HRV-data finnes for denne datoen
                hrv_results[activity_id_str] = hrv_by_date[activity_date]
            else:
                # Ingen HRV-data for denne aktiviteten
                hrv_results[activity_id_str] = None
        
        activities_with_hrv = len([v for v in hrv_results.values() if v is not None])
        logger.info(f"✅ HRV Bulk: Returnerer {activities_with_hrv}/{len(activity_id_list)} aktiviteter med HRV-data")
        
        return {
            "hrv_data": hrv_results,
            "total_activities": len(activity_id_list),
            "activities_with_hrv": activities_with_hrv
        }
        
    except Exception as e:
        logger.error(f"❌ HRV Bulk: Feil ved henting av HRV-data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/body-battery/by-activity/{activity_id}", response_model=dict)
def get_body_battery_for_activity(
    activity_id: int,
    analysis_service: AnalysisService = Depends(get_analysis_service),
    db: Session = Depends(get_db)
):
    """
    Henter Body Battery-nivå ved start av en spesifikk aktivitet.
    Basert på søvn, HRV, stress og restitusjonsdata.
    """
    try:
        body_battery_data = analysis_service.calculate_body_battery_start(activity_id, db)
        if body_battery_data is None:
            raise HTTPException(status_code=404, detail="Could not calculate Body Battery for this activity")
        return body_battery_data
    except HTTPException as e:
        # Re-raise kjente HTTP-feil
        raise e
    except Exception as e:
        logger.error(f"Error calculating Body Battery for activity {activity_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/body-battery")
async def get_body_battery_data(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    storage: DataStorage = Depends(get_data_storage),
    db: Session = Depends(get_db)
):
    """Henter Body Battery-data for en tidsperiode fra databasen"""
    try:
        from ..services.body_battery_service import BodyBatteryService
        from ..services.garmin_client import GarminClient
        from ..config import settings
        
        # Initialiser Body Battery service
        garmin_client = GarminClient(
            email=settings.GARMIN_EMAIL,
            password=settings.GARMIN_PASSWORD,
            token_dir=settings.TOKEN_DIR
        )
        body_battery_service = BodyBatteryService(garmin_client)
        
        # Bruk standard tidsperiode hvis ikke spesifisert
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        # Hent data fra databasen
        result = body_battery_service.get_body_battery_over_time(db, start_date, end_date)
        
        return result
        
    except Exception as e:
        logger.error(f"Feil ved henting av Body Battery-data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/body-battery/statistics")
async def get_body_battery_statistics(
    storage: DataStorage = Depends(get_data_storage),
    db: Session = Depends(get_db)
):
    """Henter statistikk for Body Battery-data"""
    try:
        from ..services.body_battery_service import BodyBatteryService
        from ..services.garmin_client import GarminClient
        from ..config import settings
        
        # Initialiser Body Battery service
        garmin_client = GarminClient(
            email=settings.GARMIN_EMAIL,
            password=settings.GARMIN_PASSWORD,
            token_dir=settings.TOKEN_DIR
        )
        body_battery_service = BodyBatteryService(garmin_client)
        
        # Hent statistikk fra databasen
        result = body_battery_service.get_body_battery_statistics(db)
        
        return result
        
    except Exception as e:
        logger.error(f"Feil ved henting av Body Battery-statistikk: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
