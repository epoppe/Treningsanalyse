import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from ..database.models.body_battery import BodyBattery
from .garmin_client import GarminClient

logger = logging.getLogger(__name__)


class BodyBatteryService:
    def __init__(self, garmin_client: GarminClient):
        self.garmin_client = garmin_client
    
    async def sync_body_battery_data_to_database(self, db: Session, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Synkroniserer Body Battery-data fra Garmin til database
        """
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            logger.info(f"Synkroniserer Body Battery-data fra {start_date} til {end_date}")
            
            # Hent Body Battery-data fra Garmin
            body_battery_data = await self.garmin_client.get_body_battery_range(start_dt, end_dt)
            
            if not body_battery_data:
                logger.warning("Ingen Body Battery-data funnet fra Garmin")
                return {"message": "Ingen data funnet", "synced_records": 0}
            
            synced_count = 0
            updated_count = 0
            
            for day_data in body_battery_data:
                if not day_data or 'date' not in day_data:
                    continue
                
                try:
                    # Konverter dato
                    data_date = datetime.strptime(day_data['date'], '%Y-%m-%d').date()
                    
                    # Sjekk om data allerede eksisterer
                    existing_record = db.query(BodyBattery).filter(
                        BodyBattery.date == data_date
                    ).first()
                    
                    # Beregn høyeste og laveste verdier med flere mulige kilder
                    max_body_battery = day_data.get('max_body_battery')
                    min_body_battery = day_data.get('min_body_battery')

                    # Fallback fra starts
                    if max_body_battery is None and day_data.get('body_battery_charged_start') is not None:
                        max_body_battery = day_data['body_battery_charged_start']
                    if min_body_battery is None and day_data.get('body_battery_charged_start') is not None:
                        min_body_battery = day_data['body_battery_charged_start']
                    if day_data.get('body_battery_drained_start') is not None:
                        if max_body_battery is None or day_data['body_battery_drained_start'] > max_body_battery:
                            max_body_battery = day_data['body_battery_drained_start']
                        if min_body_battery is None or day_data['body_battery_drained_start'] < min_body_battery:
                            min_body_battery = day_data['body_battery_drained_start']

                    # Fallback fra arrays (garth DailyBodyBatteryStress eller raw bodyBattery)
                    values_array = day_data.get('body_battery_values_array') or day_data.get('values')
                    if (max_body_battery is None or min_body_battery is None) and isinstance(values_array, (list, tuple)) and len(values_array) > 0:
                        try:
                            numeric_vals = [v for v in values_array if isinstance(v, (int, float))]
                            if numeric_vals:
                                if max_body_battery is None:
                                    max_body_battery = max(numeric_vals)
                                if min_body_battery is None:
                                    min_body_battery = min(numeric_vals)
                        except Exception:
                            pass
                    
                    # Beregn netto opplading
                    net_charge = None
                    if day_data.get('body_battery_charged') is not None and day_data.get('body_battery_drained') is not None:
                        net_charge = (day_data['body_battery_charged'] or 0) - (day_data['body_battery_drained'] or 0)

                    # Hvis absolutt ingen nyttige verdier, hopp over lagring
                    has_any_value = any([
                        day_data.get('body_battery_charged') is not None,
                        day_data.get('body_battery_drained') is not None,
                        day_data.get('body_battery_charged_start') is not None,
                        day_data.get('body_battery_drained_start') is not None,
                        max_body_battery is not None,
                        min_body_battery is not None,
                        net_charge is not None,
                    ])
                    if not has_any_value:
                        logger.info(f"Hopper over Body Battery {data_date} (ingen nyttige verdier fra Garmin)")
                        continue
                    
                    if existing_record:
                        # Oppdater eksisterende record
                        existing_record.body_battery_charged = day_data.get('body_battery_charged')
                        existing_record.body_battery_drained = day_data.get('body_battery_drained')
                        existing_record.body_battery_charged_start = day_data.get('body_battery_charged_start')
                        existing_record.body_battery_drained_start = day_data.get('body_battery_drained_start')
                        existing_record.max_body_battery = max_body_battery
                        existing_record.min_body_battery = min_body_battery
                        existing_record.net_charge = net_charge
                        existing_record.device_name = day_data.get('device_name')
                        existing_record.updated_at = datetime.now()
                        updated_count += 1
                    else:
                        # Opprett ny record
                        new_record = BodyBattery(
                            date=data_date,
                            body_battery_charged=day_data.get('body_battery_charged'),
                            body_battery_drained=day_data.get('body_battery_drained'),
                            body_battery_charged_start=day_data.get('body_battery_charged_start'),
                            body_battery_drained_start=day_data.get('body_battery_drained_start'),
                            max_body_battery=max_body_battery,
                            min_body_battery=min_body_battery,
                            net_charge=net_charge,
                            device_name=day_data.get('device_name')
                        )
                        db.add(new_record)
                        synced_count += 1
                    
                except Exception as e:
                    logger.error(f"Feil ved synkronisering av Body Battery-data for {day_data.get('date', 'ukjent dato')}: {e}")
                    continue
            
            # Lagre endringene
            db.commit()
            
            logger.info(f"Body Battery-synkronisering fullført: {synced_count} nye, {updated_count} oppdatert")
            
            return {
                "message": "Body Battery-synkronisering fullført",
                "synced_records": synced_count,
                "updated_records": updated_count,
                "total_processed": len(body_battery_data)
            }
            
        except Exception as e:
            logger.error(f"Feil ved Body Battery-synkronisering: {e}")
            db.rollback()
            raise
    
    def get_body_battery_over_time(self, db: Session, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Henter Body Battery-data for en tidsperiode
        """
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Hent Body Battery-records
            body_battery_records = db.query(BodyBattery).filter(
                and_(
                    BodyBattery.date >= start_dt,
                    BodyBattery.date <= end_dt
                )
            ).order_by(BodyBattery.date).all()
            
            # Konverter til liste med dictionaries
            body_battery_data = []
            for record in body_battery_records:
                data = record.to_dict()
                body_battery_data.append(data)
            
            return {
                "body_battery_data": body_battery_data,
                "total_records": len(body_battery_data)
            }
            
        except Exception as e:
            logger.error(f"Feil ved henting av Body Battery-data: {e}")
            raise
    
    def get_body_battery_statistics(self, db: Session) -> Dict[str, Any]:
        """
        Henter statistikk for Body Battery-data
        """
        try:
            # Total antall records
            total_records = db.query(func.count(BodyBattery.id)).scalar()
            
            # Gjennomsnitt av høyeste Body Battery
            avg_max = db.query(func.avg(BodyBattery.max_body_battery)).filter(
                BodyBattery.max_body_battery.isnot(None)
            ).scalar()
            
            # Gjennomsnitt av laveste Body Battery
            avg_min = db.query(func.avg(BodyBattery.min_body_battery)).filter(
                BodyBattery.min_body_battery.isnot(None)
            ).scalar()
            
            # Høyeste Body Battery noensinne
            highest_ever = db.query(func.max(BodyBattery.max_body_battery)).scalar()
            
            # Laveste Body Battery noensinne
            lowest_ever = db.query(func.min(BodyBattery.min_body_battery)).scalar()
            
            return {
                "total_records": total_records or 0,
                "average_max_body_battery": round(avg_max, 1) if avg_max else None,
                "average_min_body_battery": round(avg_min, 1) if avg_min else None,
                "highest_body_battery_ever": highest_ever,
                "lowest_body_battery_ever": lowest_ever
            }
            
        except Exception as e:
            logger.error(f"Feil ved henting av Body Battery-statistikk: {e}")
            raise 