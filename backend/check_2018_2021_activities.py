#!/usr/bin/env python3
"""
Script for å sjekke aktiviteter fra 2018-2021 og identifisere manglende FIT-data
"""

import os
import sys
import sqlite3
from datetime import datetime, date
import pandas as pd

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.storage import DataStorage

def check_2018_2021_activities():
    """Sjekk aktiviteter fra 2018-2021 og identifiser manglende FIT-data"""
    
    # Hent database-tilkobling
    db_path = os.path.join(os.path.dirname(__file__), "data", "activities.db")
    conn = sqlite3.connect(db_path)
    
    # Finn alle aktiviteter fra 2018-2021
    query = """
    SELECT 
        id as activity_id,
        name,
        start_time_local,
        type,
        distance,
        moving_time,
        total_elevation_gain
    FROM activities 
    WHERE date(start_time_local) >= '2018-01-01' 
    AND date(start_time_local) <= '2021-12-31'
    ORDER BY start_time_local DESC
    """
    
    activities_df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"🔍 Fant {len(activities_df)} aktiviteter fra 2018-2021")
    
    if len(activities_df) == 0:
        print("❌ Ingen aktiviteter funnet i perioden 2018-2021")
        return
    
    # Vis oversikt over aktiviteter per år
    activities_df['year'] = pd.to_datetime(activities_df['start_time_local']).dt.year
    yearly_counts = activities_df['year'].value_counts().sort_index()
    print("\n📊 Aktiviteter per år:")
    for year, count in yearly_counts.items():
        print(f"  {year}: {count} aktiviteter")
    
    # Sjekk FIT-data tilgjengelighet
    try:
        storage = DataStorage(os.path.join(os.path.dirname(__file__), "data"))
        activity_details = storage.activity_details_df
        
        print(f"\n📋 FIT-data oversikt:")
        print(f"Total FIT-datapunkter tilgjengelig: {len(activity_details):,}")
        
        # Sjekk hvilke aktiviteter som har FIT-data
        activities_with_fit = set(activity_details['activity_id'].unique())
        activities_2018_2021 = set(activities_df['activity_id'])
        
        missing_fit = activities_2018_2021 - activities_with_fit
        has_fit = activities_2018_2021 & activities_with_fit
        
        print(f"\n🎯 FIT-data status for 2018-2021:")
        print(f"  ✅ Har FIT-data: {len(has_fit)} aktiviteter")
        print(f"  ❌ Mangler FIT-data: {len(missing_fit)} aktiviteter")
        print(f"  📈 Dekning: {len(has_fit)/len(activities_2018_2021)*100:.1f}%")
        
        if missing_fit:
            print(f"\n📝 Eksempler på aktiviteter som mangler FIT-data:")
            missing_activities = activities_df[activities_df['activity_id'].isin(list(missing_fit)[:5])]
            for _, activity in missing_activities.iterrows():
                print(f"  - {activity['activity_id']}: {activity['name']} ({activity['start_time_local'][:10]})")
            
            if len(missing_fit) > 5:
                print(f"  ... og {len(missing_fit) - 5} til")
    
    except Exception as e:
        print(f"❌ Feil ved lasting av FIT-data: {e}")
    
    return activities_df, missing_fit if 'missing_fit' in locals() else set()

if __name__ == "__main__":
    activities_df, missing_fit = check_2018_2021_activities()
    
    if missing_fit:
        print(f"\n🚀 For å laste ned FIT-data for {len(missing_fit)} manglende aktiviteter:")
        print(f"   Bruk sync API med datoperiode 2018-01-01 til 2021-12-31") 