from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..dependencies import get_db
from ..database.models.activity import Activity
from ..services.garmin_client import GarminClient
from ..services.power_service import PowerService
from ..storage import DataStorage
from ..dependencies import get_data_storage, get_garmin_client
import plotly.graph_objects as go
import plotly.io as pio
import pandas as pd
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ActivityTypeResponse(BaseModel):
    typeKey: Optional[str] = None
    parentTypeKey: Optional[str] = None

class ActivityResponse(BaseModel):
    activityId: str
    activityName: Optional[str]
    startTimeLocal: datetime
    distance: Optional[float]
    duration: Optional[float]
    calories: Optional[float]
    averageHR: Optional[float]
    averageSpeed: Optional[float]
    averagePace: Optional[float]
    averageRunningCadenceInStepsPerMinute: Optional[float]
    vO2MaxValue: Optional[float]
    activityType: Optional[ActivityTypeResponse]
    avgStrideLength: Optional[float] = Field(None, description="Average stride length in meters")
    negativeSplitPercent: Optional[float] = Field(None, description="Negative split percentage")
    decouplingPercent: Optional[float] = Field(None, description="Decoupling percentage")
    trainingReadinessScore: Optional[float] = Field(None, description="Training readiness score (0-100)")
    totalTrainingEffect: Optional[float] = Field(None, description="Aerobic Training Effect (1.0-5.0)")
    totalAnaerobicTrainingEffect: Optional[float] = Field(None, description="Anaerobic Training Effect (1.0-5.0)")
    epoc: Optional[float] = Field(None, description="Exercise Post Oxygen Consumption (også brukt som TSS)")
    averagePowerWatts: Optional[float] = Field(None, description="Average power in watts")
    lactateThresholdSpeed: Optional[float] = Field(None, description="Lactate threshold speed in m/s")
    details: Optional[Dict[str, Any]] = Field(None, description="Detailed metrics for the activity")

