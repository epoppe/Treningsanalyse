"""
Service for å beregne og oppdatere sammendragstabeller.
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_

from app.database.session import SessionLocal
from app.database.models.activity import Activity, ActivityType
from app.database.models.summaries import DailySummary, WeeklySummary, MonthlySummary, YearlySummary, PersonalRecord
import json

class SummaryService:
    """Service for å beregne sammendrag av treningsdata."""
    
    def __init__(self):
        self.db = SessionLocal()
    
    def calculate_daily_summary(self, target_date: date) -> DailySummary:
        """Beregn daglig sammendrag for en spesifikk dato."""
        
        # Hent alle aktiviteter for dagen
        activities = self.db.query(Activity).filter(
            func.date(Activity.start_time) == target_date
        ).all()
        
        if not activities:
            return None
        
        # Beregn totaler
        total_distance = sum(a.distance or 0 for a in activities)
        total_duration = sum(a.duration or 0 for a in activities)
        total_calories = sum(a.calories or 0 for a in activities)
        total_ascent = sum(a.total_ascent or 0 for a in activities)
        total_descent = sum(a.total_descent or 0 for a in activities)
        
        # Beregn gjennomsnitt
        heart_rates = [a.average_heart_rate for a in activities if a.average_heart_rate]
        speeds = [a.average_speed for a in activities if a.average_speed]
        
        # Beregn pace - bruk eksisterende pace eller beregn fra speed
        paces = []
        for a in activities:
            if a.average_pace:
                paces.append(a.average_pace)
            elif a.average_speed and a.average_speed > 0:
                # Beregn pace fra speed: pace (sek/km) = 1000 / speed (m/s)
                calculated_pace = 1000 / a.average_speed
                paces.append(calculated_pace)
        
        cadences = [a.average_running_cadence for a in activities if a.average_running_cadence]
        
        avg_heart_rate = sum(heart_rates) / len(heart_rates) if heart_rates else None
        avg_speed = sum(speeds) / len(speeds) if speeds else None
        avg_pace = sum(paces) / len(paces) if paces else None
        avg_cadence = sum(cadences) / len(cadences) if cadences else None
        
        # Aktivitetstype breakdown
        activity_types = {}
        for activity in activities:
            type_name = activity.activity_type.type_name if activity.activity_type else 'Ukjent'
            if type_name not in activity_types:
                activity_types[type_name] = {
                    'count': 0,
                    'distance': 0,
                    'duration': 0,
                    'calories': 0
                }
            activity_types[type_name]['count'] += 1
            activity_types[type_name]['distance'] += activity.distance or 0
            activity_types[type_name]['duration'] += activity.duration or 0
            activity_types[type_name]['calories'] += activity.calories or 0
        
        # Beste prestasjoner
        best_distance = max(a.distance or 0 for a in activities)
        best_duration = max(a.duration or 0 for a in activities)
        best_speed = max(a.average_speed or 0 for a in activities)
        pace_values = [a.average_pace for a in activities if a.average_pace]
        best_pace = min(pace_values) if pace_values else None
        
        # Sjekk om det allerede finnes et sammendrag for denne dagen
        existing_summary = self.db.query(DailySummary).filter(
            DailySummary.date == target_date
        ).first()
        
        if existing_summary:
            # Oppdater eksisterende
            existing_summary.total_activities = len(activities)
            existing_summary.total_distance = total_distance
            existing_summary.total_duration = total_duration
            existing_summary.total_calories = total_calories
            existing_summary.total_ascent = total_ascent
            existing_summary.total_descent = total_descent
            existing_summary.avg_heart_rate = avg_heart_rate
            existing_summary.avg_speed = avg_speed
            existing_summary.avg_pace = avg_pace
            existing_summary.avg_cadence = avg_cadence
            existing_summary.activity_types_breakdown = json.dumps(activity_types)
            existing_summary.best_distance = best_distance
            existing_summary.best_duration = best_duration
            existing_summary.best_speed = best_speed
            existing_summary.best_pace = best_pace if best_pace != float('inf') else None
            existing_summary.updated_at = datetime.now()
            
            summary = existing_summary
        else:
            # Opprett nytt
            summary = DailySummary(
                date=target_date,
                total_activities=len(activities),
                total_distance=total_distance,
                total_duration=total_duration,
                total_calories=total_calories,
                total_ascent=total_ascent,
                total_descent=total_descent,
                avg_heart_rate=avg_heart_rate,
                avg_speed=avg_speed,
                avg_pace=avg_pace,
                avg_cadence=avg_cadence,
                activity_types_breakdown=json.dumps(activity_types),
                best_distance=best_distance,
                best_duration=best_duration,
                best_speed=best_speed,
                best_pace=best_pace if best_pace != float('inf') else None,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.db.add(summary)
        
        self.db.commit()
        return summary
    
    def calculate_weekly_summary(self, year: int, week_number: int) -> WeeklySummary:
        """Beregn ukentlig sammendrag."""
        
        # Beregn ukedatoer
        jan_1 = date(year, 1, 1)
        week_start = jan_1 + timedelta(weeks=week_number-1)
        week_start = week_start - timedelta(days=week_start.weekday())  # Mandag
        week_end = week_start + timedelta(days=6)  # Søndag
        
        # Hent aktiviteter for uken
        activities = self.db.query(Activity).filter(
            and_(
                func.date(Activity.start_time) >= week_start,
                func.date(Activity.start_time) <= week_end
            )
        ).all()
        
        if not activities:
            return None
        
        # Beregn totaler (samme logikk som daglig)
        total_distance = sum(a.distance or 0 for a in activities)
        total_duration = sum(a.duration or 0 for a in activities)
        total_calories = sum(a.calories or 0 for a in activities)
        total_ascent = sum(a.total_ascent or 0 for a in activities)
        total_descent = sum(a.total_descent or 0 for a in activities)
        
        # Beregn gjennomsnitt
        heart_rates = [a.average_heart_rate for a in activities if a.average_heart_rate]
        speeds = [a.average_speed for a in activities if a.average_speed]
        
        # Beregn pace - bruk eksisterende pace eller beregn fra speed
        paces = []
        for a in activities:
            if a.average_pace:
                paces.append(a.average_pace)
            elif a.average_speed and a.average_speed > 0:
                # Beregn pace fra speed: pace (sek/km) = 1000 / speed (m/s)
                calculated_pace = 1000 / a.average_speed
                paces.append(calculated_pace)
        
        cadences = [a.average_running_cadence for a in activities if a.average_running_cadence]
        
        avg_heart_rate = sum(heart_rates) / len(heart_rates) if heart_rates else None
        avg_speed = sum(speeds) / len(speeds) if speeds else None
        avg_pace = sum(paces) / len(paces) if paces else None
        avg_cadence = sum(cadences) / len(cadences) if cadences else None
        
        # Ukentlige beregninger
        activities_per_day = len(activities) / 7
        distance_per_day = total_distance / 7
        duration_per_day = total_duration / 7
        
        # Aktivitetstype breakdown
        activity_types = {}
        for activity in activities:
            type_name = activity.activity_type.type_name if activity.activity_type else 'Ukjent'
            if type_name not in activity_types:
                activity_types[type_name] = {
                    'count': 0,
                    'distance': 0,
                    'duration': 0,
                    'calories': 0
                }
            activity_types[type_name]['count'] += 1
            activity_types[type_name]['distance'] += activity.distance or 0
            activity_types[type_name]['duration'] += activity.duration or 0
            activity_types[type_name]['calories'] += activity.calories or 0
        
        # Beste prestasjoner
        best_distance = max(a.distance or 0 for a in activities)
        best_duration = max(a.duration or 0 for a in activities)
        best_speed = max(a.average_speed or 0 for a in activities)
        pace_values = [a.average_pace for a in activities if a.average_pace]
        best_pace = min(pace_values) if pace_values else None
        
        # Sjekk om det allerede finnes et sammendrag
        existing_summary = self.db.query(WeeklySummary).filter(
            and_(
                WeeklySummary.year == year,
                WeeklySummary.week_number == week_number
            )
        ).first()
        
        if existing_summary:
            # Oppdater eksisterende
            existing_summary.total_activities = len(activities)
            existing_summary.total_distance = total_distance
            existing_summary.total_duration = total_duration
            existing_summary.total_calories = total_calories
            existing_summary.total_ascent = total_ascent
            existing_summary.total_descent = total_descent
            existing_summary.avg_heart_rate = avg_heart_rate
            existing_summary.avg_speed = avg_speed
            existing_summary.avg_pace = avg_pace
            existing_summary.avg_cadence = avg_cadence
            existing_summary.activities_per_day = activities_per_day
            existing_summary.distance_per_day = distance_per_day
            existing_summary.duration_per_day = duration_per_day
            existing_summary.activity_types_breakdown = json.dumps(activity_types)
            existing_summary.best_distance = best_distance
            existing_summary.best_duration = best_duration
            existing_summary.best_speed = best_speed
            existing_summary.best_pace = best_pace if best_pace != float('inf') else None
            existing_summary.updated_at = datetime.now()
            
            summary = existing_summary
        else:
            # Opprett nytt
            summary = WeeklySummary(
                year=year,
                week_number=week_number,
                week_start_date=week_start,
                week_end_date=week_end,
                total_activities=len(activities),
                total_distance=total_distance,
                total_duration=total_duration,
                total_calories=total_calories,
                total_ascent=total_ascent,
                total_descent=total_descent,
                avg_heart_rate=avg_heart_rate,
                avg_speed=avg_speed,
                avg_pace=avg_pace,
                avg_cadence=avg_cadence,
                activities_per_day=activities_per_day,
                distance_per_day=distance_per_day,
                duration_per_day=duration_per_day,
                activity_types_breakdown=json.dumps(activity_types),
                best_distance=best_distance,
                best_duration=best_duration,
                best_speed=best_speed,
                best_pace=best_pace if best_pace != float('inf') else None,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.db.add(summary)
        
        self.db.commit()
        return summary
    
    def calculate_monthly_summary(self, year: int, month: int) -> MonthlySummary:
        """Beregn månedlig sammendrag."""
        
        # Hent aktiviteter for måneden
        activities = self.db.query(Activity).filter(
            and_(
                extract('year', Activity.start_time) == year,
                extract('month', Activity.start_time) == month
            )
        ).all()
        
        if not activities:
            return None
        
        # Samme beregningslogikk som ukentlig, men med månedlige beregninger
        total_distance = sum(a.distance or 0 for a in activities)
        total_duration = sum(a.duration or 0 for a in activities)
        total_calories = sum(a.calories or 0 for a in activities)
        total_ascent = sum(a.total_ascent or 0 for a in activities)
        total_descent = sum(a.total_descent or 0 for a in activities)
        
        # Beregn gjennomsnitt
        heart_rates = [a.average_heart_rate for a in activities if a.average_heart_rate]
        speeds = [a.average_speed for a in activities if a.average_speed]
        
        # Beregn pace - bruk eksisterende pace eller beregn fra speed
        paces = []
        for a in activities:
            if a.average_pace:
                paces.append(a.average_pace)
            elif a.average_speed and a.average_speed > 0:
                # Beregn pace fra speed: pace (sek/km) = 1000 / speed (m/s)
                calculated_pace = 1000 / a.average_speed
                paces.append(calculated_pace)
        
        cadences = [a.average_running_cadence for a in activities if a.average_running_cadence]
        
        avg_heart_rate = sum(heart_rates) / len(heart_rates) if heart_rates else None
        avg_speed = sum(speeds) / len(speeds) if speeds else None
        avg_pace = sum(paces) / len(paces) if paces else None
        avg_cadence = sum(cadences) / len(cadences) if cadences else None
        
        # Beregn månedsdatoer
        import calendar
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        
        # Månedlige beregninger
        days_in_month = calendar.monthrange(year, month)[1]
        activities_per_day = len(activities) / days_in_month
        distance_per_day = total_distance / days_in_month
        duration_per_day = total_duration / days_in_month
        
        # Ukentlige beregninger
        weeks_in_month = days_in_month / 7
        activities_per_week = len(activities) / weeks_in_month
        distance_per_week = total_distance / weeks_in_month
        duration_per_week = total_duration / weeks_in_month
        
        # Aktivitetstype breakdown
        activity_types = {}
        for activity in activities:
            type_name = activity.activity_type.type_name if activity.activity_type else 'Ukjent'
            if type_name not in activity_types:
                activity_types[type_name] = {
                    'count': 0,
                    'distance': 0,
                    'duration': 0,
                    'calories': 0
                }
            activity_types[type_name]['count'] += 1
            activity_types[type_name]['distance'] += activity.distance or 0
            activity_types[type_name]['duration'] += activity.duration or 0
            activity_types[type_name]['calories'] += activity.calories or 0
        
        # Trendberegning (sammenlign med forrige måned)
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        
        prev_summary = self.db.query(MonthlySummary).filter(
            and_(
                MonthlySummary.year == prev_year,
                MonthlySummary.month == prev_month
            )
        ).first()
        
        distance_trend = None
        duration_trend = None
        activities_trend = None
        
        if prev_summary:
            if prev_summary.total_distance > 0:
                distance_trend = ((total_distance - prev_summary.total_distance) / prev_summary.total_distance) * 100
            if prev_summary.total_duration > 0:
                duration_trend = ((total_duration - prev_summary.total_duration) / prev_summary.total_duration) * 100
            if prev_summary.total_activities > 0:
                activities_trend = ((len(activities) - prev_summary.total_activities) / prev_summary.total_activities) * 100
        
        # Sjekk om det allerede finnes et sammendrag
        existing_summary = self.db.query(MonthlySummary).filter(
            and_(
                MonthlySummary.year == year,
                MonthlySummary.month == month
            )
        ).first()
        
        if existing_summary:
            # Oppdater eksisterende
            existing_summary.month_start_date = month_start
            existing_summary.month_end_date = month_end
            existing_summary.total_activities = len(activities)
            existing_summary.total_distance = total_distance
            existing_summary.total_duration = total_duration
            existing_summary.total_calories = total_calories
            existing_summary.total_ascent = total_ascent
            existing_summary.total_descent = total_descent
            existing_summary.avg_heart_rate = avg_heart_rate
            existing_summary.avg_speed = avg_speed
            existing_summary.avg_pace = avg_pace
            existing_summary.avg_cadence = avg_cadence
            existing_summary.activities_per_day = activities_per_day
            existing_summary.distance_per_day = distance_per_day
            existing_summary.duration_per_day = duration_per_day
            existing_summary.activities_per_week = activities_per_week
            existing_summary.distance_per_week = distance_per_week
            existing_summary.duration_per_week = duration_per_week
            existing_summary.activity_types_breakdown = json.dumps(activity_types)
            existing_summary.distance_trend = distance_trend
            existing_summary.duration_trend = duration_trend
            existing_summary.activities_trend = activities_trend
            existing_summary.updated_at = datetime.now()
            
            summary = existing_summary
        else:
            # Opprett nytt
            summary = MonthlySummary(
                year=year,
                month=month,
                month_start_date=month_start,
                month_end_date=month_end,
                total_activities=len(activities),
                total_distance=total_distance,
                total_duration=total_duration,
                total_calories=total_calories,
                total_ascent=total_ascent,
                total_descent=total_descent,
                avg_heart_rate=avg_heart_rate,
                avg_speed=avg_speed,
                avg_pace=avg_pace,
                avg_cadence=avg_cadence,
                activities_per_day=activities_per_day,
                distance_per_day=distance_per_day,
                duration_per_day=duration_per_day,
                activities_per_week=activities_per_week,
                distance_per_week=distance_per_week,
                duration_per_week=duration_per_week,
                activity_types_breakdown=json.dumps(activity_types),
                distance_trend=distance_trend,
                duration_trend=duration_trend,
                activities_trend=activities_trend,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.db.add(summary)
        
        self.db.commit()
        return summary
    
    def update_personal_records(self, activity: Activity):
        """Oppdater personlige rekorder basert på en ny aktivitet."""
        
        records_to_check = [
            ('distance', activity.distance, 'meter'),
            ('duration', activity.duration, 'sekunder'),
            ('speed', activity.average_speed, 'm/s'),
            ('ascent', activity.total_ascent, 'meter')
        ]
        
        for record_type, value, unit in records_to_check:
            if value is None:
                continue
            
            # Sjekk eksisterende rekord
            existing_record = self.db.query(PersonalRecord).filter(
                and_(
                    PersonalRecord.record_type == record_type,
                    PersonalRecord.activity_type_id == activity.activity_type_id
                )
            ).first()
            
            is_new_record = False
            if not existing_record:
                is_new_record = True
            elif record_type == 'speed':
                # Høyere er bedre for hastighet
                is_new_record = value > existing_record.value
            elif record_type == 'pace':
                # Lavere er bedre for tempo
                is_new_record = value < existing_record.value
            else:
                # Høyere er bedre for distanse, varighet, høydemeter
                is_new_record = value > existing_record.value
            
            if is_new_record:
                if existing_record:
                    # Oppdater eksisterende rekord
                    existing_record.value = value
                    existing_record.activity_id = activity.activity_id
                    existing_record.achieved_date = activity.start_time.date()
                    existing_record.updated_at = datetime.now()
                else:
                    # Opprett ny rekord
                    new_record = PersonalRecord(
                        record_type=record_type,
                        activity_type_id=activity.activity_type_id,
                        value=value,
                        unit=unit,
                        activity_id=activity.activity_id,
                        achieved_date=activity.start_time.date(),
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    self.db.add(new_record)
        
        self.db.commit()
    
    def bulk_update_summaries(self, start_date: date, end_date: date):
        """Bulk-oppdater sammendrag for en periode."""
        
        current_date = start_date
        while current_date <= end_date:
            # Daglig sammendrag
            self.calculate_daily_summary(current_date)
            
            # Ukentlig sammendrag (kun på søndager)
            if current_date.weekday() == 6:  # Søndag
                year, week_num, _ = current_date.isocalendar()
                self.calculate_weekly_summary(year, week_num)
            
            # Månedlig sammendrag (kun på siste dag i måneden)
            next_day = current_date + timedelta(days=1)
            if next_day.month != current_date.month:
                self.calculate_monthly_summary(current_date.year, current_date.month)
            
            current_date += timedelta(days=1)
        
        print(f"Sammendrag oppdatert for perioden {start_date} til {end_date}")
    
    def calculate_daily_summaries(self) -> int:
        """Beregn alle daglige sammendrag."""
        count = 0
        
        # Hent alle unike datoer med aktiviteter
        dates = self.db.query(func.date(Activity.start_time)).distinct().all()
        
        for date_tuple in dates:
            date_str = date_tuple[0]
            if date_str:
                # Konverter string til date-objekt
                try:
                    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    summary = self.calculate_daily_summary(target_date)
                    if summary:
                        count += 1
                except ValueError:
                    continue
        
        return count
    
    def calculate_weekly_summaries(self) -> int:
        """Beregn alle ukentlige sammendrag."""
        count = 0
        
        # Hent alle unike år og uker
        year_weeks = self.db.query(
            extract('year', Activity.start_time).label('year'),
            extract('week', Activity.start_time).label('week')
        ).distinct().all()
        
        for year, week in year_weeks:
            if year and week:
                summary = self.calculate_weekly_summary(int(year), int(week))
                if summary:
                    count += 1
        
        return count
    
    def calculate_monthly_summaries(self) -> int:
        """Beregn alle månedlige sammendrag."""
        count = 0
        
        # Hent alle unike år og måneder
        year_months = self.db.query(
            extract('year', Activity.start_time).label('year'),
            extract('month', Activity.start_time).label('month')
        ).distinct().all()
        
        for year, month in year_months:
            if year and month:
                summary = self.calculate_monthly_summary(int(year), int(month))
                if summary:
                    count += 1
        
        return count
    
    def get_daily_summaries(self, start_date: Optional[date] = None, end_date: Optional[date] = None, limit: int = 30) -> List[DailySummary]:
        """Hent daglige sammendrag."""
        query = self.db.query(DailySummary)
        
        if start_date:
            query = query.filter(DailySummary.date >= start_date)
        if end_date:
            query = query.filter(DailySummary.date <= end_date)
        
        return query.order_by(DailySummary.date.desc()).limit(limit).all()
    
    def get_weekly_summaries(self, start_date: Optional[date] = None, end_date: Optional[date] = None, limit: int = 12) -> List[WeeklySummary]:
        """Hent ukentlige sammendrag."""
        query = self.db.query(WeeklySummary)
        
        if start_date:
            query = query.filter(WeeklySummary.week_start_date >= start_date)
        if end_date:
            query = query.filter(WeeklySummary.week_end_date <= end_date)
        
        return query.order_by(WeeklySummary.week_start_date.desc()).limit(limit).all()
    
    def get_monthly_summaries(self, start_date: Optional[date] = None, end_date: Optional[date] = None, limit: int = 12) -> List[MonthlySummary]:
        """Hent månedlige sammendrag."""
        query = self.db.query(MonthlySummary)
        
        if start_date:
            query = query.filter(MonthlySummary.month_start_date >= start_date)
        if end_date:
            query = query.filter(MonthlySummary.month_end_date <= end_date)
        
        return query.order_by(MonthlySummary.month_start_date.desc()).limit(limit).all()

    def __del__(self):
        """Lukk database-tilkobling."""
        if hasattr(self, 'db'):
            self.db.close() 