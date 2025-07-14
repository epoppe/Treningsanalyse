#!/usr/bin/env python3
"""
Script for å hente Training Effect data fra Garmin og oppdatere databasen
"""

import asyncio
from datetime import datetime, timedelta
from app.services.garmin_client import GarminClient
from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.config import settings
from sqlalchemy import desc

async def update_training_effect_data():
    """Henter Training Effect data fra Garmin og oppdaterer databasen"""
    
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
        
        # Hent de 20 nyeste aktivitetene
        print("🔍 Henter de 20 nyeste aktivitetene...")
        activities = db.query(Activity).order_by(desc(Activity.start_time)).limit(20).all()
        
        print(f"📊 Fant {len(activities)} aktiviteter å oppdatere")
        
        updated_count = 0
        failed_count = 0
        
        for i, activity in enumerate(activities, 1):
            activity_id = activity.activity_id
            print(f"\n{i:2d}. Prosesserer aktivitet {activity_id} - {activity.activity_name}")
            print(f"    Start: {activity.start_time}")
            
            try:
                # Hent Training Effect data fra Garmin
                te_data = await garmin_client.get_activity_training_effect(activity_id)
                
                if te_data:
                    # Oppdater databasen
                    activity.total_training_effect = te_data.get('aerobic_training_effect')
                    activity.total_anaerobic_training_effect = te_data.get('anaerobic_training_effect')
                    
                    print(f"    ✅ Oppdatert: Aerobic TE={activity.total_training_effect}, "
                          f"Anaerobic TE={activity.total_anaerobic_training_effect}")
                    
                    if te_data.get('training_effect_label'):
                        print(f"    🏷️  Label: {te_data['training_effect_label']}")
                    
                    updated_count += 1
                else:
                    print(f"    ❌ Ingen Training Effect data funnet")
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
        print(f"\n📊 SAMMENDRAG AV OPPDATERTE VERDIER:")
        for activity in activities[:10]:  # Vis bare de 10 første
            if activity.total_training_effect is not None or activity.total_anaerobic_training_effect is not None:
                print(f"  {activity.activity_id}: Aerobic={activity.total_training_effect}, "
                      f"Anaerobic={activity.total_anaerobic_training_effect}")
        
    except Exception as e:
        print(f"❌ Generell feil: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(update_training_effect_data()) 