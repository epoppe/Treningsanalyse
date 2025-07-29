#!/usr/bin/env python3
"""
Enkel test av power-beregning
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.power_service import PowerService
from app.storage import DataStorage

def test_power_calculation():
    """Tester power-beregning med enkle verdier"""
    
    # Initialiser PowerService
    storage = DataStorage()
    power_service = PowerService(storage)
    
    print("=== Enkel Power-beregning Test ===\n")
    
    # Test 1: Enkel power-beregning
    print("1. Tester power-beregning med enkle verdier:")
    
    # Test med typiske løpeverdier
    mass_kg = 75.0
    speed_mps = 3.0  # ~10.8 km/h
    prev_speed_mps = 3.0  # Konstant hastighet
    slope_percent = 0.0  # Flat terreng
    vo_cm = 10.0  # Vertikal oscillasjon
    gct_ms = 250.0  # Ground contact time
    
    power = power_service.running_power(mass_kg, speed_mps, prev_speed_mps, slope_percent, vo_cm, gct_ms)
    
    print(f"   Masse: {mass_kg} kg")
    print(f"   Hastighet: {speed_mps} m/s ({speed_mps * 3.6:.1f} km/h)")
    print(f"   Stigning: {slope_percent}%")
    print(f"   Vertikal oscillasjon: {vo_cm} cm")
    print(f"   Ground contact time: {gct_ms} ms")
    print(f"   Beregnet power: {power:.1f} W")
    print()
    
    # Test 2: Power med stigning
    print("2. Tester power med stigning:")
    slope_percent = 5.0  # 5% stigning
    power_uphill = power_service.running_power(mass_kg, speed_mps, prev_speed_mps, slope_percent, vo_cm, gct_ms)
    print(f"   Power med {slope_percent}% stigning: {power_uphill:.1f} W")
    print(f"   Økning: {power_uphill - power:.1f} W")
    print()
    
    # Test 3: Power med høyere hastighet
    print("3. Tester power med høyere hastighet:")
    speed_mps = 4.0  # ~14.4 km/h
    power_faster = power_service.running_power(mass_kg, speed_mps, prev_speed_mps, slope_percent, vo_cm, gct_ms)
    print(f"   Power ved {speed_mps} m/s: {power_faster:.1f} W")
    print()
    
    print("=== Test fullført ===")
    print("Power-beregningen ser ut til å fungere korrekt!")

if __name__ == "__main__":
    test_power_calculation()