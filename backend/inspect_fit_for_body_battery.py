#!/usr/bin/env python3
"""
Script for å undersøke FIT-data og lete etter body_battery felter
"""

import os
import sys
import asyncio
from pathlib import Path

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.services.garmin_client import GarminClient
from app.services.sync_service import SyncService
from app.config import settings

async def inspect_fit_for_body_battery():
    """Inspiser FIT-data for å finne body_battery felter"""
    
    # Bruk en nylig aktivitet som eksempel
    activity_id = 11087578381  # Fra loggene
    
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    
    sync_service = SyncService(garmin_client, None, None)
    
    if not await garmin_client.initialize():
        print("❌ Kunne ikke initialisere Garmin-klient")
        return
    
    print(f"🔍 Inspiserer FIT-data for aktivitet {activity_id}")
    
    # Hent FIT-data fra Garmin
    fit_data = await garmin_client.get_activity_details(str(activity_id))
    if not fit_data:
        print("❌ Ingen FIT-data fra Garmin")
        return
    
    print(f"✓ Hentet FIT-data ({len(fit_data)} bytes)")
    
    # Bruk fitparse direkte for å få alle felt
    try:
        import zipfile
        import io
        from fitparse import FitFile
        
        # Sjekk om dataene er en ZIP-fil
        if fit_data.startswith(b'PK'):
            print("📦 FIT-data er en ZIP-fil, ekstrakterer...")
            with zipfile.ZipFile(io.BytesIO(fit_data), 'r') as zip_file:
                fit_files = [name for name in zip_file.namelist() if name.endswith('.fit')]
                if not fit_files:
                    print("❌ Ingen FIT-fil funnet i ZIP")
                    return
                fit_data = zip_file.read(fit_files[0])
        
        # Parser FIT-data
        fitfile = FitFile(io.BytesIO(fit_data))
        
        print("\n🔍 Alle meldingstyper i FIT-filen:")
        message_types = set()
        for message in fitfile.get_messages():
            message_types.add(message.name)
        
        for msg_type in sorted(message_types):
            print(f"  - {msg_type}")
        
        # Undersøk alle felter i alle meldingstyper
        all_fields = set()
        body_battery_fields = []
        
        print(f"\n🔍 Inspeserer alle felter...")
        for message in fitfile.get_messages():
            for field in message.fields:
                field_name = field.name.lower()
                all_fields.add(field.name)
                
                # Søk etter body battery relaterte felter
                if any(keyword in field_name for keyword in ['body', 'battery', 'energy', 'stress', 'recovery']):
                    body_battery_fields.append({
                        'message_type': message.name,
                        'field_name': field.name,
                        'value': field.value,
                        'units': getattr(field, 'units', None)
                    })
        
        print(f"\n📊 Totalt funnet {len(all_fields)} unike felter")
        
        # Vis alle felter sortert alfabetisk
        print(f"\n📋 Alle tilgjengelige felter (alfabetisk):")
        for field in sorted(all_fields):
            print(f"  - {field}")
        
        # Vis body battery relaterte felter
        if body_battery_fields:
            print(f"\n🔋 Body Battery / Energy / Stress relaterte felter:")
            for field_info in body_battery_fields:
                print(f"  - {field_info['message_type']}.{field_info['field_name']}: {field_info['value']} {field_info['units'] or ''}")
        else:
            print(f"\n❌ Ingen body battery relaterte felter funnet")
        
        # Undersøk spesifikke meldingstyper som kan inneholde body battery data
        specific_messages = ['session', 'activity', 'monitoring', 'device_info', 'user_profile']
        
        print(f"\n🎯 Undersøker spesifikke meldingstyper:")
        for msg_type in specific_messages:
            messages = list(fitfile.get_messages(msg_type))
            if messages:
                print(f"\n  📋 {msg_type.upper()} ({len(messages)} meldinger):")
                for i, message in enumerate(messages[:3]):  # Vis kun første 3
                    print(f"    Melding {i+1}:")
                    for field in message.fields:
                        field_name = field.name.lower()
                        if any(keyword in field_name for keyword in ['body', 'battery', 'energy', 'stress', 'recovery']):
                            print(f"      🔋 {field.name}: {field.value} {getattr(field, 'units', '') or ''}")
                        elif i == 0:  # Vis alle felter for første melding
                            print(f"      - {field.name}: {field.value}")
            else:
                print(f"    Ingen {msg_type} meldinger funnet")
                
    except ImportError:
        print("❌ fitparse-biblioteket er ikke installert")
        return
    except Exception as e:
        print(f"❌ Feil ved parsing av FIT-data: {e}")
        return

if __name__ == "__main__":
    asyncio.run(inspect_fit_for_body_battery()) 