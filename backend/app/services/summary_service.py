"""
Service for å beregne og oppdatere sammendragstabeller.
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, extract, and_

from app.database.session import SessionLocal
from app.database.models.activity import Activity, ActivityType
from app.database.models.summaries import DailySummary, WeeklySummary, MonthlySummary, YearlySummary, PersonalRecord
from app.services.activity_metric_backfill import derive_average_pace_sec_per_km
from app.utils.speed_pace import aggregate_speed_pace_from_totals
import calendar
import json

class SummaryService:
    """Service for å beregne sammendrag av treningsdata."""
    
    def __init__(self):
        self.db = SessionLocal()

    def _iter_dates(self, start_date: date, end_date: date):
        current_date = start_date
        while current_date <= end_date:
            yield current_date
            current_date += timedelta(days=1)

    def _period_weeks(self, start_date: date, end_date: date) -> list[tuple[int, int]]:
        seen: set[tuple[int, int]] = set()
        ordered: list[tuple[int, int]] = []
        for current_date in self._iter_dates(start_date, end_date):
            year, week_num, _ = current_date.isocalendar()
            key = (year, week_num)
            if key not in seen:
                seen.add(key)
                ordered.append(key)
        return ordered

    def _period_months(self, start_date: date, end_date: date) -> list[tuple[int, int]]:
        months: list[tuple[int, int]] = []
        year = start_date.year
        month = start_date.month
        while (year, month) <= (end_date.year, end_date.month):
            months.append((year, month))
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        return months

    def _period_years(self, start_date: date, end_date: date) -> list[int]:
        return list(range(start_date.year, end_date.year + 1))

    def _commit_if_requested(self, commit: bool) -> None:
        if commit:
            self.db.commit()

    @staticmethod
    def _aggregate_speed_pace(
        activities: List[Activity],
        total_distance: float,
        total_duration: float,
    ) -> tuple[Optional[float], Optional[float], Dict[str, Optional[float]]]:
        """
        Vektet avg_speed/avg_pace fra total distanse og varighet (ikke aritmetisk snitt per aktivitet).
        """
        avg_speed, avg_pace = aggregate_speed_pace_from_totals(total_distance, total_duration)
        moving_total = sum(a.moving_duration or 0 for a in activities)
        elapsed_total = sum(a.elapsed_duration or a.duration or 0 for a in activities)
        time_basis = {
            "total_duration_s": total_duration if total_duration > 0 else None,
            "moving_duration_s": moving_total if moving_total > 0 else None,
            "elapsed_duration_s": elapsed_total if elapsed_total > 0 else None,
        }
        return avg_speed, avg_pace, time_basis

    @staticmethod
    def _activity_pace_sec_per_km(activity: Activity) -> Optional[float]:
        """Utled pace (s/km) fra lagrede eller avledbare aktivitetsfelter."""
        return derive_average_pace_sec_per_km(
            average_pace=activity.average_pace,
            average_speed=activity.average_speed,
            distance_m=activity.distance,
            duration_s=activity.duration,
        )

    @staticmethod
    def _best_performance_fields(activities: List[Activity]) -> Dict[str, Optional[float]]:
        """Beste distanse, varighet, fart og pace i en aktivitetsliste."""
        best_distance = max(a.distance or 0 for a in activities)
        best_duration = max(a.duration or 0 for a in activities)
        best_speed = max(a.average_speed or 0 for a in activities)
        pace_values = [
            pace
            for activity in activities
            if (pace := SummaryService._activity_pace_sec_per_km(activity)) is not None
        ]
        best_pace = min(pace_values) if pace_values else None
        return {
            "best_distance": best_distance,
            "best_duration": best_duration,
            "best_speed": best_speed,
            "best_pace": best_pace if best_pace != float("inf") else None,
        }
    
    def calculate_daily_summary(self, target_date: date, commit: bool = True) -> DailySummary:
        """Beregn daglig sammendrag for en spesifikk dato."""
        
        # Hent alle aktiviteter for dagen
        activities = self.db.query(Activity).filter(
            func.date(Activity.start_time) == target_date
        ).all()
        
        if not activities:
            return None
        
        # Fjern duplikater basert på activity_id
        unique_activities = {}
        for activity in activities:
            if activity.activity_id not in unique_activities:
                unique_activities[activity.activity_id] = activity
        
        activities = list(unique_activities.values())
        
        # Beregn totaler
        total_distance = sum(a.distance or 0 for a in activities)
        total_duration = sum(a.duration or 0 for a in activities)
        total_calories = sum(a.calories or 0 for a in activities)
        total_ascent = sum(a.total_ascent or 0 for a in activities)
        total_descent = sum(a.total_descent or 0 for a in activities)
        
        # Beregn gjennomsnitt — vektet fra total distanse/varighet
        heart_rates = [a.average_heart_rate for a in activities if a.average_heart_rate]
        cadences = [a.average_running_cadence for a in activities if a.average_running_cadence]

        avg_heart_rate = sum(heart_rates) / len(heart_rates) if heart_rates else None
        avg_speed, avg_pace, _time_basis = self._aggregate_speed_pace(
            activities,
            total_distance,
            total_duration,
        )
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
        
        best_fields = self._best_performance_fields(activities)
        
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
            existing_summary.best_distance = best_fields["best_distance"]
            existing_summary.best_duration = best_fields["best_duration"]
            existing_summary.best_speed = best_fields["best_speed"]
            existing_summary.best_pace = best_fields["best_pace"]
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
                best_distance=best_fields["best_distance"],
                best_duration=best_fields["best_duration"],
                best_speed=best_fields["best_speed"],
                best_pace=best_fields["best_pace"],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.db.add(summary)
        
        self._commit_if_requested(commit)
        return summary
    
    def calculate_weekly_summary(self, year: int, week_number: int, commit: bool = True) -> WeeklySummary:
        """Beregn ukentlig sammendrag."""

        # Bruk ekte ISO-uker slik at uke 1/52/53 rundt årsskifter blir riktig.
        week_start = date.fromisocalendar(year, week_number, 1)
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
        
        # Fjern duplikater basert på activity_id
        unique_activities = {}
        for activity in activities:
            if activity.activity_id not in unique_activities:
                unique_activities[activity.activity_id] = activity
        
        activities = list(unique_activities.values())
        
        # Beregn totaler (samme logikk som daglig)
        total_distance = sum(a.distance or 0 for a in activities)
        total_duration = sum(a.duration or 0 for a in activities)
        total_calories = sum(a.calories or 0 for a in activities)
        total_ascent = sum(a.total_ascent or 0 for a in activities)
        total_descent = sum(a.total_descent or 0 for a in activities)
        
        # Beregn gjennomsnitt — vektet fra total distanse/varighet
        heart_rates = [a.average_heart_rate for a in activities if a.average_heart_rate]
        cadences = [a.average_running_cadence for a in activities if a.average_running_cadence]

        avg_heart_rate = sum(heart_rates) / len(heart_rates) if heart_rates else None
        avg_speed, avg_pace, _time_basis = self._aggregate_speed_pace(
            activities,
            total_distance,
            total_duration,
        )
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
        
        best_fields = self._best_performance_fields(activities)
        
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
            existing_summary.best_distance = best_fields["best_distance"]
            existing_summary.best_duration = best_fields["best_duration"]
            existing_summary.best_speed = best_fields["best_speed"]
            existing_summary.best_pace = best_fields["best_pace"]
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
                best_distance=best_fields["best_distance"],
                best_duration=best_fields["best_duration"],
                best_speed=best_fields["best_speed"],
                best_pace=best_fields["best_pace"],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.db.add(summary)
        
        self._commit_if_requested(commit)
        return summary
    
    def calculate_monthly_summary(self, year: int, month: int, commit: bool = True) -> MonthlySummary:
        """Beregn månedlig sammendrag."""
        
        # Hent aktiviteter for måneden (med eager loading av activity_type)
        activities = self.db.query(Activity).options(
            joinedload(Activity.activity_type)
        ).filter(
            and_(
                extract('year', Activity.start_time) == year,
                extract('month', Activity.start_time) == month
            )
        ).all()
        
        if not activities:
            return None
        
        # Fjern duplikater basert på activity_id
        unique_activities = {}
        for activity in activities:
            if activity.activity_id not in unique_activities:
                unique_activities[activity.activity_id] = activity
        
        activities = list(unique_activities.values())
        
        # Samme beregningslogikk som ukentlig, men med månedlige beregninger
        total_distance = sum(a.distance or 0 for a in activities)
        total_duration = sum(a.duration or 0 for a in activities)
        total_calories = sum(a.calories or 0 for a in activities)
        total_tss = sum(a.training_stress_score or 0 for a in activities)
        total_ascent = sum(a.total_ascent or 0 for a in activities)
        total_descent = sum(a.total_descent or 0 for a in activities)
        
        # Beregn gjennomsnitt — vektet fra total distanse/varighet
        heart_rates = [a.average_heart_rate for a in activities if a.average_heart_rate]
        cadences = [a.average_running_cadence for a in activities if a.average_running_cadence]

        avg_heart_rate = sum(heart_rates) / len(heart_rates) if heart_rates else None
        avg_speed, avg_pace, _time_basis = self._aggregate_speed_pace(
            activities,
            total_distance,
            total_duration,
        )
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
            # Bruk type_key fra activity_type relasjon (type_name er ikke populert i databasen)
            type_name = None
            if hasattr(activity, 'activity_type') and activity.activity_type:
                type_name = activity.activity_type.type_key or activity.activity_type.type_name
            elif hasattr(activity, 'activity_type_name') and activity.activity_type_name:
                type_name = activity.activity_type_name
            
            # Fallback til 'Ukjent' hvis ingenting er satt
            if not type_name or type_name == 'None' or type_name == '':
                type_name = 'Ukjent'
                
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

        best_fields = self._best_performance_fields(activities)
        
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
            existing_summary.total_tss = total_tss
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
            existing_summary.best_distance = best_fields["best_distance"]
            existing_summary.best_duration = best_fields["best_duration"]
            existing_summary.best_speed = best_fields["best_speed"]
            existing_summary.best_pace = best_fields["best_pace"]
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
                total_tss=total_tss,
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
                best_distance=best_fields["best_distance"],
                best_duration=best_fields["best_duration"],
                best_speed=best_fields["best_speed"],
                best_pace=best_fields["best_pace"],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.db.add(summary)
        
        self._commit_if_requested(commit)
        return summary

    def calculate_yearly_summary(self, year: int, commit: bool = True) -> Optional[YearlySummary]:
        """Beregn årlig sammendrag fra aktiviteter (samme mønster som månedlig)."""
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(extract("year", Activity.start_time) == year)
            .all()
        )

        if not activities:
            return None

        unique_activities: dict[str, Activity] = {}
        for activity in activities:
            if activity.activity_id not in unique_activities:
                unique_activities[activity.activity_id] = activity
        activities = list(unique_activities.values())

        total_distance = sum(a.distance or 0 for a in activities)
        total_duration = sum(a.duration or 0 for a in activities)
        total_calories = sum(a.calories or 0 for a in activities)
        total_ascent = sum(a.total_ascent or 0 for a in activities)
        total_descent = sum(a.total_descent or 0 for a in activities)

        heart_rates = [a.average_heart_rate for a in activities if a.average_heart_rate]
        cadences = [a.average_running_cadence for a in activities if a.average_running_cadence]

        avg_heart_rate = sum(heart_rates) / len(heart_rates) if heart_rates else None
        avg_speed, avg_pace, _time_basis = self._aggregate_speed_pace(
            activities,
            total_distance,
            total_duration,
        )
        avg_cadence = sum(cadences) / len(cadences) if cadences else None

        days_in_year = 366 if calendar.isleap(year) else 365
        activities_per_day = len(activities) / days_in_year
        distance_per_day = total_distance / days_in_year
        duration_per_day = total_duration / days_in_year

        weeks_in_year = days_in_year / 7
        activities_per_week = len(activities) / weeks_in_year
        distance_per_week = total_distance / weeks_in_year
        duration_per_week = total_duration / weeks_in_year

        months_in_year = 12
        activities_per_month = len(activities) / months_in_year
        distance_per_month = total_distance / months_in_year
        duration_per_month = total_duration / months_in_year

        activity_types = {}
        for activity in activities:
            type_name = None
            if hasattr(activity, "activity_type") and activity.activity_type:
                type_name = activity.activity_type.type_key or activity.activity_type.type_name
            elif hasattr(activity, "activity_type_name") and activity.activity_type_name:
                type_name = activity.activity_type_name
            if not type_name or type_name == "None" or type_name == "":
                type_name = "Ukjent"
            if type_name not in activity_types:
                activity_types[type_name] = {"count": 0, "distance": 0, "duration": 0, "calories": 0}
            activity_types[type_name]["count"] += 1
            activity_types[type_name]["distance"] += activity.distance or 0
            activity_types[type_name]["duration"] += activity.duration or 0
            activity_types[type_name]["calories"] += activity.calories or 0

        monthly_rows = (
            self.db.query(MonthlySummary)
            .filter(MonthlySummary.year == year)
            .order_by(MonthlySummary.month.asc())
            .all()
        )
        monthly_breakdown = [
            {
                "month": row.month,
                "total_activities": row.total_activities,
                "total_distance": row.total_distance,
                "total_duration": row.total_duration,
                "total_calories": row.total_calories,
            }
            for row in monthly_rows
        ]

        prev_summary = self.db.query(YearlySummary).filter(YearlySummary.year == year - 1).first()
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

        best_fields = self._best_performance_fields(activities)

        existing_summary = self.db.query(YearlySummary).filter(YearlySummary.year == year).first()
        summary_fields = {
            "total_activities": len(activities),
            "total_distance": total_distance,
            "total_duration": total_duration,
            "total_calories": total_calories,
            "total_ascent": total_ascent,
            "total_descent": total_descent,
            "avg_heart_rate": avg_heart_rate,
            "avg_speed": avg_speed,
            "avg_pace": avg_pace,
            "avg_cadence": avg_cadence,
            "activities_per_day": activities_per_day,
            "distance_per_day": distance_per_day,
            "duration_per_day": duration_per_day,
            "activities_per_week": activities_per_week,
            "distance_per_week": distance_per_week,
            "duration_per_week": duration_per_week,
            "activities_per_month": activities_per_month,
            "distance_per_month": distance_per_month,
            "duration_per_month": duration_per_month,
            "activity_types_breakdown": json.dumps(activity_types),
            "monthly_breakdown": monthly_breakdown or None,
            "best_distance": best_fields["best_distance"],
            "best_duration": best_fields["best_duration"],
            "best_speed": best_fields["best_speed"],
            "best_pace": best_fields["best_pace"],
            "distance_trend": distance_trend,
            "duration_trend": duration_trend,
            "activities_trend": activities_trend,
            "updated_at": datetime.now(),
        }

        if existing_summary:
            for field, value in summary_fields.items():
                setattr(existing_summary, field, value)
            summary = existing_summary
        else:
            summary = YearlySummary(
                year=year,
                created_at=datetime.now(),
                **summary_fields,
            )
            self.db.add(summary)

        self._commit_if_requested(commit)
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
    
    def bulk_update_summaries(self, start_date: date, end_date: date) -> Dict[str, int]:
        """Bulk-oppdater sammendrag for en periode med kun berørte dager, uker, måneder og år."""
        daily_count = 0
        weekly_count = 0
        monthly_count = 0
        yearly_count = 0

        for current_date in self._iter_dates(start_date, end_date):
            if self.calculate_daily_summary(current_date, commit=False):
                daily_count += 1

        for year, week_num in self._period_weeks(start_date, end_date):
            if self.calculate_weekly_summary(year, week_num, commit=False):
                weekly_count += 1

        for year, month in self._period_months(start_date, end_date):
            if self.calculate_monthly_summary(year, month, commit=False):
                monthly_count += 1

        for year in self._period_years(start_date, end_date):
            if self.calculate_yearly_summary(year, commit=False):
                yearly_count += 1

        self.db.commit()

        print(
            f"Sammendrag oppdatert for perioden {start_date} til {end_date} "
            f"(dag={daily_count}, uke={weekly_count}, måned={monthly_count}, år={yearly_count})"
        )
        return {
            "daily_count": daily_count,
            "weekly_count": weekly_count,
            "monthly_count": monthly_count,
            "yearly_count": yearly_count,
        }
    
    def calculate_daily_summaries(self) -> int:
        """Beregn alle daglige sammendrag."""
        count = 0
        
        # Hent alle unike datoer med aktiviteter (fjern duplikater basert på activity_id)
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
        
        # Hent alle unike år og uker (fjern duplikater basert på activity_id)
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
        
        # Hent alle unike år og måneder (fjern duplikater basert på activity_id)
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

    def calculate_yearly_summaries(self) -> int:
        """Beregn alle årlige sammendrag (nødvendig for year-over-year-trender)."""
        count = 0
        years = self.db.query(extract("year", Activity.start_time).label("year")).distinct().all()
        for (year,) in years:
            if year:
                summary = self.calculate_yearly_summary(int(year))
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