@router.get("/activities/date-range", response_model=List[ActivityResponse])
def get_activities_by_date_range(
    start_date: str = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: str = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    force_refresh: Optional[str] = Query(None, description="Force refresh of power calculations"),
    db: Session = Depends(get_db)
):
    """Hent aktiviteter for en spesifikk datoperiode."""
    try:
        from datetime import datetime
        
        # Konverter string til datetime
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Hent aktiviteter i perioden med eager loading av activity_type
        activities = db.query(Activity).options(
            joinedload(Activity.activity_type)
        ).filter(
            Activity.start_time >= start_dt,
            Activity.start_time <= end_dt
        ).order_by(Activity.start_time.desc()).all()
        
        # Initialiser PowerService for power-beregning
        storage = DataStorage()
        power_service = PowerService(storage)
        
        response_data = []
        for act in activities:
            # Hent aktivitetstype
            act_type_data = None
            if act.activity_type:
                act_type_data = {
                    "typeKey": act.activity_type.type_key,
                    "parentTypeKey": act.activity_type.parent_type_key
                }
            
            # Beregn gjennomsnittlig steglengde hvis tilgjengelig
            avg_stride_length = None
            if act.average_running_cadence and act.distance and act.total_steps:
                # Gjennomsnittlig steglengde = distanse / antall steg
                avg_stride_length = act.distance / act.total_steps
            
            # Hent power for løpeaktiviteter
            average_power_watts = None
            if act.activity_type and act.activity_type.type_key == 'running' or (act_type_data and act_type_data.get('typeKey') == 'running'):
                # Bruk lagret power fra database hvis tilgjengelig
                if act.average_power is not None:
                    average_power_watts = act.average_power
                elif force_refresh == 'true':
                    # Beregn power kun hvis force_refresh er true og power ikke er lagret
                    try:
                        power_result = power_service.calculate_activity_power(int(act.activity_id), db)
                        if power_result:
                            average_power_watts = power_result['average_power_watts']
                    except Exception as e:
                        logger.warning(f"Kunne ikke beregne power for aktivitet {act.activity_id}: {e}")
            
            # Manually construct the dictionary for the response, ensuring correct field names
            response_data.append({
                "activityId": act.activity_id,
                "activityName": act.activity_name,
                "startTimeLocal": act.start_time,
                "distance": act.distance,
                "duration": act.duration,
                "calories": act.calories,
                "averageHR": act.average_heart_rate,
                "averageSpeed": act.average_speed,
                "averagePace": act.average_pace,
                "averageRunningCadenceInStepsPerMinute": act.average_running_cadence,
                "vO2MaxValue": act.vo2_max,
                "activityType": act_type_data,
                "avgStrideLength": avg_stride_length,
                "negativeSplitPercent": act.negative_split_percent,
                "decouplingPercent": act.decoupling_percent,
                "trainingReadinessScore": act.training_readiness_score,
                "totalTrainingEffect": act.total_training_effect,
                "totalAnaerobicTrainingEffect": act.total_anaerobic_training_effect,
                "epoc": act.epoc,  # Exercise Post Oxygen Consumption (også brukt som TSS)
                "averagePowerWatts": average_power_watts,  # Power i watt
                "lactateThresholdSpeed": act.lactate_threshold_speed,  # Lactate threshold speed
                "details": act.detailed_metrics
            })
            
        logger.info(f"Returnerer {len(response_data)} aktiviteter for perioden {start_date} til {end_date}")
        return response_data
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.get("/activities", response_model=List[ActivityResponse])
def get_activities(
    limit: int = 100, 
    offset: int = 0, 
    since: Optional[str] = Query(None, description="Hent aktiviteter etter denne datoen (YYYY-MM-DD)"),
    force_refresh: Optional[str] = Query(None, description="Force refresh of power calculations"),
    db: Session = Depends(get_db)
):
    """
    Retrieve activities from the database with pagination, and format them for the API response.
    Optimized with caching to reduce power calculations.
    """
    try:
        logger.info(f"Henter aktiviteter fra databasen (limit: {limit}, offset: {offset}, since: {since})...")
        
        # Bygg query
        query = db.query(Activity).options(joinedload(Activity.activity_type))
        
        # Legg til since filter hvis gitt
        if since:
            try:
                since_date = datetime.strptime(since, "%Y-%m-%d")
                query = query.filter(Activity.start_time >= since_date)
                logger.info(f"Filtrerer aktiviteter etter {since_date}")
            except ValueError:
                logger.warning(f"Ugyldig since dato format: {since}")
        
        # Hent aktiviteter sortert etter starttid (nyeste først)
        activities = query.order_by(Activity.start_time.desc()).limit(limit).offset(offset).all()
        logger.info(f"Hentet {len(activities)} aktiviteter fra databasen")
        
        # Initialiser PowerService kun hvis vi trenger å beregne power
        storage = None
        power_service = None
        
        response_data = []
        for act in activities:
            # Construct the nested activity type object
            act_type_data = None
            if act.activity_type:
                act_type_data = {
                    "typeKey": act.activity_type.type_key,
                    "parentTypeKey": act.activity_type.parent_type_key
                }

            # Calculate average stride length
            avg_stride_length = None
            if act.average_speed and act.average_running_cadence and act.average_running_cadence > 0:
                # average_speed is in m/s, cadence is in steps/min.
                # Convert speed to m/min: average_speed * 60
                # Stride length (m/step) = (m/min) / (steps/min)
                avg_stride_length = (act.average_speed * 60) / act.average_running_cadence

            # Hent power for løpeaktiviteter - kun hvis ikke allerede lagret
            average_power_watts = None
            if (act.activity_type and act.activity_type.type_key == 'running') or (act_type_data and act_type_data.get('typeKey') == 'running'):
                # Bruk lagret power fra database hvis tilgjengelig
                if act.average_power is not None:
                    average_power_watts = act.average_power
                elif force_refresh == 'true':
                    # Beregn power kun hvis force_refresh er true og power ikke er lagret
                    if storage is None:
                        storage = DataStorage()
                        power_service = PowerService(storage)
                    try:
                        power_result = power_service.calculate_activity_power(int(act.activity_id), db)
                        if power_result:
                            average_power_watts = power_result['average_power_watts']
                    except Exception as e:
                        logger.warning(f"Kunne ikke beregne power for aktivitet {act.activity_id}: {e}")

            # Manually construct the dictionary for the response, ensuring correct field names
            response_data.append({
                "activityId": act.activity_id,
                "activityName": act.activity_name,
                "startTimeLocal": act.start_time,
                "distance": act.distance,
                "duration": act.duration,
                "calories": act.calories,
                "averageHR": act.average_heart_rate,
                "averageSpeed": act.average_speed,
                "averagePace": act.average_pace,
                "averageRunningCadenceInStepsPerMinute": act.average_running_cadence,
                "vO2MaxValue": act.vo2_max,
                "activityType": act_type_data,
                "avgStrideLength": avg_stride_length,
                "negativeSplitPercent": act.negative_split_percent,
                "decouplingPercent": act.decoupling_percent,
                "trainingReadinessScore": act.training_readiness_score,
                "totalTrainingEffect": act.total_training_effect,
                "totalAnaerobicTrainingEffect": act.total_anaerobic_training_effect,
                "epoc": act.epoc,  # Exercise Post Oxygen Consumption (også brukt som TSS)
                "averagePowerWatts": average_power_watts,  # Power i watt
                "lactateThresholdSpeed": act.lactate_threshold_speed,  # Lactate threshold speed
                "details": act.detailed_metrics
            })
            
        logger.info(f"Returnerer {len(response_data)} aktiviteter til frontend")
        return response_data
    except Exception as e:
        import traceback
        traceback.print_exc() # This will print the error to the backend console
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.get("/activities/new", response_model=List[ActivityResponse])
def get_new_activities(
    since: str = Query(..., description="Hent aktiviteter etter denne datoen (YYYY-MM-DD)"),
    force_refresh: Optional[str] = Query(None, description="Force refresh of power calculations"),
    db: Session = Depends(get_db)
):
    """
    Retrieve only new activities since a given date.
    This is optimized for incremental updates.
    """
    try:
        logger.info(f"Henter nye aktiviteter siden {since}...")
        
        # Konverter since til datetime
        since_date = datetime.strptime(since, "%Y-%m-%d")
        
        # Hent kun nye aktiviteter
        activities = db.query(Activity).options(joinedload(Activity.activity_type)).filter(
            Activity.start_time >= since_date
        ).order_by(Activity.start_time.desc()).all()
        
        logger.info(f"Hentet {len(activities)} nye aktiviteter siden {since_date}")
        
        # Initialiser PowerService for power-beregning
        storage = DataStorage()
        power_service = PowerService(storage)
        
        response_data = []
        for act in activities:
            # Construct the nested activity type object
            act_type_data = None
            if act.activity_type:
                act_type_data = {
                    "typeKey": act.activity_type.type_key,
                    "parentTypeKey": act.activity_type.parent_type_key
                }

            # Calculate average stride length
            avg_stride_length = None
            if act.average_speed and act.average_running_cadence and act.average_running_cadence > 0:
                avg_stride_length = (act.average_speed * 60) / act.average_running_cadence

            # Hent power for løpeaktiviteter
            average_power_watts = None
            if (act.activity_type and act.activity_type.type_key == 'running') or (act_type_data and act_type_data.get('typeKey') == 'running'):
                # Bruk lagret power fra database hvis tilgjengelig
                if act.average_power is not None:
                    average_power_watts = act.average_power
                elif force_refresh == 'true':
                    # Beregn power kun hvis force_refresh er true og power ikke er lagret
                    try:
                        power_result = power_service.calculate_activity_power(int(act.activity_id), db)
                        if power_result:
                            average_power_watts = power_result['average_power_watts']
                    except Exception as e:
                        logger.warning(f"Kunne ikke beregne power for aktivitet {act.activity_id}: {e}")

            # Manually construct the dictionary for the response
            response_data.append({
                "activityId": act.activity_id,
                "activityName": act.activity_name,
                "startTimeLocal": act.start_time,
                "distance": act.distance,
                "duration": act.duration,
                "calories": act.calories,
                "averageHR": act.average_heart_rate,
                "averageSpeed": act.average_speed,
                "averagePace": act.average_pace,
                "averageRunningCadenceInStepsPerMinute": act.average_running_cadence,
                "vO2MaxValue": act.vo2_max,
                "activityType": act_type_data,
                "avgStrideLength": avg_stride_length,
                "negativeSplitPercent": act.negative_split_percent,
                "decouplingPercent": act.decoupling_percent,
                "trainingReadinessScore": act.training_readiness_score,
                "totalTrainingEffect": act.total_training_effect,
                "totalAnaerobicTrainingEffect": act.total_anaerobic_training_effect,
                "epoc": act.epoc,
                "averagePowerWatts": average_power_watts,
                "lactateThresholdSpeed": act.lactate_threshold_speed,
                "details": act.detailed_metrics
            })
            
        logger.info(f"Returnerer {len(response_data)} nye aktiviteter til frontend")
        return response_data
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.get("/activities/count")
def get_activity_count(db: Session = Depends(get_db)):
    """
    Retrieve the total count of activities in the database.
    """
    try:
        logger.info("Henter totalt antall aktiviteter fra databasen...")
        count = db.query(Activity).count()
        logger.info(f"Totalt antall aktiviteter: {count}")
        return {"count": count}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.get("/activities/{activity_id}/details", response_model=List[Dict[str, Any]])
