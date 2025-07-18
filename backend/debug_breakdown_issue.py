#!/usr/bin/env python3
"""
Debug-skript for å undersøke activity_types_breakdown-problemet.
"""

from datetime import date
from app.database.session import SessionLocal
from app.database.models.summaries import DailySummary
import json

def debug_breakdown_issue():
    """Debug activity_types_breakdown-problemet."""
    print("Debugging activity_types_breakdown-problemet...")
    
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
        print(f"   activity_types_breakdown: {summary.activity_types_breakdown}")
        
        # Parse breakdown
        try:
            breakdown = json.loads(summary.activity_types_breakdown) if isinstance(summary.activity_types_breakdown, str) else summary.activity_types_breakdown
            print(f"   Parsed breakdown: {breakdown}")
            
            # Test med kun running
            print(f"\n2. Testing med kun 'running':")
            running_count = breakdown.get('Løping', {}).get('count', 0)
            print(f"   Løping count: {running_count}")
            
            # Test med running og treadmill_running
            print(f"\n3. Testing med 'running' og 'treadmill_running':")
            # Begge mapper til 'Løping', så vi får 2 * count
            total_count = running_count * 2
            print(f"   Total count (2 * {running_count}): {total_count}")
            
            # Test med alle aktivitetstyper som mapper til 'Løping'
            print(f"\n4. Testing med alle aktivitetstyper som mapper til 'Løping':")
            # running, treadmill_running, trail_running alle mapper til 'Løping'
            total_count_all = running_count * 3
            print(f"   Total count (3 * {running_count}): {total_count_all}")
            
            # Simuler filtreringslogikken
            print(f"\n5. Simulerer filtreringslogikken:")
            
            # Test 1: Kun running
            activity_types_1 = ["running"]
            norwegian_types_1 = ["Løping"]
            total_selected_1 = sum(breakdown.get(activity_type, {}).get('count', 0) for activity_type in norwegian_types_1)
            total_all_1 = sum(data.get('count', 0) for data in breakdown.values())
            ratio_1 = total_selected_1 / total_all_1 if total_all_1 > 0 else 0
            print(f"   Kun running: selected={total_selected_1}, all={total_all_1}, ratio={ratio_1}")
            
            # Test 2: Running og treadmill_running
            activity_types_2 = ["running", "treadmill_running"]
            norwegian_types_2 = ["Løping", "Løping"]  # Dette er problemet!
            total_selected_2 = sum(breakdown.get(activity_type, {}).get('count', 0) for activity_type in norwegian_types_2)
            total_all_2 = sum(data.get('count', 0) for data in breakdown.values())
            ratio_2 = total_selected_2 / total_all_2 if total_all_2 > 0 else 0
            print(f"   Running + treadmill: selected={total_selected_2}, all={total_all_2}, ratio={ratio_2}")
            
            # Test 3: Alle aktivitetstyper
            activity_types_3 = ["running", "treadmill_running", "trail_running"]
            norwegian_types_3 = ["Løping", "Løping", "Løping"]  # Dette er problemet!
            total_selected_3 = sum(breakdown.get(activity_type, {}).get('count', 0) for activity_type in norwegian_types_3)
            total_all_3 = sum(data.get('count', 0) for data in breakdown.values())
            ratio_3 = total_selected_3 / total_all_3 if total_all_3 > 0 else 0
            print(f"   Alle løpingstyper: selected={total_selected_3}, all={total_all_3}, ratio={ratio_3}")
            
            print(f"\n=== PROBLEM IDENTIFISERT ===")
            print(f"Problemet er at 'running', 'treadmill_running', og 'trail_running' alle mapper til 'Løping'.")
            print(f"Når vi summerer count for 'Løping' flere ganger, får vi feil resultat.")
            print(f"Løsningen er å fjerne duplikater fra norwegian_activity_types-listen.")
            
        except Exception as e:
            print(f"   Feil ved parsing av breakdown: {e}")
        
    except Exception as e:
        print(f"✗ Debug feilet: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_breakdown_issue() 