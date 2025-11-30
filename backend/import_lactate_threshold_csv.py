#!/usr/bin/env python3
"""
Importerer lactate threshold verdier fra CSV-fil og oppdaterer alle løpeaktiviteter i databasen.
Dette er en engangsinnlasting som erstatter alle eksisterende verdier.
"""

import sys
import os
import csv
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional

sys.path.append(str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.database.models.activity import Activity, ActivityType
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_pace_to_mps(pace_str: str) -> Optional[float]:
    """
    Konverterer tempo fra format "5:45 /km" til m/s.
    
    Args:
        pace_str: Tempo i format "5:45 /km" eller lignende
        
    Returns:
        Hastighet i m/s, eller None hvis parsing feiler
    """
    try:
        # Fjern whitespace og "/km" delen
        pace_str = pace_str.strip().replace("/km", "").replace(" ", "")
        
        # Split på kolon
        parts = pace_str.split(":")
        if len(parts) != 2:
            logger.warning(f"Uventet tempo-format: {pace_str}")
            return None
            
        minutes = int(parts[0])
        seconds = int(parts[1])
        
        # Konverter til sekunder per km
        total_seconds_per_km = minutes * 60 + seconds
        
        # Konverter til m/s: 1000 meter / sekunder per km
        speed_mps = 1000.0 / total_seconds_per_km
        
        return speed_mps
    except Exception as e:
        logger.error(f"Feil ved parsing av tempo {pace_str}: {e}")
        return None


def read_lactate_threshold_csv(csv_path: str) -> Dict[date, float]:
    """
    Leser CSV-fil med lactate threshold verdier.
    
    Args:
        csv_path: Sti til CSV-filen
        
    Returns:
        Dictionary med dato -> lactate threshold speed (m/s)
    """
    threshold_data = {}
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            # Finn hvor hastighet-dataene starter (første rad med "Verdi,Tempo")
            speed_section_start = None
            for i, row in enumerate(rows):
                if len(row) >= 3 and row[1] == "Verdi" and row[2] == "Tempo":
                    speed_section_start = i + 1
                    break
            
            if speed_section_start is None:
                logger.error("Kunne ikke finne hastighet-seksjonen i CSV-filen")
                return threshold_data
            
            # Les hastighet-dataene (før puls-seksjonen starter)
            for i in range(speed_section_start, len(rows)):
                row = rows[i]
                
                # Stopp når vi kommer til puls-seksjonen
                if len(row) >= 3 and row[1] == "Verdi" and row[2] == "bpm":
                    break
                
                # Hopp over tomme rader
                if len(row) < 3 or not row[0] or not row[2]:
                    continue
                
                try:
                    # Parse dato
                    threshold_date = datetime.strptime(row[0], "%Y-%m-%d").date()
                    
                    # Parse tempo
                    pace_str = row[2]
                    speed_mps = parse_pace_to_mps(pace_str)
                    
                    if speed_mps is not None:
                        threshold_data[threshold_date] = speed_mps
                        logger.info(f"Lest: {threshold_date} -> {speed_mps:.4f} m/s ({pace_str})")
                    else:
                        logger.warning(f"Kunne ikke parse tempo for {threshold_date}: {pace_str}")
                        
                except ValueError as e:
                    logger.warning(f"Kunne ikke parse rad {i+1}: {row} - {e}")
                    continue
            
            logger.info(f"Totalt lest {len(threshold_data)} lactate threshold verdier fra CSV")
            
    except Exception as e:
        logger.error(f"Feil ved lesing av CSV-fil: {e}")
        raise
    
    return threshold_data


def get_lactate_threshold_for_date(threshold_data: Dict[date, float], activity_date: date) -> Optional[float]:
    """
    Finner riktig lactate threshold verdi for en gitt dato.
    Bruker den siste verdien før eller på aktivitetens dato.
    
    Args:
        threshold_data: Dictionary med dato -> lactate threshold speed
        activity_date: Datoen for aktiviteten
        
    Returns:
        Lactate threshold speed i m/s, eller None hvis ingen verdi finnes
    """
    # Sorter datoene i stigende rekkefølge
    sorted_dates = sorted(threshold_data.keys())
    
    # Finn den siste verdien som er på eller før aktivitetens dato
    threshold_value = None
    for threshold_date in sorted_dates:
        if threshold_date <= activity_date:
            threshold_value = threshold_data[threshold_date]
        else:
            break
    
    return threshold_value


def import_lactate_threshold_values(csv_path: str):
    """
    Importerer lactate threshold verdier fra CSV og oppdaterer alle løpeaktiviteter.
    
    Args:
        csv_path: Sti til CSV-filen
    """
    db = SessionLocal()
    
    try:
        # Les CSV-filen
        logger.info(f"Leser lactate threshold verdier fra {csv_path}...")
        threshold_data = read_lactate_threshold_csv(csv_path)
        
        if not threshold_data:
            logger.error("Ingen lactate threshold verdier funnet i CSV-filen")
            return
        
        # Hent alle løpeaktiviteter
        logger.info("Henter alle løpeaktiviteter fra databasen...")
        running_types = db.query(ActivityType).filter(
            ActivityType.type_key.in_(['running', 'treadmill_running'])
        ).all()
        
        running_type_ids = [at.id for at in running_types]
        
        running_activities = db.query(Activity).filter(
            Activity.activity_type_id.in_(running_type_ids)
        ).all()
        
        logger.info(f"Fant {len(running_activities)} løpeaktiviteter")
        
        if not running_activities:
            logger.warning("Ingen løpeaktiviteter funnet i databasen")
            return
        
        # Oppdater alle aktiviteter
        updated_count = 0
        skipped_count = 0
        
        for activity in running_activities:
            if not activity.start_time:
                skipped_count += 1
                continue
            
            activity_date = activity.start_time.date()
            threshold_value = get_lactate_threshold_for_date(threshold_data, activity_date)
            
            if threshold_value is None:
                logger.warning(f"Ingen lactate threshold verdi funnet for aktivitet {activity.activity_id} (dato: {activity_date})")
                skipped_count += 1
                continue
            
            # Oppdater aktiviteten (erstatter eksisterende verdi)
            old_value = activity.lactate_threshold_speed
            activity.lactate_threshold_speed = threshold_value
            
            if old_value != threshold_value:
                logger.debug(
                    f"Oppdatert aktivitet {activity.activity_id} ({activity_date}): "
                    f"{old_value} -> {threshold_value:.4f} m/s"
                )
                updated_count += 1
        
        # Commit endringene
        db.commit()
        
        logger.info(f"✅ Ferdig! Oppdatert {updated_count} aktiviteter med lactate threshold verdier")
        logger.info(f"   Hoppet over {skipped_count} aktiviteter (mangler dato eller verdi)")
        
        # Verifiser endringene
        activities_with_threshold = db.query(Activity).filter(
            Activity.activity_type_id.in_(running_type_ids),
            Activity.lactate_threshold_speed.isnot(None)
        ).count()
        
        logger.info(f"   Totalt {activities_with_threshold} løpeaktiviteter har nå lactate threshold verdi")
        
    except Exception as e:
        logger.error(f"Feil ved import av lactate threshold verdier: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Importerer lactate threshold verdier fra CSV-fil")
    parser.add_argument(
        "csv_path",
        type=str,
        help="Sti til CSV-filen med lactate threshold verdier"
    )
    
    args = parser.parse_args()
    
    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        logger.error(f"CSV-fil ikke funnet: {csv_path}")
        sys.exit(1)
    
    logger.info("🚀 Starter import av lactate threshold verdier...")
    logger.info(f"📁 CSV-fil: {csv_path}")
    
    import_lactate_threshold_values(str(csv_path))
    
    logger.info("✅ Import fullført!")

