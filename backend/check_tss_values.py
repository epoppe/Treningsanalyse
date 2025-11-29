#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / 'data' / 'treningsanalyse.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute('SELECT month, year, total_tss FROM monthly_summaries ORDER BY year DESC, month DESC LIMIT 5')
rows = cursor.fetchall()

print('Måned | År | Total TSS')
print('-' * 30)
for r in rows:
    tss_value = r[2] if r[2] is not None else 'NULL'
    print(f'{r[0]:2d}/{r[1]} | {tss_value}')

conn.close()