async def read_activity_details(
    activity_id: int,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """
    Henter detaljerte tidsseriedata for en aktivitet.
    Sjekker først lokal lagring. Hvis data ikke finnes, hentes de fra Garmin.
    """
    try:
        # 1. Sjekk lokal lagring først
        details = storage.get_activity_details(activity_id)
        if details is not None:
            return details.to_dict('records')

        # 2. Hvis ikke lokalt, hent fra Garmin
        fit_data = await garmin_client.get_activity_details(str(activity_id))
        if not fit_data:
            raise HTTPException(status_code=404, detail="Kunne ikke hente aktivitetsdetaljer fra Garmin.")

        # 3. Parse FIT-data til parquet-format
        from ..services.sync_service import SyncService
        sync_service = SyncService(garmin_client, storage, None)  # db_session er ikke nødvendig for parsing
        parsed_data = sync_service._parse_fit_data(fit_data)
        
        if not parsed_data or 'records' not in parsed_data:
            raise HTTPException(status_code=500, detail="Kunne ikke parse FIT-data.")

        # 4. Konverter til parquet-format
        parquet_records = []
        for record in parsed_data['records']:
            parquet_record = {
                'activity_id': activity_id,
                'timestamp': record.get('timestamp'),
                'latitude': record.get('position_lat'),
                'longitude': record.get('position_long'),
                'speed': record.get('speed'),
                'heart_rate': record.get('heart_rate'),
                'cadence': record.get('cadence'),
                'temperature': record.get('temperature'),
                'altitude': record.get('enhanced_altitude') or record.get('altitude')
            }
            
            # Kun legg til record hvis den har nødvendige data
            if parquet_record['timestamp'] is not None:
                parquet_records.append(parquet_record)

        # 5. Lagre dataene lokalt
        if parquet_records:
            storage.save_activity_details(parquet_records)
        else:
            raise HTTPException(status_code=500, detail="Ingen gyldige data funnet i FIT-filen.")

        # 6. Hent og returner de nylig lagrede dataene
        new_details = storage.get_activity_details(activity_id)
        if new_details is not None:
            return new_details.to_dict('records')
        else:
            # Dette skal i teorien ikke skje hvis lagring var vellykket
            raise HTTPException(status_code=500, detail="Klarte ikke å hente data etter lagring.")

    except Exception as e:
        logger.error(f"Feil under henting av aktivitetsdetaljer for {activity_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"En feil oppstod: {str(e)}")

@router.get("/activities/{activity_id}/charts/{chart_type}")
def get_activity_chart(
    activity_id: int, 
    chart_type: str, 
    storage: DataStorage = Depends(get_data_storage)
):
    """
    Generate and return a Plotly chart for a given activity and chart type.
    """
    details_list = storage.get_activity_details(activity_id)
    if details_list is None:
        raise HTTPException(status_code=404, detail="Activity details not found")

    details_df = pd.DataFrame(details_list)
    # Konverter timestamp til datetime-objekter hvis det ikke allerede er det
    if 'timestamp' in details_df.columns and not pd.api.types.is_datetime64_any_dtype(details_df['timestamp']):
        details_df['timestamp'] = pd.to_datetime(details_df['timestamp'])

    # Beregn forløpt tid for x-aksen
    if details_df.empty or 'timestamp' not in details_df.columns or details_df['timestamp'].dropna().empty:
        raise HTTPException(status_code=404, detail="Aktiviteten mangler tidsstempeldata for å bygge grafer.")
    
    start_time = details_df['timestamp'].min()
    elapsed_timedelta = details_df['timestamp'] - start_time
    # Konverter Timedelta til datetime-objekter for at Plotly skal kunne formatere dem
    details_df['elapsed_time'] = pd.to_datetime(elapsed_timedelta.dt.total_seconds(), unit='s')

    fig = go.Figure()

    if chart_type == 'pulse':
        if 'heart_rate' not in details_df.columns or details_df['heart_rate'].dropna().empty:
            raise HTTPException(status_code=404, detail="No heart rate data available for this activity.")
        
        # Filter out nulls and calculate average
        pulse_data = details_df['heart_rate'].dropna()
        avg_pulse = pulse_data.mean()

        # Create Area Chart
        fig.add_trace(go.Scatter(
            x=details_df['elapsed_time'], 
            y=pulse_data, 
            fill='tozeroy',
            mode='lines', 
            name='Puls',
            line=dict(color='red')
        ))
        # Add average line
        fig.add_hline(
            y=avg_pulse, 
            line_dash="dot",
            line_color="grey",
            annotation_text="Gjennomsnitt", 
            annotation_position="bottom right"
        )
        fig.update_layout(title_text='Puls', yaxis_title='Puls (slag/min)')
        # Sett y-aksens startverdi til 80 for bedre visuell fremstilling
        fig.update_yaxes(range=[80, pulse_data.max() + 10]) # Legger til 10 i pusterom over maks

    elif chart_type == 'altitude':
        if 'altitude' not in details_df.columns or details_df['altitude'].dropna().empty:
            raise HTTPException(status_code=404, detail="No altitude data available for this activity.")

        altitude_data = details_df['altitude'].dropna()
        avg_altitude = altitude_data.mean()

        fig.add_trace(go.Scatter(
            x=details_df['elapsed_time'], 
            y=altitude_data,
            fill='tozeroy',
            mode='lines',
            name='Høyde',
            line=dict(color='green')
        ))
        fig.add_hline(
            y=avg_altitude, 
            line_dash="dot",
            line_color="grey",
            annotation_text="Gjennomsnitt", 
            annotation_position="bottom right"
        )
        fig.update_layout(title_text='Høydemeter', yaxis_title='Høydemeter (moh)')
    
    elif chart_type == 'pace':
        if 'speed' not in details_df.columns or details_df['speed'].dropna().empty:
            raise HTTPException(status_code=404, detail="No speed data available for this activity.")

        # ANTAGELSE: 'speed' fra Garmin er i km/t, ikke m/s. Fjerner unødvendig konvertering.
        speed_kph = details_df['speed']
        pace_data_raw = 60 / speed_kph.where(speed_kph > 0)

        # Fjerner ugyldige verdier og sørger for at tidsstemplene stemmer overens
        pace_data = pace_data_raw.dropna()
        # Sikrer at vi bruker de korrekte, formaterbare tidsdataene
        elapsed_time_data = details_df['elapsed_time'][pace_data.index]

        if pace_data.empty:
            raise HTTPException(status_code=404, detail="No valid speed data to calculate pace.")

        avg_pace_val = pace_data.mean()

        # Sett faste verdier for y-aksen som ønsket av brukeren
        max_pace_display = 10
        min_pace_display = 3

        # Løsning for fyll-retning: transformer data i stedet for å invertere aksen
        y_transformed = max_pace_display - pace_data
        
        # Lag formaterte strenger for hover-info
        def format_pace_for_hover(p):
            minutes = int(p)
            seconds = int((p * 60) % 60)
            return f"{minutes:02d}:{seconds:02d}"

        hover_text = pace_data.apply(format_pace_for_hover)

        fig.add_trace(go.Scatter(
            x=elapsed_time_data, 
            y=y_transformed,
            customdata=hover_text,
            hovertemplate='<b>Forløpt tid:</b> %{x|%M:%S}<br><b>Tempo:</b> %{customdata} min/km<extra></extra>',
            fill='tozeroy', # Fyller nå korrekt ned mot bunnen
            mode='lines',
            name='Tempo',
            line=dict(color='blue')
        ))

        # Transformer gjennomsnittslinjen på samme måte
        avg_pace_transformed = max_pace_display - avg_pace_val
        fig.add_hline(
            y=avg_pace_transformed, 
            line_dash="dot",
            line_color="grey",
            annotation_text="Snitt", 
            annotation_position="bottom right"
        )

        fig.update_layout(
            title_text='Tempo', 
            yaxis_title='Tempo (min/km)'
        )
        
        # Lag og sett manuelle akse-etiketter for å vise originalverdier
        tickvals_orig = list(range(min_pace_display, max_pace_display + 1))
        tickvals_transformed = [max_pace_display - v for v in tickvals_orig]
        ticktext = [str(v) for v in tickvals_orig]

        fig.update_yaxes(
            range=[0, max_pace_display - min_pace_display], # Fast område
            tickvals=tickvals_transformed,
            ticktext=ticktext
        )

    else:
        raise HTTPException(status_code=404, detail=f"Chart type '{chart_type}' not found")

    # Felles x-akse-formatering for alle grafer
    fig.update_xaxes(
        title_text='Forløpt tid',
        tickformat='%M:%S'
    )

    # Konverter figuren til en JSON-streng med Plotlys egen metode
    chart_json = pio.to_json(fig)
    return Response(content=chart_json, media_type="application/json")

@router.get("/activities/{activity_id}/negative-split")
def get_activity_negative_split(
    activity_id: int, 
    storage: DataStorage = Depends(get_data_storage),
    db: Session = Depends(get_db)
):
    """
    Beregner negativ split for en aktivitet basert på FIT-data.
    """
    try:
        from ..services.analysis_service import AnalysisService
        
        analysis_service = AnalysisService(storage)
        result = analysis_service.calculate_negative_split(activity_id, db)
        
        return result
        
    except HTTPException:
        # Re-raise HTTPExceptions (like 404) without wrapping them
        raise
    except Exception as e:
        logger.error(f"Feil ved beregning av negative split for aktivitet {activity_id}: {e}")
        raise HTTPException(status_code=500, detail=f"En feil oppstod: {str(e)}")

@router.get("/activities/{activity_id}/decoupling")
def get_activity_decoupling(
    activity_id: int, 
    storage: DataStorage = Depends(get_data_storage),
    db: Session = Depends(get_db)
):
    """
    Beregner cardiac-aerobic decoupling for en aktivitet basert på FIT-data.
    """
    try:
        from ..services.analysis_service import AnalysisService
        
        analysis_service = AnalysisService(storage)
        result = analysis_service.calculate_decoupling(activity_id, db)
        
        return result
        
    except HTTPException:
        # Re-raise HTTPExceptions (like 404) without wrapping them
        raise
    except Exception as e:
        logger.error(f"Feil ved beregning av decoupling for aktivitet {activity_id}: {e}")
        raise HTTPException(status_code=500, detail=f"En feil oppstod: {str(e)}")
