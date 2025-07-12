#!/usr/bin/env python3
"""
Kommandolinje-verktøy for treningsanalyse.
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Legg til backend-mappen til Python path
sys.path.append(str(Path(__file__).parent))

from app.services.data_sync import DataSyncService
from app.services.export_service import export_service
from app.services.advanced_analysis import advanced_analysis
from app.utils.error_handler import error_handler

def sync_data(args):
    """Synkroniser data fra Garmin Connect."""
    try:
        print("Starter datasynkronisering...")
        sync_service = DataSyncService()
        
        if args.all:
            print("Synkroniserer alle data...")
            sync_service.sync_all_data()
        elif args.activities:
            print("Synkroniserer aktiviteter...")
            sync_service.sync_activities()
        elif args.hrv:
            print("Synkroniserer HRV-data...")
            sync_service.sync_hrv_data()
        
        print("Datasynkronisering fullført!")
        
    except Exception as e:
        error_handler.log_error(e, {'command': 'sync_data', 'args': vars(args)})
        print(f"Feil under synkronisering: {e}")
        sys.exit(1)

def export_data(args):
    """Eksporter data."""
    try:
        print(f"Eksporterer data til {args.format}...")
        
        # Hent aktiviteter basert på filter
        from app.database.session import SessionLocal
        from app.database.models.activity import Activity
        
        db = SessionLocal()
        query = db.query(Activity)
        
        if args.start_date:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
            query = query.filter(Activity.start_time >= start_date)
        
        if args.end_date:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
            query = query.filter(Activity.start_time <= end_date)
        
        activities = query.all()
        db.close()
        
        if not activities:
            print("Ingen aktiviteter funnet for eksport.")
            return
        
        if args.format == 'csv':
            filepath = export_service.export_activities_to_csv(activities, args.output)
        elif args.format == 'json':
            filepath = export_service.export_activities_to_json(activities, args.output)
        else:
            print(f"Ukjent format: {args.format}")
            sys.exit(1)
        
        print(f"Data eksportert til: {filepath}")
        
    except Exception as e:
        error_handler.log_error(e, {'command': 'export_data', 'args': vars(args)})
        print(f"Feil under eksport: {e}")
        sys.exit(1)

def create_backup(args):
    """Opprett backup."""
    try:
        print("Oppretter backup...")
        backup_path = export_service.create_backup(args.include_exports)
        print(f"Backup opprettet: {backup_path}")
        
    except Exception as e:
        error_handler.log_error(e, {'command': 'create_backup', 'args': vars(args)})
        print(f"Feil under backup: {e}")
        sys.exit(1)

def analyze_data(args):
    """Analyser data."""
    try:
        if args.monthly:
            year, month = map(int, args.monthly.split('-'))
            result = advanced_analysis.get_monthly_summary(year, month)
            print(f"\nMånedlig sammendrag for {month}/{year}:")
            print(f"Totalt aktiviteter: {result.get('total_activities', 0)}")
            print(f"Total distanse: {result.get('total_distance', 0):.2f} meter")
            print(f"Total varighet: {result.get('total_duration', 0)} sekunder")
            print(f"Gjennomsnittspuls: {result.get('avg_heart_rate', 'N/A')}")
        
        elif args.yearly:
            year = int(args.yearly)
            result = advanced_analysis.get_yearly_summary(year)
            print(f"\nÅrlig sammendrag for {year}:")
            print(f"Totalt aktiviteter: {result.get('total_activities', 0)}")
            
            activity_types = result.get('activity_types', {})
            print("\nAktivitetstyper:")
            for type_name, stats in activity_types.items():
                print(f"  {type_name}: {stats['count']} aktiviteter, {stats['total_distance']:.2f}m")
        
        elif args.trends:
            result = advanced_analysis.get_performance_trends(args.trends, args.days or 90)
            if 'error' in result:
                print(f"Feil: {result['error']}")
            else:
                print(f"\nPrestasjonstrender for {args.trends} (siste {result['period_days']} dager):")
                print(f"Totalt aktiviteter: {result['total_activities']}")
                print(f"Gjennomsnittsdistanse: {result['avg_distance']:.2f} meter")
                print(f"Gjennomsnittsfart: {result['avg_speed']:.2f} km/h")
                print(f"Distansetrend: {result['distance_trend']:.2f}")
                print(f"Fartstrend: {result['speed_trend']:.2f}")
        
        elif args.records:
            records = advanced_analysis.get_personal_records(args.records if args.records != 'all' else None)
            print("\nPersonlige rekorder:")
            for record in records:
                print(f"  {record['record_type']}: {record['value']} {record['unit']} ({record['date']})")
        
    except Exception as e:
        error_handler.log_error(e, {'command': 'analyze_data', 'args': vars(args)})
        print(f"Feil under analyse: {e}")
        sys.exit(1)

def main():
    """Hovedfunksjon."""
    parser = argparse.ArgumentParser(description='Treningsanalyse CLI')
    subparsers = parser.add_subparsers(dest='command', help='Tilgjengelige kommandoer')
    
    # Sync-kommando
    sync_parser = subparsers.add_parser('sync', help='Synkroniser data')
    sync_parser.add_argument('--all', action='store_true', help='Synkroniser alle data')
    sync_parser.add_argument('--activities', action='store_true', help='Synkroniser kun aktiviteter')
    sync_parser.add_argument('--hrv', action='store_true', help='Synkroniser kun HRV-data')
    sync_parser.set_defaults(func=sync_data)
    
    # Export-kommando
    export_parser = subparsers.add_parser('export', help='Eksporter data')
    export_parser.add_argument('--format', choices=['csv', 'json'], required=True, help='Eksportformat')
    export_parser.add_argument('--output', help='Utdatafil (valgfritt)')
    export_parser.add_argument('--start-date', help='Startdato (YYYY-MM-DD)')
    export_parser.add_argument('--end-date', help='Sluttdato (YYYY-MM-DD)')
    export_parser.set_defaults(func=export_data)
    
    # Backup-kommando
    backup_parser = subparsers.add_parser('backup', help='Opprett backup')
    backup_parser.add_argument('--include-exports', action='store_true', help='Inkluder eksportfiler i backup')
    backup_parser.set_defaults(func=create_backup)
    
    # Analyse-kommando
    analyze_parser = subparsers.add_parser('analyze', help='Analyser data')
    analyze_parser.add_argument('--monthly', help='Månedlig sammendrag (YYYY-MM)')
    analyze_parser.add_argument('--yearly', help='Årlig sammendrag (YYYY)')
    analyze_parser.add_argument('--trends', help='Prestasjonstrend for aktivitetstype')
    analyze_parser.add_argument('--days', type=int, help='Antall dager for trendanalyse (standard: 90)')
    analyze_parser.add_argument('--records', help='Personlige rekorder (aktivitetstype eller "all")')
    analyze_parser.set_defaults(func=analyze_data)
    
    # Parse argumenter
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Kjør kommando
    args.func(args)

if __name__ == '__main__':
    main() 