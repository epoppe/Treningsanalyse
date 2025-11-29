#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / 'data' / 'treningsanalyse.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Sjekk aktiviteter fra november 2025
cursor.execute("""
    SELECT COUNT(*) as total,
           COUNT(total_ascent) as with_ascent,
           SUM(total_ascent) as total_ascent_sum,
           AVG(total_ascent) as avg_ascent
    FROM activities
    WHERE strftime('%Y-%m', start_time) = '2025-11'
""")

result = cursor.fetchone()
print(f'November 2025 aktiviteter:')
print(f'  Total: {result[0]}')
print(f'  Med total_ascent: {result[1]}')
print(f'  Sum total_ascent: {result[2] if result[2] else 0}')
print(f'  Gjennomsnitt: {result[3] if result[3] else 0}')

# Sjekk noen eksempler
cursor.execute("""
    SELECT activity_id, start_time, total_ascent, distance
    FROM activities
    WHERE strftime('%Y-%m', start_time) = '2025-11'
    LIMIT 5
""")

rows = cursor.fetchall()
print(f'\nEksempler:')
for r in rows:
    print(f'  {r[0]}: {r[1]} - total_ascent: {r[2]}, distance: {r[3]}')

# Sjekk månedlig sammendrag
cursor.execute("""
    SELECT month, year, total_ascent
    FROM monthly_summaries
    WHERE year = 2025 AND month = 11
""")

summary = cursor.fetchone()
if summary:
    print(f'\nMånedlig sammendrag november 2025:')
    print(f'  total_ascent: {summary[2]}')

conn.close()

