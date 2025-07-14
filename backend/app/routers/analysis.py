from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, date
from ..database.session import get_db
from ..database.models.summaries import DailySummary, WeeklySummary, MonthlySummary
from ..services.analysis_service import AnalysisService
from ..storage import DataStorage
from ..dependencies import get_analysis_service, get_db, get_data_storage
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
    
    # Map engelske aktivitetstyper til norske
    norwegian_activity_types = []
    for activity_type in activity_types:
        norwegian_type = activity_type_mapping.get(activity_type, activity_type)
        norwegian_activity_types.append(norwegian_type)
    
    filtered_summaries = []
    for summary in summaries:
        if not summary.activity_types_breakdown:
            continue
        
        # Parse JSON
        try:
            breakdown = json.loads(summary.activity_types_breakdown) if isinstance(summary.activity_types_breakdown, str) else summary.activity_types_breakdown
        except:
            continue
        
        # Sjekk om noen av de ønskede aktivitetstypene finnes (bruk norske navn)
        if any(activity_type in breakdown for activity_type in norwegian_activity_types):
            # Beregn andeler for valgte aktivitetstyper
            total_selected = sum(breakdown.get(activity_type, {}).get('count', 0) for activity_type in norwegian_activity_types)
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
                filtered_breakdown = {k: v for k, v in breakdown.items() if k in norwegian_activity_types}
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
    storage: DataStorage = Depends(get_data_storage)
):
    """Hent HRV-data over tid med valgfri datofiltrering. HRV-data er kun tilgjengelig fra 2023 og fremover."""
    try:
        # HRV-data er kun tilgjengelig fra 2023 og fremover
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            if start_dt.year < 2023:
                start_date = "2023-01-01"
                logger.info(f"HRV-startdato justert fra {start_date} til 2023-01-01 (HRV-data kun tilgjengelig fra 2023)")
        
        analysis_service = AnalysisService(storage)
        hrv_data = analysis_service.get_hrv_over_time(start_date, end_date)
        return hrv_data
    except Exception as e:
        logger.error(f"Feil ved henting av HRV-data: {str(e)}")
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
        return hrv_data
    except HTTPException as e:
        # Re-raise kjente HTTP-feil
        raise e
    except Exception as e:
        logger.error(f"Error fetching HRV data for activity {activity_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

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
