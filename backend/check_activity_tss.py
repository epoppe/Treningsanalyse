#!/usr/bin/env python3
import sqlite3
from pathlib import Path
from datetime import datetime

db_path = Path(__file__).parent / 'data' / 'treningsanalyse.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Sjekk aktiviteter fra november 2025
cursor.execute("""
    SELECT COUNT(*) as total,
           COUNT(training_stress_score) as with_tss,
           SUM(training_stress_score) as total_tss
    FROM activities
    WHERE strftime('%Y-%m', start_time) = '2025-11'
""")

result = cursor.fetchone()
print(f'November 2025 aktiviteter:')
print(f'  Total: {result[0]}')
print(f'  Med TSS: {result[1]}')
print(f'  Sum TSS: {result[2] if result[2] else 0}')

# Sjekk noen eksempler
cursor.execute("""
    SELECT activity_id, start_time, training_stress_score
    FROM activities
    WHERE strftime('%Y-%m', start_time) = '2025-11'
    LIMIT 5
""")

rows = cursor.fetchall()
print(f'\nEksempler:')
for r in rows:
    print(f'  {r[0]}: {r[1]} - TSS: {r[2]}')

conn.close()

