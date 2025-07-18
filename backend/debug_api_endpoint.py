#!/usr/bin/env python3
"""
Debug-skript for å teste API-endepunktene direkte.
"""

import requests
import json
from datetime import date

def debug_api_endpoints():
    """Test API-endepunktene direkte."""
    print("Testing API-endepunkter direkte...")
    
    base_url = "http://localhost:8000/api/analysis"
    
    try:
        # Test daglige sammendrag uten filtrering
        print("\n1. Testing daglige sammendrag uten filtrering:")
        response = requests.get(f"{base_url}/daily-summaries?limit=5")
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Antall sammendrag: {len(data)}")
            
            for summary in data:
                print(f"   {summary.get('date')}: {summary.get('total_activities')} aktiviteter")
        else:
            print(f"   Feil: {response.status_code} - {response.text}")
        
        # Test daglige sammendrag med aktivitetstyper
        print("\n2. Testing daglige sammendrag med aktivitetstyper:")
        activity_types = ["running", "treadmill_running", "cycling", "resort_skiing", "cross_country_skiing_ws", "indoor_cardio", "walking", "hiking", "mountain_biking", "resort_skiing_snowboarding_ws", "other", "trail_running", "gravel_cycling", "lap_swimming", "multi_sport", "open_water_swimming", "indoor_cycling"]
        
        params = "&".join([f"activity_types={at}" for at in activity_types])
        response = requests.get(f"{base_url}/daily-summaries?limit=5&{params}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Antall sammendrag: {len(data)}")
            
            for summary in data:
                print(f"   {summary.get('date')}: {summary.get('total_activities')} aktiviteter")
        else:
            print(f"   Feil: {response.status_code} - {response.text}")
        
        # Test ukentlige sammendrag
        print("\n3. Testing ukentlige sammendrag:")
        response = requests.get(f"{base_url}/weekly-summaries?limit=5")
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Antall sammendrag: {len(data)}")
            
            for summary in data:
                print(f"   {summary.get('week_start_date')} - {summary.get('week_end_date')}: {summary.get('total_activities')} aktiviteter")
        else:
            print(f"   Feil: {response.status_code} - {response.text}")
        
        # Test månedlige sammendrag
        print("\n4. Testing månedlige sammendrag:")
        response = requests.get(f"{base_url}/monthly-summaries?limit=5")
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Antall sammendrag: {len(data)}")
            
            for summary in data:
                print(f"   {summary.get('month_start_date')} - {summary.get('month_end_date')}: {summary.get('total_activities')} aktiviteter")
        else:
            print(f"   Feil: {response.status_code} - {response.text}")
        
        # Test summary-stats
        print("\n5. Testing summary-stats:")
        response = requests.get(f"{base_url}/summary-stats")
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Data: {json.dumps(data, indent=2)}")
        else:
            print(f"   Feil: {response.status_code} - {response.text}")
        
    except Exception as e:
        print(f"✗ API-test feilet: {e}")

if __name__ == "__main__":
    debug_api_endpoints() 