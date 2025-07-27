#!/usr/bin/env python3
"""
Script for å sjekke EPOC-status i databasen
"""

import os
import sys
from datetime import datetime
from sqlalchemy import and_, func

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal
from app.database.models.activity import Activity

def check_epoc_status():
    """Sjekker EPOC-status i databasen"""
    
    print("🔍 Sjekker EPOC-status i databasen")
    
    db = SessionLocal()
    
    try:
        # Total antall aktiviteter
        total_activities = db.query(Activity).count()
        print(f"📊 Total antall aktiviteter: {total_activities}")
        
        # Aktiviter med EPOC
        activities_with_epoc = db.query(Activity).filter(
            Activity.epoc.isnot(None),
            Activity.epoc > 0
        ).count()
        print(f"✅ Aktiviter med EPOC: {activities_with_epoc}")
        
        # Aktiviter uten EPOC
        activities_without_epoc = db.query(Activity).filter(
            (Activity.epoc.is_(None) | (Activity.epoc == 0))
        ).count()
        print(f"❌ Aktiviter uten EPOC: {activities_without_epoc}")
        
        # Sjekk aktiviteter i perioden 2021-2025
        start_date = datetime(2021, 1, 1)
        end_date = datetime(2025, 6, 1)
        
        activities_in_period = db.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time < end_date
            )
        ).count()
        print(f"\n📅 Aktiviter i perioden 2021-2025: {activities_in_period}")
        
        # Aktiviter i perioden uten EPOC
        activities_in_period_without_epoc = db.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time < end_date,
                (Activity.epoc.is_(None) | (Activity.epoc == 0))
            )
        ).count()
        print(f"❌ Aktiviter i perioden uten EPOC: {activities_in_period_without_epoc}")
        
        # Aktiviter i perioden med EPOC
        activities_in_period_with_epoc = db.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time < end_date,
                Activity.epoc.isnot(None),
                Activity.epoc > 0
            )
        ).count()
        print(f"✅ Aktiviter i perioden med EPOC: {activities_in_period_with_epoc}")
        
        # Vis noen eksempler på aktiviteter uten EPOC
        print(f"\n📋 EKSEMPLER PÅ AKTIVITETER UTEN EPOC:")
        sample_activities = db.query(Activity).filter(
            (Activity.epoc.is_(None) | (Activity.epoc == 0))
        ).order_by(Activity.start_time.desc()).limit(5).all()
        
        for activity in sample_activities:
            print(f"  {activity.start_time.strftime('%Y-%m-%d')}: {activity.activity_name} (ID: {activity.activity_id})")
        
        # Vis noen eksempler på aktiviteter med EPOC
        print(f"\n📋 EKSEMPLER PÅ AKTIVITETER MED EPOC:")
        sample_activities_with_epoc = db.query(Activity).filter(
            Activity.epoc.isnot(None),
            Activity.epoc > 0
        ).order_by(Activity.start_time.desc()).limit(5).all()
        
        for activity in sample_activities_with_epoc:
            print(f"  {activity.start_time.strftime('%Y-%m-%d')}: {activity.activity_name} - EPOC: {activity.epoc}")
        
        # Statistikk per år
        print(f"\n📈 EPOC-STATISTIKK PER ÅR:")
        for year in range(2021, 2026):
            year_start = datetime(year, 1, 1)
            year_end = datetime(year + 1, 1, 1)
            
            total_in_year = db.query(Activity).filter(
                and_(
                    Activity.start_time >= year_start,
                    Activity.start_time < year_end
                )
            ).count()
            
            with_epoc_in_year = db.query(Activity).filter(
                and_(
                    Activity.start_time >= year_start,
                    Activity.start_time < year_end,
                    Activity.epoc.isnot(None),
                    Activity.epoc > 0
                )
            ).count()
            
            if total_in_year > 0:
                percentage = (with_epoc_in_year / total_in_year) * 100
                print(f"  {year}: {with_epoc_in_year}/{total_in_year} ({percentage:.1f}%)")
        
    except Exception as e:
        print(f"❌ Feil: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    check_epoc_status() 