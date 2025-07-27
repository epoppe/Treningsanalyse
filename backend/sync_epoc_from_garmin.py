#!/usr/bin/env python3
"""
Script for å synkronisere korrekte EPOC-verdier fra Garmin Connect
for aktiviteter fra 1. juni 2025 og bakover
"""

import os
import sys
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import and_

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.services.garmin_client import GarminClient
from app.config import settings
import logging

# Konfigurer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EPOCSyncService:
    def __init__(self):
        self.garmin_client = GarminClient(
            email=settings.GARMIN_EMAIL,
            password=settings.GARMIN_PASSWORD,
            token_dir=settings.TOKEN_DIR
        )
    
    async def initialize(self):
        """Initialiserer Garmin-klienten"""
        print("🔐 Initialiserer Garmin-klient...")
        
        if not await self.garmin_client.initialize():
            print("❌ Kunne ikke autentisere med Garmin Connect")
            return False
        
        print("✅ Autentisert med Garmin Connect")
        return True
    
    async def get_activity_epoc_from_garmin(self, activity_id: str, start_time: datetime) -> float:
        """
        Henter EPOC-verdi for en spesifikk aktivitet fra Garmin Connect
        """
        try:
            # Hent Training Effect data fra Garmin Connect (som inkluderer EPOC)
            training_effect_data = await self.garmin_client.get_activity_training_effect(activity_id)
            
            if training_effect_data and 'training_load' in training_effect_data:
                epoc_value = training_effect_data['training_load']
                if epoc_value and epoc_value > 0:
                    logger.info(f"EPOC hentet fra Garmin for aktivitet {activity_id}: {epoc_value}")
                    return epoc_value
                else:
                    logger.warning(f"EPOC-verdi er 0 eller null for aktivitet {activity_id}")
                    return None
            else:
                logger.warning(f"Ingen EPOC-data funnet for aktivitet {activity_id}")
                return None
                
        except Exception as e:
            logger.error(f"Feil ved henting av EPOC for aktivitet {activity_id}: {e}")
            return None
    
    async def sync_epoc_for_activities(self, start_date: datetime, end_date: datetime):
        """
        Synkroniserer EPOC-verdier for aktiviteter i den spesifiserte perioden
        """
        print(f"🔄 Starter EPOC-synkronisering for perioden {start_date.strftime('%Y-%m-%d')} til {end_date.strftime('%Y-%m-%d')}")
        
        db = SessionLocal()
        
        try:
            # Hent aktiviteter i perioden
            activities = db.query(Activity).filter(
                and_(
                    Activity.start_time >= start_date,
                    Activity.start_time <= end_date
                )
            ).order_by(Activity.start_time.desc()).all()
            
            print(f"📊 Fant {len(activities)} aktiviteter å synkronisere EPOC for")
            
            if not activities:
                print("✅ Ingen aktiviteter å synkronisere")
                return
            
            # Grupper aktiviteter etter år for bedre oversikt
            activities_by_year = {}
            for activity in activities:
                year = activity.start_time.year
                if year not in activities_by_year:
                    activities_by_year[year] = []
                activities_by_year[year].append(activity)
            
            print(f"\n📅 Aktivitetene fordelt på år:")
            for year in sorted(activities_by_year.keys(), reverse=True):
                print(f"   {year}: {len(activities_by_year[year])} aktiviteter")
            
            # Synkroniser EPOC for hver aktivitet
            updated_count = 0
            failed_count = 0
            skipped_count = 0
            
            for year in sorted(activities_by_year.keys(), reverse=True):
                year_activities = activities_by_year[year]
                print(f"\n🔢 Prosesserer {year} ({len(year_activities)} aktiviteter)")
                
                for i, activity in enumerate(year_activities, 1):
                    try:
                        # Hent EPOC fra Garmin
                        epoc_from_garmin = await self.get_activity_epoc_from_garmin(
                            activity.activity_id, 
                            activity.start_time
                        )
                        
                        if epoc_from_garmin is not None:
                            # Oppdater aktiviteten
                            old_epoc = activity.epoc
                            activity.epoc = epoc_from_garmin
                            
                            # Vis fremdrift hver 10. aktivitet
                            if i % 10 == 0 or i == len(year_activities):
                                print(f"   {i:3d}/{len(year_activities)}: {activity.activity_name[:30]}... - EPOC: {old_epoc} → {epoc_from_garmin}")
                            
                            updated_count += 1
                        else:
                            skipped_count += 1
                            if i % 10 == 0 or i == len(year_activities):
                                print(f"   {i:3d}/{len(year_activities)}: {activity.activity_name[:30]}... - Ingen EPOC-data fra Garmin")
                        
                    except Exception as e:
                        logger.error(f"Feil ved prosessering av aktivitet {activity.activity_id}: {e}")
                        failed_count += 1
                        continue
                
                # Lagre endringer for hvert år
                print(f"   💾 Lagrer endringer for {year}...")
                db.commit()
            
            print(f"\n✅ EPOC-synkronisering fullført!")
            print(f"   Oppdatert: {updated_count} aktiviteter")
            print(f"   Hoppet over: {skipped_count} aktiviteter (ingen EPOC-data)")
            print(f"   Feilet: {failed_count} aktiviteter")
            print(f"   Total prosessert: {len(activities)} aktiviteter")
            
            # Vis sammendrag av oppdaterte EPOC-verdier
            if updated_count > 0:
                print(f"\n📊 SAMMENDRAG AV OPPDATERTE EPOC-VERDIER:")
                
                # Hent noen eksempler på oppdaterte EPOC-verdier
                sample_activities = db.query(Activity).filter(
                    and_(
                        Activity.start_time >= start_date,
                        Activity.start_time <= end_date,
                        Activity.epoc.isnot(None),
                        Activity.epoc > 0
                    )
                ).order_by(Activity.start_time.desc()).limit(10).all()
                
                for activity in sample_activities:
                    print(f"  {activity.start_time.strftime('%Y-%m-%d')}: {activity.activity_name[:40]}... - EPOC: {activity.epoc}")
            
        except Exception as e:
            print(f"❌ Feil under EPOC-synkronisering: {e}")
            db.rollback()
            raise
        finally:
            db.close()

async def main():
    """Hovedfunksjon for EPOC-synkronisering"""
    
    print("🔄 EPOC-synkronisering fra Garmin Connect")
    print("📅 Periode: 1. juni 2025 og bakover")
    
    # Opprett synkroniseringsservice
    sync_service = EPOCSyncService()
    
    # Initialiser Garmin-klient
    if not await sync_service.initialize():
        print("❌ Kunne ikke initialisere Garmin-klient")
        return
    
    # Definer datogrenser
    end_date = datetime(2025, 6, 1)  # 1. juni 2025
    start_date = datetime(2021, 1, 1)  # Januar 2021 (eller tidligere hvis ønskelig)
    
    # Start synkronisering
    await sync_service.sync_epoc_for_activities(start_date, end_date)
    
    print("\n🎉 EPOC-synkronisering fullført!")

if __name__ == "__main__":
    asyncio.run(main()) 