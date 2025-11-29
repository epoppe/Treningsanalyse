#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / 'data' / 'treningsanalyse.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Sjekk datoområde for aktiviteter
cursor.execute("""
    SELECT 
        MIN(start_time) as earliest,
        MAX(start_time) as latest,
        COUNT(*) as total
    FROM activities
""")

result = cursor.fetchone()
print(f'Aktiviteter i databasen:')
print(f'  Total: {result[2]}')
print(f'  Tidligste: {result[0]}')
print(f'  Siste: {result[1]}')

conn.close()

