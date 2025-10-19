from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.database.models.sync_state import SyncState
from datetime import datetime

db = SessionLocal()

print('=== DATABASE STATUS ===')
print(f'Aktiviteter i juli 2024: {db.query(Activity).filter(Activity.start_time >= datetime(2024, 7, 1), Activity.start_time < datetime(2024, 8, 1)).count()}')
print(f'Aktiviteter i august 2024: {db.query(Activity).filter(Activity.start_time >= datetime(2024, 8, 1), Activity.start_time < datetime(2024, 9, 1)).count()}')
print(f'Totalt antall aktiviteter: {db.query(Activity).count()}')

print('\n=== SYNC STATE ===')
sync_state = db.query(SyncState).filter_by(key='activities').first()
if sync_state:
    print(f'Siste synkroniserte dato: {sync_state.last_synced_date}')
    print(f'Siste synkronisering tidspunkt: {sync_state.last_synced_at}')
else:
    print('Ingen SyncState funnet')

print('\n=== ELDSTE/NYESTE AKTIVITET ===')
oldest = db.query(Activity).order_by(Activity.start_time.asc()).first()
newest = db.query(Activity).order_by(Activity.start_time.desc()).first()
if oldest:
    print(f'Eldste: {oldest.activity_id} - {oldest.start_time} - {oldest.activity_name}')
if newest:
    print(f'Nyeste: {newest.activity_id} - {newest.start_time} - {newest.activity_name}')

db.close()

