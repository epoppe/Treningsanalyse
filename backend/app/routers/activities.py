from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..dependencies import get_db
from ..database.models.activity import Activity
from ..services.garmin_client import GarminClient
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

@router.get("", response_model=List[ActivityResponse])
def get_activities(db: Session = Depends(get_db)):
    """
    Retrieve all activities from the database, and format them for the API response.
    """
    try:
        logger.info("Henter aktiviteter fra databasen...")
        # Eager load the related activity_type to avoid N+1 query problem
        activities = db.query(Activity).options(joinedload(Activity.activity_type)).order_by(Activity.start_time.desc()).all()
        logger.info(f"Hentet {len(activities)} aktiviteter fra databasen")
        
        response_data = []
        for act in activities:
            # Construct the nested activity type object
            act_type_data = None
            if act.activity_type:
                act_type_data = {
                    "typeKey": act.activity_type.type_key,
                    "parentTypeKey": act.activity_type.parent_type_key
                }
            elif act.type:
                 # Fallback to the 'type' column if the relationship is not set
                act_type_data = {"typeKey": act.type}

            # Calculate average stride length
            avg_stride_length = None
            if act.average_speed and act.average_running_cadence and act.average_running_cadence > 0:
                # average_speed is in m/s, cadence is in steps/min.
                # Convert speed to m/min: average_speed * 60
                # Stride length (m/step) = (m/min) / (steps/min)
                avg_stride_length = (act.average_speed * 60) / act.average_running_cadence

            # Manually construct the dictionary for the response, ensuring correct field names
            response_data.append({
                "activityId": act.id,
                "activityName": act.name,
                "startTimeLocal": act.start_time,
                "distance": act.distance,
                "duration": act.duration,
                "calories": act.calories,
                "averageHR": act.average_hr,
                "averageSpeed": act.average_speed,
                "averagePace": act.average_pace,
                "averageRunningCadenceInStepsPerMinute": act.average_running_cadence,
                "vO2MaxValue": act.vo2_max,
                "activityType": act_type_data,
                "avgStrideLength": avg_stride_length
            })

        logger.info(f"Returnerer {len(response_data)} aktiviteter til frontend")
        return response_data
    except Exception as e:
        import traceback
        traceback.print_exc() # This will print the error to the backend console
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.get("/{activity_id}/details", response_model=List[Dict[str, Any]])
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
        if details:
            return details

        # 2. Hvis ikke lokalt, hent fra Garmin
        fit_data = await garmin_client.get_activity_details(str(activity_id))
        if not fit_data:
            raise HTTPException(status_code=404, detail="Kunne ikke hente aktivitetsdetaljer fra Garmin.")

        # 3. Lagre dataene lokalt
        storage.save_activity_details(activity_id, fit_data)

        # 4. Hent og returner de nylig lagrede dataene
        new_details = storage.get_activity_details(activity_id)
        if new_details:
            return new_details
        else:
            # Dette skal i teorien ikke skje hvis lagring var vellykket
            raise HTTPException(status_code=500, detail="Klarte ikke å hente data etter lagring.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"En feil oppstod: {str(e)}")

@router.get("/{activity_id}/charts/{chart_type}")
def get_activity_chart(
    activity_id: int, 
    chart_type: str, 
    storage: DataStorage = Depends(get_data_storage)
):
    """
    Generate and return a Plotly chart for a given activity and chart type.
    """
    details_list = storage.get_activity_details(activity_id)
    if not details_list:
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

@router.get("/{activity_id}/negative-split")
def get_activity_negative_split(
    activity_id: int, 
    storage: DataStorage = Depends(get_data_storage)
):
    """
    Beregner negativ split for en aktivitet basert på lagrede FIT-data fra parquet-filen.
    Negativ split = (gjennomsnittlig pace første halvdel - gjennomsnittlig pace andre halvdel) / gjennomsnittlig pace første halvdel * 100
    Positiv verdi = negativ split (raskere andre halvdel)
    Negativ verdi = positiv split (saktere andre halvdel)
    """
    details_df = storage.get_activity_details(activity_id)
    if details_df is None or details_df.empty:
        raise HTTPException(status_code=404, detail="Activity details not found")

    # Filtrer ut rader med gyldig speed og timestamp data
    valid_data = details_df.dropna(subset=['speed', 'timestamp'])
    
    if len(valid_data) < 10:  # Trenger minimum 10 datapunkter for å beregne negativ split
        raise HTTPException(status_code=404, detail="Insufficient data points for negative split calculation")
        
    # Sorter etter timestamp
    valid_data = valid_data.sort_values('timestamp')
    
    # Del i to halvdeler
    midpoint = len(valid_data) // 2
    first_half = valid_data.iloc[:midpoint]
    second_half = valid_data.iloc[midpoint:]
    
    # Beregn gjennomsnittlig speed for hver halvdel (ignorer 0-verdier)
    first_half_speed = first_half[first_half['speed'] > 0]['speed'].mean()
    second_half_speed = second_half[second_half['speed'] > 0]['speed'].mean()
    
    if pd.isna(first_half_speed) or pd.isna(second_half_speed) or first_half_speed == 0:
        raise HTTPException(status_code=404, detail="Invalid speed data for negative split calculation")
    
    # Konverter speed (antatt m/s) til pace (min/km)
    # pace = 1000 / (speed * 60) for å få min/km
    first_half_pace = 1000 / (first_half_speed * 60)
    second_half_pace = 1000 / (second_half_speed * 60)
    
    # Beregn negativ split som prosentvis forbedring (invertert fra opprinnelig decoupling)
    # Positiv verdi = negativ split (raskere andre halvdel)
    # Negativ verdi = positiv split (saktere andre halvdel)
    negative_split_percent = ((first_half_pace - second_half_pace) / first_half_pace) * 100
    
    return {
        "activity_id": activity_id,
        "negative_split_percent": round(negative_split_percent, 2),
        "first_half_pace": round(first_half_pace, 2),
        "second_half_pace": round(second_half_pace, 2),
        "data_points": len(valid_data),
        "first_half_points": len(first_half),
        "second_half_points": len(second_half)
    }
