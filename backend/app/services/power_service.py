import math
import polars as pl
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session, selectinload
from ..storage import DataStorage
from ..database.models.activity import Activity
from ..utils.activity_filters import is_running_activity
from ..cache.cache_manager import get_cache_manager
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class PowerService:
    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.cache = get_cache_manager()
        
        # Konstant parametere for power-beregning
        self.MASS = 75.0  # kg (løper + sko/utstyr)
        self.RHO = 1.226  # lufttetthet (kg/m³)
        self.CDA = 0.24   # aerodynamisk koeffisient
        self.G = 9.81     # gravitasjon

    def running_power(self, mass_kg: float, speed_mps: float, prev_speed_mps: float, 
                     slope_percent: float, vo_cm: float, gct_ms: float, wind_mps: float = 0) -> float:
        """
        Beregner løpekraft for et enkelt datapunkt basert på Garmin Connect IQ-modell.
        Justert basert på reverse-engineered Garmin CIQ-koder.
        
        Args:
            mass_kg: Løperens masse i kg
            speed_mps: Nåværende hastighet i m/s
            prev_speed_mps: Forrige hastighet i m/s
            slope_percent: Stigning i prosent
            vo_cm: Vertikal oscillasjon i cm
            gct_ms: Ground contact time i ms
            wind_mps: Vindhastighet i m/s (standard: 0)
            
        Returns:
            Power i Watt
        """
        # Basert på reverse-engineered Garmin Connect IQ power-beregning
        
        # 1. GRUNNLEGGENDE LØPEPOWER (basert på hastighet)
        # Garmin bruker 4.0-4.1 W/kg ved 3.0 m/s på flat mark
        base_power_per_kg = 4.05  # Økt fra 3.5 til 4.05 W/kg for å matche Garmin
        speed_factor = (speed_mps / 3.0) ** 2  # Kvadratisk forhold til hastighet
        base_power = mass_kg * base_power_per_kg * speed_factor
        
        # 2. JUSTERING FOR STIGNING (asymmetrisk som Garmin)
        # Garmin er mer aggressiv oppover (0.18-0.20) og demper raskere nedover (0.10)
        if slope_percent >= 0:
            grade_factor = 1.0 + slope_percent * 0.19  # Økt fra 0.15 til 0.19 for oppover
        else:
            grade_factor = 1.0 + slope_percent * 0.10  # Redusert fra 0.15 til 0.10 for nedover
        
        # 3. JUSTERING FOR LØPEFORM (diskret som Garmin)
        form_factor = 1.0
        if vo_cm > 0 and gct_ms > 0:
            # Optimal løpeform: VO ~6-8cm, GCT ~200-250ms
            optimal_vo = 7.0  # cm
            optimal_gct = 225.0  # ms
            
            # Diskret justering som Garmin - små avvik straffes ikke
            vo_dev = abs(vo_cm - optimal_vo)
            gct_dev = abs(gct_ms - optimal_gct)
            
            # VO: Ingen straff hvis avvik < 1.0cm
            vo_factor = 1.0 if vo_dev < 1.0 else 1.0 + (vo_dev / optimal_vo) * 0.10
            
            # GCT: Ingen straff hvis avvik < 15ms
            gct_factor = 1.0 if gct_dev < 15 else 1.0 + (gct_dev / optimal_gct) * 0.10
            
            form_factor = vo_factor * gct_factor
        
        # 4. AKSELERASJON (større utslag som Garmin)
        accel_factor = 1.0
        if abs(speed_mps - prev_speed_mps) > 0.1:  # Mer enn 0.1 m/s endring
            # Garmin bruker sterkere akselerasjonsfaktor for spurter
            accel_factor = 1.0 + abs(speed_mps - prev_speed_mps) * 1.5  # Økt fra 1.1 til 1.5 for spurter
        
        # 5. LUFTMOTSTAND (redusert CdA som Garmin)
        air_resistance = 0.0
        if speed_mps > 3.0:  # Luftmotstand blir viktig over 10.8 km/h
            # Garmin bruker CdA = 0.28 (redusert fra 0.5)
            air_resistance = 0.5 * 1.225 * 0.28 * (speed_mps ** 3)
        
        # 6. TOTAL POWER
        total_power = base_power * grade_factor * form_factor * accel_factor + air_resistance
        
        # Garmin lar verdien falle lavere på nedoverbakker
        return max(total_power, 60.0)  # Redusert minimum fra 80W til 60W

    def calculate_activity_power(self, activity_id: int, db: Session, mass_kg: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Beregner power for en løpeaktivitet basert på FIT-data.
        
        Args:
            activity_id: Aktivitetens ID
            db: Database session
            mass_kg: Løperens masse (bruker standard hvis ikke spesifisert)
            
        Returns:
            Dictionary med power-statistikk
        """
        try:
            # Sjekk cache først
            cached_power = self.cache.get_power(str(activity_id))
            if cached_power is not None:
                logger.debug(f"Power cache hit for activity {activity_id}")
                return cached_power
            
            # Hent aktivitet fra database
            activity = (
                db.query(Activity)
                .options(selectinload(Activity.activity_type))
                .filter(Activity.activity_id == str(activity_id))
                .first()
            )
            if not activity:
                logger.warning(f"Aktivitet {activity_id} ikke funnet i database")
                return None
            
            if not is_running_activity(activity):
                type_key = activity.activity_type.type_key if activity.activity_type else None
                logger.info(f"Aktivitet {activity_id} er ikke en utendørs løpeaktivitet: {type_key}")
                return None
            
            # Bruk standard masse hvis ikke spesifisert
            if mass_kg is None:
                mass_kg = self.MASS
            
            # Hent FIT-data
            details_df = self.storage.get_activity_details(activity_id)
            if details_df is None or details_df.empty:
                logger.warning(f"Ingen FIT-data tilgjengelig for aktivitet {activity_id}")
                raise HTTPException(status_code=404, detail="No FIT data available for this activity")
            
            # Sjekk at vi har nødvendige kolonner
            required_columns = ['speed', 'timestamp']
            if not all(col in details_df.columns for col in required_columns):
                logger.warning(f"Mangler nødvendige kolonner for power-beregning: {required_columns}")
                raise HTTPException(status_code=404, detail="Missing required data columns for power calculation")
            
            # Konverter til Polars hvis det er pandas (for kompatibilitet)
            if hasattr(details_df, 'to_dict'):  # pandas DataFrame
                details_df = pl.from_pandas(details_df)
            
            # Filtrer ut rader med gyldig speed og timestamp data
            valid_data = details_df.filter(
                (pl.col('speed').is_not_null()) &
                (pl.col('timestamp').is_not_null()) &
                (pl.col('speed') > 0)
            )
            
            if len(valid_data) < 10:
                logger.warning(f"Ikke nok datapunkter for power-beregning: {len(valid_data)}")
                raise HTTPException(status_code=404, detail="Insufficient data points for power calculation")
            
            # Sorter etter timestamp
            valid_data = valid_data.sort('timestamp')
            
            # Beregn power for hvert datapunkt
            power_values = []
            prev_speed = 0.0
            
            for row in valid_data.iter_rows(named=True):
                speed = row['speed']
                grade = row.get('grade', 0.0) if row.get('grade') is not None else 0.0
                vo = row.get('vertical_oscillation', 0.0) if row.get('vertical_oscillation') is not None else 0.0
                gct = row.get('stance_time', 0.0) if row.get('stance_time') is not None else 0.0
                
                power = self.running_power(mass_kg, speed, prev_speed, grade, vo, gct)
                power_values.append(power)
                prev_speed = speed
            
            if not power_values:
                logger.warning(f"Ingen gyldige power-verdier beregnet for aktivitet {activity_id}")
                return None
            
            # Beregn statistikk
            avg_power = sum(power_values) / len(power_values)
            max_power = max(power_values)
            min_power = min(power_values)
            
            # Beregn power zones (basert på gjennomsnittlig power)
            power_zones = self._calculate_power_zones(power_values, avg_power)
            
            # Lagre i database hvis vi har en power-kolonne
            # TODO: Legg til power-kolonne i Activity-modellen hvis nødvendig
            
            # Lagre power-verdier i databasen
            try:
                activity.average_power = round(avg_power, 1)
                activity.max_power = round(max_power, 1)
                activity.normalized_power = round(avg_power, 1)  # For løping er normalized power ofte lik average power
                db.commit()
                logger.info(f"Lagret power-verdier i database for aktivitet {activity_id}")
            except Exception as e:
                logger.error(f"Kunne ikke lagre power-verdier i database for aktivitet {activity_id}: {e}")
                db.rollback()
            
            logger.info(f"Beregnet power for aktivitet {activity_id}: avg={avg_power:.1f}W, max={max_power:.1f}W")
            
            result = {
                "activity_id": activity_id,
                "average_power_watts": round(avg_power, 1),
                "max_power_watts": round(max_power, 1),
                "min_power_watts": round(min_power, 1),
                "power_zones": power_zones,
                "data_points": len(power_values),
                "mass_kg": mass_kg,
                "calculation_method": "calculated"
            }
            
            # Cache resultatet
            self.cache.set_power(str(activity_id), result)
            
            return result
            
        except HTTPException:
            # Re-raise HTTPExceptions without logging them as errors
            raise
        except Exception as e:
            logger.error(f"Feil ved beregning av power for aktivitet {activity_id}: {e}")
            return None

    def _calculate_power_zones(self, power_values: List[float], avg_power: float) -> Dict[str, Any]:
        """
        Beregner power zones basert på gjennomsnittlig power.
        
        Args:
            power_values: Liste med power-verdier
            avg_power: Gjennomsnittlig power
            
        Returns:
            Dictionary med power zone statistikk
        """
        # Definer power zones (kan justeres etter behov)
        zone_thresholds = {
            "zone1": avg_power * 0.7,  # < 70% av avg
            "zone2": avg_power * 0.85, # 70-85% av avg
            "zone3": avg_power * 1.0,  # 85-100% av avg
            "zone4": avg_power * 1.15, # 100-115% av avg
            "zone5": avg_power * 1.3   # > 115% av avg
        }
        
        zone_counts = {
            "zone1": 0, "zone2": 0, "zone3": 0, "zone4": 0, "zone5": 0
        }
        
        for power in power_values:
            if power < zone_thresholds["zone1"]:
                zone_counts["zone1"] += 1
            elif power < zone_thresholds["zone2"]:
                zone_counts["zone2"] += 1
            elif power < zone_thresholds["zone3"]:
                zone_counts["zone3"] += 1
            elif power < zone_thresholds["zone4"]:
                zone_counts["zone4"] += 1
            else:
                zone_counts["zone5"] += 1
        
        total_points = len(power_values)
        zone_percentages = {
            zone: round((count / total_points) * 100, 1) 
            for zone, count in zone_counts.items()
        }
        
        return {
            "thresholds": {zone: round(threshold, 1) for zone, threshold in zone_thresholds.items()},
            "counts": zone_counts,
            "percentages": zone_percentages
        }

    def calculate_power_for_period(self, start_date: str, end_date: str, db: Session, 
                                 mass_kg: Optional[float] = None) -> Dict[str, Any]:
        """
        Beregner power-statistikk for alle løpeaktiviteter i en periode.
        
        Args:
            start_date: Startdato (YYYY-MM-DD)
            end_date: Sluttdato (YYYY-MM-DD)
            db: Database session
            mass_kg: Løperens masse
            
        Returns:
            Dictionary med power-statistikk for perioden
        """
        try:
            # Hent alle løpeaktiviteter i perioden
            activities = db.query(Activity).filter(
                Activity.activity_type == 'running',
                Activity.date >= start_date,
                Activity.date <= end_date
            ).all()
            
            if not activities:
                return {
                    "period": f"{start_date} til {end_date}",
                    "activities_analyzed": 0,
                    "total_activities": 0,
                    "average_power_watts": 0,
                    "max_power_watts": 0,
                    "min_power_watts": 0
                }
            
            power_results = []
            successful_activities = 0
            
            for activity in activities:
                power_result = self.calculate_activity_power(int(activity.activity_id), db, mass_kg)
                if power_result:
                    power_results.append(power_result)
                    successful_activities += 1
            
            if not power_results:
                return {
                    "period": f"{start_date} til {end_date}",
                    "activities_analyzed": 0,
                    "total_activities": len(activities),
                    "average_power_watts": 0,
                    "max_power_watts": 0,
                    "min_power_watts": 0
                }
            
            # Beregn periodestatistikk
            avg_powers = [result["average_power_watts"] for result in power_results]
            max_powers = [result["max_power_watts"] for result in power_results]
            
            period_avg_power = sum(avg_powers) / len(avg_powers)
            period_max_power = max(max_powers)
            period_min_power = min(avg_powers)
            
            return {
                "period": f"{start_date} til {end_date}",
                "activities_analyzed": successful_activities,
                "total_activities": len(activities),
                "average_power_watts": round(period_avg_power, 1),
                "max_power_watts": round(period_max_power, 1),
                "min_power_watts": round(period_min_power, 1),
                "activities": power_results
            }
            
        except Exception as e:
            logger.error(f"Feil ved beregning av power for periode {start_date} til {end_date}: {e}")
            return None