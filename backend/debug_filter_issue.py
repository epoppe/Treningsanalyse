#!/usr/bin/env python3
"""
Debug-skript for å undersøke filtreringsproblemet i API.
"""

from datetime import date
from app.database.session import SessionLocal
from app.database.models.summaries import DailySummary
import json

def debug_filter_issue():
    """Debug filtreringsproblemet i API."""
    print("Debugging filtreringsproblemet...")
    
    db = SessionLocal()
    
    try:
        # Hent sammendrag for 16.7.2025
        test_date = date(2025, 7, 16)
        summary = db.query(DailySummary).filter(DailySummary.date == test_date).first()
        
        if not summary:
            print("Ingen sammendrag funnet for 16.7.2025")
            return
        
        print(f"\n1. Original sammendrag for {test_date}:")
        print(f"   total_activities: {summary.total_activities}")
        print(f"   total_distance: {summary.total_distance}")
        print(f"   activity_types_breakdown: {summary.activity_types_breakdown}")
        
        # Parse breakdown
        try:
            breakdown = json.loads(summary.activity_types_breakdown) if isinstance(summary.activity_types_breakdown, str) else summary.activity_types_breakdown
            print(f"   Parsed breakdown: {breakdown}")
            
            # Beregn totaler
            total_all = sum(data.get('count', 0) for data in breakdown.values())
            print(f"   Total count i breakdown: {total_all}")
            
            # Test med alle aktivitetstyper
            activity_types = ["running", "treadmill_running", "cycling", "resort_skiing", "cross_country_skiing_ws", "indoor_cardio", "walking", "hiking", "mountain_biking", "resort_skiing_snowboarding_ws", "other", "trail_running", "gravel_cycling", "lap_swimming", "multi_sport", "open_water_swimming", "indoor_cycling"]
            
            # Mapping mellom engelsk typeKey og norske aktivitetstyper
            activity_type_mapping = {
                'running': 'Løping',
                'treadmill_running': 'Løping',
                'cycling': 'Sykling',
                'indoor_cycling': 'Sykling',
                'gravel_cycling': 'Sykling',
                'mountain_biking': 'Sykling',
                'walking': 'Fotturer',
                'hiking': 'Fotturer',
                'trail_running': 'Løping',
                'lap_swimming': 'Svømming',
                'open_water_swimming': 'Svømming',
                'resort_skiing': 'Alpint',
                'resort_skiing_snowboarding_ws': 'Alpint',
                'cross_country_skiing_ws': 'Langrenn',
                'indoor_cardio': 'Innendørs trening',
                'multi_sport': 'Multisport',
                'other': 'Annet'
            }
            
            # Map engelske aktivitetstyper til norske
            norwegian_activity_types = []
            for activity_type in activity_types:
                norwegian_type = activity_type_mapping.get(activity_type, activity_type)
                norwegian_activity_types.append(norwegian_type)
            
            print(f"\n2. Testing filtrering:")
            print(f"   Norske aktivitetstyper: {norwegian_activity_types}")
            
            # Sjekk om noen av de ønskede aktivitetstypene finnes
            found_types = [activity_type for activity_type in norwegian_activity_types if activity_type in breakdown]
            print(f"   Funnet aktivitetstyper: {found_types}")
            
            # Beregn andeler for valgte aktivitetstyper
            total_selected = sum(breakdown.get(activity_type, {}).get('count', 0) for activity_type in norwegian_activity_types)
            print(f"   Total selected: {total_selected}")
            print(f"   Total all: {total_all}")
            
            if total_selected > 0 and total_all > 0:
                ratio = total_selected / total_all
                print(f"   Ratio: {ratio}")
                
                # Simuler filtrering
                new_total_activities = int(summary.total_activities * ratio)
                print(f"   Original total_activities: {summary.total_activities}")
                print(f"   New total_activities: {new_total_activities}")
                
                # Sjekk om det er noe galt med ratio-beregningen
                if ratio != 1.0:
                    print(f"   ⚠️  Ratio er ikke 1.0! Dette kan forklare problemet.")
                else:
                    print(f"   ✓ Ratio er 1.0, som forventet.")
                    
                    # Sjekk om det er noe annet som påvirker verdien
                    print(f"   Sjekker om det er andre faktorer...")
                    
                    # Test med kun én aktivitetstype
                    single_type = ["Løping"]
                    total_single = sum(breakdown.get(activity_type, {}).get('count', 0) for activity_type in single_type)
                    ratio_single = total_single / total_all
                    print(f"   Kun 'Løping': total={total_single}, ratio={ratio_single}")
                    
                    # Test med to aktivitetstyper
                    two_types = ["Løping", "Sykling"]
                    total_two = sum(breakdown.get(activity_type, {}).get('count', 0) for activity_type in two_types)
                    ratio_two = total_two / total_all
                    print(f"   'Løping' + 'Sykling': total={total_two}, ratio={ratio_two}")
            
        except Exception as e:
            print(f"   Feil ved parsing av breakdown: {e}")
        
        # Test med andre dager
        print(f"\n3. Testing andre dager:")
        other_dates = [date(2025, 7, 14), date(2025, 7, 12)]
        
        for test_date in other_dates:
            other_summary = db.query(DailySummary).filter(DailySummary.date == test_date).first()
            if other_summary:
                print(f"   {test_date}: total_activities={other_summary.total_activities}")
                try:
                    other_breakdown = json.loads(other_summary.activity_types_breakdown) if isinstance(other_summary.activity_types_breakdown, str) else other_summary.activity_types_breakdown
                    other_total = sum(data.get('count', 0) for data in other_breakdown.values())
                    print(f"     Breakdown total: {other_total}")
                except:
                    print(f"     Kunne ikke parse breakdown")
        
    except Exception as e:
        print(f"✗ Debug feilet: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_filter_issue() 