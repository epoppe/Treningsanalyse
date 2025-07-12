"""
Avanserte analyse-funksjoner for treningsdata.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.database.models.activity import Activity
from app.database.session import SessionLocal

class AdvancedAnalysis:
    """Avanserte analyse-funksjoner."""
    
    def __init__(self):
        self.db = SessionLocal()
    
    def get_monthly_summary(self, year: int, month: int) -> Dict[str, Any]:
        """Hent månedlig sammendrag."""
        activities = self.db.query(Activity).filter(
            extract('year', Activity.start_time) == year,
            extract('month', Activity.start_time) == month
        ).all()
        
        if not activities:
            return {}
        
        total_distance = sum(a.distance or 0 for a in activities)
        total_duration = sum(a.duration or 0 for a in activities)
        total_calories = sum(a.calories or 0 for a in activities)
        total_ascent = sum(a.total_ascent or 0 for a in activities)
        
        avg_heart_rates = [a.average_heart_rate for a in activities if a.average_heart_rate]
        avg_heart_rate = np.mean(avg_heart_rates) if avg_heart_rates else None
        
        return {
            'year': year,
            'month': month,
            'total_activities': len(activities),
            'total_distance': round(total_distance, 2),
            'total_duration': total_duration,
            'total_calories': total_calories,
            'total_ascent': total_ascent,
            'avg_heart_rate': round(avg_heart_rate, 1) if avg_heart_rate else None,
            'avg_distance_per_activity': round(total_distance / len(activities), 2),
            'avg_duration_per_activity': round(total_duration / len(activities), 0)
        }
    
    def get_yearly_summary(self, year: int) -> Dict[str, Any]:
        """Hent årlig sammendrag."""
        activities = self.db.query(Activity).filter(
            extract('year', Activity.start_time) == year
        ).all()
        
        if not activities:
            return {}
        
        # Gruppér etter aktivitetstype
        activity_types = {}
        for activity in activities:
            type_name = activity.activity_type.type_name if activity.activity_type else 'Ukjent'
            if type_name not in activity_types:
                activity_types[type_name] = {
                    'count': 0,
                    'total_distance': 0,
                    'total_duration': 0,
                    'total_calories': 0
                }
            
            activity_types[type_name]['count'] += 1
            activity_types[type_name]['total_distance'] += activity.distance or 0
            activity_types[type_name]['total_duration'] += activity.duration or 0
            activity_types[type_name]['total_calories'] += activity.calories or 0
        
        # Månedsvis breakdown
        monthly_data = []
        for month in range(1, 13):
            month_summary = self.get_monthly_summary(year, month)
            if month_summary:
                monthly_data.append(month_summary)
        
        return {
            'year': year,
            'total_activities': len(activities),
            'activity_types': activity_types,
            'monthly_breakdown': monthly_data
        }
    
    def get_performance_trends(self, activity_type: str, days: int = 90) -> Dict[str, Any]:
        """Analyser prestasjonstrend for en aktivitetstype."""
        start_date = datetime.now() - timedelta(days=days)
        
        activities = self.db.query(Activity).join(Activity.activity_type).filter(
            Activity.start_time >= start_date,
            Activity.activity_type.has(type_name=activity_type)
        ).order_by(Activity.start_time).all()
        
        if len(activities) < 2:
            return {'error': 'Ikke nok data for trendanalyse'}
        
        # Beregn trendindikatorer
        dates = [a.start_time for a in activities]
        distances = [a.distance or 0 for a in activities]
        durations = [a.duration or 0 for a in activities]
        heart_rates = [a.average_heart_rate for a in activities if a.average_heart_rate]
        
        # Beregn gjennomsnittsfart (kun for aktiviteter med både distanse og varighet)
        speeds = []
        for activity in activities:
            if activity.distance and activity.duration and activity.duration > 0:
                speed = (activity.distance / 1000) / (activity.duration / 3600)  # km/h
                speeds.append(speed)
        
        # Trendanalyse (lineær regresjon)
        def calculate_trend(values):
            if len(values) < 2:
                return 0
            x = np.arange(len(values))
            slope, _ = np.polyfit(x, values, 1)
            return slope
        
        return {
            'activity_type': activity_type,
            'period_days': days,
            'total_activities': len(activities),
            'distance_trend': calculate_trend(distances),
            'duration_trend': calculate_trend(durations),
            'speed_trend': calculate_trend(speeds) if speeds else 0,
            'heart_rate_trend': calculate_trend(heart_rates) if heart_rates else 0,
            'avg_distance': np.mean(distances) if distances else 0,
            'avg_duration': np.mean(durations) if durations else 0,
            'avg_speed': np.mean(speeds) if speeds else 0,
            'avg_heart_rate': np.mean(heart_rates) if heart_rates else 0
        }
    
    def compare_periods(self, period1_start: datetime, period1_end: datetime,
                       period2_start: datetime, period2_end: datetime) -> Dict[str, Any]:
        """Sammenlign to tidsperioder."""
        
        def get_period_stats(start_date, end_date):
            activities = self.db.query(Activity).filter(
                Activity.start_time >= start_date,
                Activity.start_time <= end_date
            ).all()
            
            if not activities:
                return None
            
            return {
                'total_activities': len(activities),
                'total_distance': sum(a.distance or 0 for a in activities),
                'total_duration': sum(a.duration or 0 for a in activities),
                'total_calories': sum(a.calories or 0 for a in activities),
                'avg_heart_rate': np.mean([a.average_heart_rate for a in activities if a.average_heart_rate]) or 0
            }
        
        period1_stats = get_period_stats(period1_start, period1_end)
        period2_stats = get_period_stats(period2_start, period2_end)
        
        if not period1_stats or not period2_stats:
            return {'error': 'Ikke nok data i en eller begge perioder'}
        
        # Beregn endringer
        changes = {}
        for key in ['total_activities', 'total_distance', 'total_duration', 'total_calories', 'avg_heart_rate']:
            if period1_stats[key] > 0:
                change_pct = ((period2_stats[key] - period1_stats[key]) / period1_stats[key]) * 100
                changes[f'{key}_change_pct'] = round(change_pct, 1)
            else:
                changes[f'{key}_change_pct'] = 0
        
        return {
            'period1': {
                'start': period1_start.date(),
                'end': period1_end.date(),
                'stats': period1_stats
            },
            'period2': {
                'start': period2_start.date(),
                'end': period2_end.date(),
                'stats': period2_stats
            },
            'changes': changes
        }
    
    def get_personal_records(self, activity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Finn personlige rekorder."""
        query = self.db.query(Activity)
        
        if activity_type:
            query = query.join(Activity.activity_type).filter(
                Activity.activity_type.has(type_name=activity_type)
            )
        
        activities = query.all()
        
        if not activities:
            return []
        
        records = []
        
        # Lengste distanse
        max_distance_activity = max(activities, key=lambda a: a.distance or 0)
        if max_distance_activity.distance:
            records.append({
                'record_type': 'Lengste distanse',
                'value': max_distance_activity.distance,
                'unit': 'meter',
                'activity_id': max_distance_activity.activity_id,
                'activity_name': max_distance_activity.activity_name,
                'date': max_distance_activity.start_time.date()
            })
        
        # Lengste varighet
        max_duration_activity = max(activities, key=lambda a: a.duration or 0)
        if max_duration_activity.duration:
            records.append({
                'record_type': 'Lengste varighet',
                'value': max_duration_activity.duration,
                'unit': 'sekunder',
                'activity_id': max_duration_activity.activity_id,
                'activity_name': max_duration_activity.activity_name,
                'date': max_duration_activity.start_time.date()
            })
        
        # Høyeste gjennomsnittspuls
        max_hr_activity = max(activities, key=lambda a: a.average_heart_rate or 0)
        if max_hr_activity.average_heart_rate:
            records.append({
                'record_type': 'Høyeste gjennomsnittspuls',
                'value': max_hr_activity.average_heart_rate,
                'unit': 'bpm',
                'activity_id': max_hr_activity.activity_id,
                'activity_name': max_hr_activity.activity_name,
                'date': max_hr_activity.start_time.date()
            })
        
        # Mest høydemeter
        max_ascent_activity = max(activities, key=lambda a: a.total_ascent or 0)
        if max_ascent_activity.total_ascent:
            records.append({
                'record_type': 'Mest høydemeter',
                'value': max_ascent_activity.total_ascent,
                'unit': 'meter',
                'activity_id': max_ascent_activity.activity_id,
                'activity_name': max_ascent_activity.activity_name,
                'date': max_ascent_activity.start_time.date()
            })
        
        return records
    
    def __del__(self):
        """Lukk database-tilkobling."""
        if hasattr(self, 'db'):
            self.db.close()

# Global analysis service
advanced_analysis = AdvancedAnalysis() 