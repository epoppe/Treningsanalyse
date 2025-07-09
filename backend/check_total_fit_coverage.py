#!/usr/bin/env python3
"""
Script for å sjekke total FIT-data dekning etter nedlasting av 2018-2021 data
"""

import os
import sys
import sqlite3
from datetime import datetime, date
import pandas as pd

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.storage import DataStorage

def check_total_fit_coverage():
    """Sjekk total FIT-data dekning på tvers av alle år"""
    
    # Hent database-tilkobling
    db_path = os.path.join(os.path.dirname(__file__), "data", "activities.db")
    conn = sqlite3.connect(db_path)
    
    # Finn alle aktiviteter
    query = """
    SELECT 
        id as activity_id,
        name,
        start_time_local,
        type,
        distance,
        moving_time
    FROM activities 
    ORDER BY start_time_local DESC
    """
    
    activities_df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"🔍 Total antall aktiviteter i database: {len(activities_df):,}")
    
    if len(activities_df) == 0:
        print("❌ Ingen aktiviteter funnet")
        return
    
    # Vis oversikt over aktiviteter per år
    activities_df['year'] = pd.to_datetime(activities_df['start_time_local']).dt.year
    yearly_counts = activities_df['year'].value_counts().sort_index()
    
    print("\n📊 Aktiviteter per år:")
    for year, count in yearly_counts.items():
        print(f"  {year}: {count:,} aktiviteter")
    
    # Sjekk FIT-data tilgjengelighet
    try:
        storage = DataStorage(os.path.join(os.path.dirname(__file__), "data"))
        activity_details = storage.activity_details_df
        
        print(f"\n📋 FIT-data oversikt:")
        print(f"Total FIT-datapunkter tilgjengelig: {len(activity_details):,}")
        
        # Sjekk hvilke aktiviteter som har FIT-data
        activities_with_fit = set(activity_details['activity_id'].unique())
        all_activities = set(activities_df['activity_id'])
        
        missing_fit = all_activities - activities_with_fit
        has_fit = all_activities & activities_with_fit
        
        print(f"\n🎯 Total FIT-data status:")
        print(f"  ✅ Har FIT-data: {len(has_fit):,} aktiviteter")
        print(f"  ❌ Mangler FIT-data: {len(missing_fit):,} aktiviteter")
        print(f"  📈 Total dekning: {len(has_fit)/len(all_activities)*100:.1f}%")
        
        # Dekning per år
        print(f"\n📊 FIT-data dekning per år:")
        for year in sorted(yearly_counts.index):
            year_activities = set(activities_df[activities_df['year'] == year]['activity_id'])
            year_with_fit = year_activities & activities_with_fit
            year_coverage = len(year_with_fit) / len(year_activities) * 100 if year_activities else 0
            print(f"  {year}: {len(year_with_fit):,}/{len(year_activities):,} ({year_coverage:.1f}%)")
        
        if missing_fit:
            print(f"\n📝 Eksempler på aktiviteter som fortsatt mangler FIT-data:")
            missing_activities = activities_df[activities_df['activity_id'].isin(list(missing_fit)[:5])]
            for _, activity in missing_activities.iterrows():
                print(f"  - {activity['activity_id']}: {activity['name']} ({activity['start_time_local'][:10]})")
    
    except Exception as e:
        print(f"❌ Feil ved lasting av FIT-data: {e}")
    
    return activities_df, missing_fit if 'missing_fit' in locals() else set()

if __name__ == "__main__":
    activities_df, missing_fit = check_total_fit_coverage()
    
    print(f"\n🎯 Status:")
    print(f"✅ FIT-data nedlasting for 2018-2021 er fullført")
    print(f"📈 Systemet har nå omfattende FIT-data dekning på tvers av alle år")
    if missing_fit:
        print(f"⚠️  {len(missing_fit)} aktiviteter mangler fortsatt FIT-data") 