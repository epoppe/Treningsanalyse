#!/usr/bin/env python3
"""
Script for å hente EPOC-data fra Garmin og oppdatere databasen
"""

import asyncio
from datetime import datetime, timedelta
from app.services.garmin_client import GarminClient
from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.config import settings
from sqlalchemy import desc

async def update_epoc_data():
    """Henter EPOC-data fra Garmin og oppdaterer databasen"""
    
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    
    db = SessionLocal()
    
    try:
        # Initialiser Garmin-klient
        if not await garmin_client.initialize():
            print("❌ Kunne ikke autentisere med Garmin")
            return
        
        print("✅ Autentisert med Garmin")
        
        # Hent de 20 nyeste aktivitetene som ikke har EPOC-data
        print("🔍 Henter aktiviteter uten EPOC-data...")
        activities = db.query(Activity).filter(
            Activity.epoc.is_(None)
        ).order_by(desc(Activity.start_time)).limit(20).all()
        
        print(f"📊 Fant {len(activities)} aktiviteter å oppdatere")
        
        updated_count = 0
        failed_count = 0
        
        for i, activity in enumerate(activities, 1):
            activity_id = activity.activity_id
            print(f"\n{i:2d}. Prosesserer aktivitet {activity_id} - {activity.activity_name}")
            print(f"    Start: {activity.start_time}")
            
            try:
                # Hent EPOC-data fra Garmin
                epoc_data = await garmin_client.get_activity_epoc_data(activity_id)
                
                if epoc_data and epoc_data.get('activity_training_load') is not None:
                    # Oppdater databasen
                    activity.epoc = epoc_data['activity_training_load']
                    
                    print(f"    ✅ Oppdatert: EPOC={activity.epoc}")
                    
                    if epoc_data.get('training_effect_label'):
                        print(f"    🏷️  Training Effect: {epoc_data['training_effect_label']}")
                    
                    updated_count += 1
                else:
                    print(f"    ❌ Ingen EPOC-data funnet")
                    failed_count += 1
                
                # Liten pause for å unngå rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"    ❌ Feil: {e}")
                failed_count += 1
        
        # Lagre endringene til databasen
        db.commit()
        print(f"\n✅ Fullført! Oppdatert {updated_count} aktiviteter, {failed_count} feilet")
        
        # Vis et sammendrag av de oppdaterte verdiene
        print(f"\n📊 SAMMENDRAG AV OPPDATERTE EPOC-VERDIER:")
        updated_activities = db.query(Activity).filter(
            Activity.epoc.isnot(None)
        ).order_by(desc(Activity.start_time)).limit(10).all()
        
        for activity in updated_activities:
            print(f"  {activity.activity_id}: {activity.activity_name} - EPOC: {activity.epoc}")
        
    except Exception as e:
        print(f"❌ Feil: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(update_epoc_data()) 