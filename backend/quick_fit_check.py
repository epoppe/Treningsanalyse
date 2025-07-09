#!/usr/bin/env python3
"""
Script for å sjekke FIT-data direkte fra storage uten database
"""

import os
import sys
import pandas as pd

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.storage import DataStorage

def quick_fit_check():
    """Sjekk FIT-data tilgjengelighet direkte fra storage"""
    
    try:
        storage = DataStorage(os.path.join(os.path.dirname(__file__), "data"))
        activity_details = storage.activity_details_df
        
        print(f"📋 FIT-data oversikt:")
        print(f"Total FIT-datapunkter: {len(activity_details):,}")
        
        if len(activity_details) > 0:
            # Sjekk unike aktiviteter
            unique_activities = activity_details['activity_id'].nunique()
            print(f"Unike aktiviteter med FIT-data: {unique_activities:,}")
            
            # Sjekk dato-rekkevidde
            min_timestamp = activity_details['timestamp'].min()
            max_timestamp = activity_details['timestamp'].max()
            print(f"Dato-rekkevidde: {min_timestamp} til {max_timestamp}")
            
            # Vis de 10 nyeste aktivitetene
            latest_activities = activity_details.groupby('activity_id')['timestamp'].max().sort_values(ascending=False).head(10)
            print(f"\n🏃 De 10 nyeste aktivitetene med FIT-data:")
            for activity_id, last_timestamp in latest_activities.items():
                num_points = len(activity_details[activity_details['activity_id'] == activity_id])
                print(f"  - {activity_id}: {last_timestamp.strftime('%Y-%m-%d')} ({num_points:,} datapunkter)")
            
            # Vis de 10 eldste aktivitetene
            oldest_activities = activity_details.groupby('activity_id')['timestamp'].min().sort_values(ascending=True).head(10)
            print(f"\n📅 De 10 eldste aktivitetene med FIT-data:")
            for activity_id, first_timestamp in oldest_activities.items():
                num_points = len(activity_details[activity_details['activity_id'] == activity_id])
                print(f"  - {activity_id}: {first_timestamp.strftime('%Y-%m-%d')} ({num_points:,} datapunkter)")
                
        else:
            print("❌ Ingen FIT-data funnet")
    
    except Exception as e:
        print(f"❌ Feil ved lasting av FIT-data: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    quick_fit_check() 