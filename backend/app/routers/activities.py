from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..dependencies import get_data_storage, get_garmin_client
from ..storage import DataStorage
from ..services.garmin_client import GarminClient
import plotly.graph_objects as go
import plotly.io as pio
import pandas as pd

router = APIRouter()

class ActivityResponse(BaseModel):
    activities: List[Dict[str, Any]]
    count: int

@router.get("/activities", response_model=ActivityResponse)
async def read_activities(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    storage: DataStorage = Depends(get_data_storage)
):
    """Henter lagrede aktiviteter, med valgfri filtrering på dato."""
    try:
        activities = storage.get_activities(start_date=start_date, end_date=end_date)
        return {"activities": activities, "count": len(activities)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
