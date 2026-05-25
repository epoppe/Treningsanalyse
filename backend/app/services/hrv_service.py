import logging
from datetime import datetime, date, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_
from ..database.models import HRV
from ..storage import DataStorage
import pandas as pd

logger = logging.getLogger(__name__)

class HRVService:
    def __init__(self, storage: DataStorage):
        self.storage = storage

    def sync_hrv_data_to_database(self, db: Session, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Synkroniserer HRV-data fra parquet-filer til databasen.
        
        Args:
            db: Database session
            start_date: Startdato for synkronisering (YYYY-MM-DD)
            end_date: Sluttdato for synkronisering (YYYY-MM-DD)
            
        Returns:
            Dict med resultater av synkroniseringen
        """
        try:
            # Hent HRV-data fra parquet-filer
            hrv_df = self.storage.get_hrv_data()
            if hrv_df is None or hrv_df.empty:
                logger.info("Ingen HRV-data funnet i parquet-filer")
                return {
                    "success": True,
                    "message": "Ingen HRV-data å synkronisere",
                    "synced_records": 0,
                    "skipped_records": 0
                }

            # Filtrer på dato hvis spesifisert
            if start_date:
                start_dt = pd.to_datetime(start_date).tz_localize('UTC')
                hrv_df = hrv_df[hrv_df.index >= start_dt]
            
            if end_date:
                end_dt = pd.to_datetime(end_date).tz_localize('UTC')
                hrv_df = hrv_df[hrv_df.index <= end_dt]

            if hrv_df.empty:
                logger.info("Ingen HRV-data i det spesifiserte datoperioden")
                return {
                    "success": True,
                    "message": "Ingen HRV-data i det spesifiserte datoperioden",
                    "synced_records": 0,
                    "skipped_records": 0
                }

            synced_count = 0
            skipped_count = 0

            # Gå gjennom hver rad i HRV-data
            for measurement_date, row in hrv_df.iterrows():
                try:
                    # Sjekk om HRV-data allerede eksisterer for denne datoen
                    existing_hrv = db.query(HRV).filter(
                        HRV.measurement_date == measurement_date.date()
                    ).first()

                    if existing_hrv:
                        # Oppdater eksisterende record
                        existing_hrv.rmssd = row.get('last_night_avg')
                        existing_hrv.measurement_time = measurement_date
                        existing_hrv.measurement_type = 'during_sleep'
                        existing_hrv.updated_at = datetime.now(timezone.utc)
                        skipped_count += 1
                    else:
                        # Opprett ny record
                        new_hrv = HRV(
                            measurement_date=measurement_date.date(),
                            measurement_time=measurement_date,
                            rmssd=row.get('last_night_avg'),
                            measurement_type='during_sleep',
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        db.add(new_hrv)
                        synced_count += 1

                except Exception as e:
                    logger.error(f"Feil ved synkronisering av HRV-data for {measurement_date}: {e}")
                    skipped_count += 1

            # Commit endringer
            db.commit()
            
            logger.info(f"HRV-synkronisering fullført: {synced_count} nye records, {skipped_count} oppdatert/skippet")
            
            return {
                "success": True,
                "message": f"HRV-data synkronisert til database",
                "synced_records": synced_count,
                "skipped_records": skipped_count,
                "total_records": len(hrv_df)
            }

        except Exception as e:
            logger.error(f"Feil ved HRV-synkronisering: {e}")
            db.rollback()
            return {
                "success": False,
                "message": f"Feil ved HRV-synkronisering: {str(e)}",
                "synced_records": 0,
                "skipped_records": 0
            }

    def get_hrv_for_activity_date(self, activity_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Henter HRV-data for datoen en spesifikk aktivitet ble utført fra databasen.
        
        Args:
            activity_id: Aktivitetens ID
            db: Database session
            
        Returns:
            HRV-data som dict eller None hvis ikke funnet
        """
        try:
            # Hent aktiviteten for å finne datoen
            from ..database.models import Activity
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                logger.warning(f"Aktivitet {activity_id} ikke funnet")
                return None

            activity_date = activity.start_time.date()

            # Sjekk om datoen er før 2023
            if activity_date.year < 2023:
                logger.info(f"HRV-data ikke tilgjengelig for datoen {activity_date} (før 2023)")
                return None

            # Hent HRV-data fra databasen
            hrv_record = db.query(HRV).filter(
                HRV.measurement_date == activity_date
            ).first()

            if not hrv_record:
                logger.info(f"Ingen HRV-data funnet for datoen {activity_date}")
                return None

            # Returner HRV-data som dict
            return {
                "date": activity_date.strftime('%Y-%m-%d'),
                "last_night_avg": hrv_record.rmssd,
                "measurement_time": hrv_record.measurement_time.isoformat() if hrv_record.measurement_time else None,
                "measurement_type": hrv_record.measurement_type
            }

        except Exception as e:
            logger.error(f"Feil ved henting av HRV-data for aktivitet {activity_id}: {e}")
            return None

    def get_hrv_over_time(self, db: Session, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Henter HRV-data over tid fra databasen med valgfri datofiltrering.
        Beregner også 7-dagers glidende gjennomsnitt.
        
        Args:
            db: Database session
            start_date: Startdato (YYYY-MM-DD)
            end_date: Sluttdato (YYYY-MM-DD)
            
        Returns:
            Dict med HRV-data og metadata
        """
        try:
            query = db.query(HRV)

            # Filtrer på dato hvis spesifisert
            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                query = query.filter(HRV.measurement_date >= start_dt)
            
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
                query = query.filter(HRV.measurement_date <= end_dt)

            # Sorter etter dato
            query = query.order_by(HRV.measurement_date)

            hrv_records = query.all()

            if not hrv_records:
                return {
                    "hrv_data": [],
                    "message": "Ingen HRV-data tilgjengelig for den spesifiserte perioden",
                    "total_records": 0
                }

            # Konverter til liste av dictionaries
            hrv_data = []
            for record in hrv_records:
                hrv_data.append({
                    "date": record.measurement_date.strftime('%Y-%m-%d'),
                    "last_night_avg": record.rmssd,
                    "measurement_time": record.measurement_time.isoformat() if record.measurement_time else None,
                    "measurement_type": record.measurement_type,
                    "created_at": record.created_at.isoformat() if record.created_at else None
                })

            # Beregn 7-dagers glidende gjennomsnitt
            if len(hrv_data) >= 7:
                for i in range(len(hrv_data)):
                    # Ta de siste 7 dagene (inkludert dag i)
                    start_idx = max(0, i - 6)
                    end_idx = i + 1
                    window_data = hrv_data[start_idx:end_idx]
                    
                    # Beregn gjennomsnitt for de 7 dagene
                    valid_values = [d['last_night_avg'] for d in window_data if d['last_night_avg'] is not None]
                    if len(valid_values) >= 4:  # Minimum 4 gyldige verdier for å beregne snitt
                        rolling_avg = sum(valid_values) / len(valid_values)
                        hrv_data[i]['rolling_avg_7d'] = round(rolling_avg, 1)
                    else:
                        hrv_data[i]['rolling_avg_7d'] = None
            else:
                # Hvis mindre enn 7 dager, sett rolling_avg_7d til None
                for data in hrv_data:
                    data['rolling_avg_7d'] = None

            # Legg til baseline-verdier (placeholder - kan utvides senere)
            for data in hrv_data:
                data['baseline_balanced_lower'] = 30.0  # Placeholder
                data['baseline_balanced_upper'] = 50.0  # Placeholder
                data['status'] = 'normal'  # Placeholder

            return {
                "hrv_data": hrv_data,
                "total_records": len(hrv_data)
            }

        except Exception as e:
            logger.error(f"Feil ved henting av HRV-data over tid: {e}")
            return {
                "hrv_data": [],
                "error": str(e),
                "total_records": 0
            }

    def get_hrv_statistics(self, db: Session) -> Dict[str, Any]:
        """
        Henter statistikk over HRV-data i databasen.
        
        Args:
            db: Database session
            
        Returns:
            Dict med HRV-statistikk
        """
        try:
            total_records = db.query(HRV).count()
            
            if total_records == 0:
                return {
                    "total_records": 0,
                    "date_range": None,
                    "average_hrv": None
                }

            # Hent datoområde
            first_record = db.query(HRV).order_by(HRV.measurement_date).first()
            last_record = db.query(HRV).order_by(HRV.measurement_date.desc()).first()

            # Beregn gjennomsnittlig HRV - bruk func.avg for å unngå multiple rows error
            from sqlalchemy import func
            avg_result = db.query(func.avg(HRV.rmssd)).filter(HRV.rmssd.isnot(None)).scalar()
            avg_hrv = float(avg_result) if avg_result is not None else None

            return {
                "total_records": total_records,
                "date_range": {
                    "start": first_record.measurement_date.strftime('%Y-%m-%d') if first_record else None,
                    "end": last_record.measurement_date.strftime('%Y-%m-%d') if last_record else None
                },
                "average_hrv": avg_hrv
            }

        except Exception as e:
            logger.error(f"Feil ved henting av HRV-statistikk: {e}")
            return {
                "total_records": 0,
                "error": str(e)
            } 
