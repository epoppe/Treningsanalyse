#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / 'data' / 'treningsanalyse.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Sjekk aktiviteter fra 2022 og fremover
cursor.execute("""
    SELECT 
        strftime('%Y-%m', start_time) as month,
        COUNT(*) as total,
        COUNT(total_ascent) as with_ascent,
        SUM(total_ascent) as total_ascent_sum
    FROM activities
    WHERE start_time >= '2022-01-01'
    GROUP BY strftime('%Y-%m', start_time)
    ORDER BY month DESC
    LIMIT 12
""")

results = cursor.fetchall()
print(f'Månedlige sammendrag for elevation gain (siste 12 måneder):')
print(f'{"Måned":<10} {"Total":<8} {"Med ascent":<12} {"Sum ascent (m)":<15}')
print('-' * 50)
for row in results:
    month, total, with_ascent, total_ascent = row
    total_ascent = total_ascent if total_ascent else 0
    print(f'{month:<10} {total:<8} {with_ascent:<12} {total_ascent:<15.1f}')

# Sjekk månedlige sammendrag
cursor.execute("""
    SELECT month, year, total_ascent
    FROM monthly_summaries
    WHERE year >= 2022
    ORDER BY year DESC, month DESC
    LIMIT 12
""")

summaries = cursor.fetchall()
print(f'\nMånedlige sammendrag (siste 12 måneder):')
print(f'{"Måned":<10} {"År":<6} {"Total ascent (m)":<20}')
print('-' * 40)
for row in summaries:
    month, year, total_ascent = row
    total_ascent = total_ascent if total_ascent else 0
    print(f'{month}/{year:<4} {total_ascent:<20.1f}')

conn.close()

