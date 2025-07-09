#!/usr/bin/env python3
"""
Script for å starte FIT-data nedlasting for 2018-2021 og overvåke fremgangen
"""

import requests
import json
import time
from datetime import datetime

def start_fit_data_download():
    """Starter FIT-data nedlasting for 2018-2021"""
    
    url = "http://localhost:8000/api/sync/fit-data/download/period"
    payload = {
        "start_date": "2018-01-01",
        "end_date": "2021-12-31"
    }
    
    print("🚀 Starter FIT-data nedlasting for 2018-2021...")
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ Nedlasting startet!")
        print(f"📝 Melding: {result['message']}")
        print(f"🆔 Job ID: {result['job_id']}")
        
        return result['job_id']
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Feil ved start av nedlasting: {e}")
        return None

def check_job_status(job_id):
    """Sjekker status på en bakgrunnsjobb"""
    
    url = f"http://localhost:8000/api/sync/status/{job_id}"
    
    try:
        response = requests.get(url)
        if response.status_code == 404:
            print(f"❌ Jobb {job_id} ikke funnet")
            return None
            
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Feil ved sjekk av status: {e}")
        return None

def monitor_job(job_id, check_interval=30):
    """Overvåker en jobb til den er ferdig"""
    
    print(f"\n🔍 Overvåker jobb {job_id}...")
    print(f"⏱️  Sjekker status hvert {check_interval} sekund")
    
    while True:
        status = check_job_status(job_id)
        
        if not status:
            break
        
        current_time = datetime.now().strftime("%H:%M:%S")
        job_status = status.get('status', 'unknown')
        
        print(f"[{current_time}] Status: {job_status}")
        
        if job_status == "completed":
            print(f"✅ Jobb fullført!")
            if 'result' in status:
                print(f"📊 Resultat: {status['result']}")
            break
        elif job_status == "failed":
            print(f"❌ Jobb feilet!")
            if 'error' in status:
                print(f"🚨 Feil: {status['error']}")
            break
        elif job_status == "processing":
            print("⚙️  Behandling pågår...")
        
        time.sleep(check_interval)

if __name__ == "__main__":
    # Start nedlasting
    job_id = start_fit_data_download()
    
    if job_id:
        # Overvåk fremgang
        monitor_job(job_id)
    else:
        print("❌ Kunne ikke starte nedlasting") 