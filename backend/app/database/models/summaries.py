from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .base import Base

class DailySummary(Base):
    __tablename__ = 'daily_summaries'
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True)
    
    # Aktivitetssammendrag
    total_activities = Column(Integer, default=0)
    total_distance = Column(Float, default=0.0)  # meter
    total_duration = Column(Float, default=0.0)  # sekunder
    total_calories = Column(Float, default=0.0)
    total_ascent = Column(Float, default=0.0)  # meter
    total_descent = Column(Float, default=0.0)  # meter
    
    # Gjennomsnittsverdier
    avg_heart_rate = Column(Float, nullable=True)  # bpm
    avg_speed = Column(Float, nullable=True)  # m/s
    avg_pace = Column(Float, nullable=True)  # sek/km
    avg_cadence = Column(Float, nullable=True)  # spm
    
    # Aktivitetstyper (JSON for fleksibilitet)
    activity_types_breakdown = Column(JSON, nullable=True)
    
    # Beste prestasjoner for dagen
    best_distance = Column(Float, nullable=True)  # meter
    best_duration = Column(Float, nullable=True)  # sekunder
    best_pace = Column(Float, nullable=True)  # sek/km
    best_speed = Column(Float, nullable=True)  # m/s
    
    # Metadata
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class WeeklySummary(Base):
    __tablename__ = 'weekly_summaries'
    
    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, index=True)
    week_number = Column(Integer, index=True)
    week_start_date = Column(Date)
    week_end_date = Column(Date)
    
    # Aktivitetssammendrag
    total_activities = Column(Integer, default=0)
    total_distance = Column(Float, default=0.0)  # meter
    total_duration = Column(Float, default=0.0)  # sekunder
    total_calories = Column(Float, default=0.0)
    total_ascent = Column(Float, default=0.0)  # meter
    total_descent = Column(Float, default=0.0)  # meter
    
    # Gjennomsnittsverdier
    avg_heart_rate = Column(Float, nullable=True)  # bpm
    avg_speed = Column(Float, nullable=True)  # m/s
    avg_pace = Column(Float, nullable=True)  # sek/km
    avg_cadence = Column(Float, nullable=True)  # spm
    
    # Ukentlige målinger
    activities_per_day = Column(Float, nullable=True)
    distance_per_day = Column(Float, nullable=True)  # meter
    duration_per_day = Column(Float, nullable=True)  # sekunder
    
    # Aktivitetstyper
    activity_types_breakdown = Column(JSON, nullable=True)
    
    # Beste prestasjoner for uken
    best_distance = Column(Float, nullable=True)  # meter
    best_duration = Column(Float, nullable=True)  # sekunder
    best_pace = Column(Float, nullable=True)  # sek/km
    best_speed = Column(Float, nullable=True)  # m/s
    
    # Metadata
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    
    # Unik constraint
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

class MonthlySummary(Base):
    __tablename__ = 'monthly_summaries'
    
    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, index=True)
    month = Column(Integer, index=True)
    month_start_date = Column(Date)
    month_end_date = Column(Date)
    
    # Aktivitetssammendrag
    total_activities = Column(Integer, default=0)
    total_distance = Column(Float, default=0.0)  # meter
    total_duration = Column(Float, default=0.0)  # sekunder
    total_calories = Column(Float, default=0.0)
    total_tss = Column(Float, default=0.0)  # Training Stress Score
    total_ascent = Column(Float, default=0.0)  # meter
    total_descent = Column(Float, default=0.0)  # meter
    
    # Gjennomsnittsverdier
    avg_heart_rate = Column(Float, nullable=True)  # bpm
    avg_speed = Column(Float, nullable=True)  # m/s
    avg_pace = Column(Float, nullable=True)  # sek/km
    avg_cadence = Column(Float, nullable=True)  # spm
    
    # Månedlige målinger
    activities_per_day = Column(Float, nullable=True)
    distance_per_day = Column(Float, nullable=True)  # meter
    duration_per_day = Column(Float, nullable=True)  # sekunder
    activities_per_week = Column(Float, nullable=True)
    distance_per_week = Column(Float, nullable=True)  # meter
    duration_per_week = Column(Float, nullable=True)  # sekunder
    
    # Aktivitetstyper
    activity_types_breakdown = Column(JSON, nullable=True)
    
    # Beste prestasjoner for måneden
    best_distance = Column(Float, nullable=True)  # meter
    best_duration = Column(Float, nullable=True)  # sekunder
    best_pace = Column(Float, nullable=True)  # sek/km
    best_speed = Column(Float, nullable=True)  # m/s
    
    # Trender (sammenligning med forrige måned)
    distance_trend = Column(Float, nullable=True)  # prosent endring
    duration_trend = Column(Float, nullable=True)  # prosent endring
    activities_trend = Column(Float, nullable=True)  # prosent endring
    
    # Metadata
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class YearlySummary(Base):
    __tablename__ = 'yearly_summaries'
    
    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, unique=True, index=True)
    
    # Aktivitetssammendrag
    total_activities = Column(Integer, default=0)
    total_distance = Column(Float, default=0.0)  # meter
    total_duration = Column(Float, default=0.0)  # sekunder
    total_calories = Column(Float, default=0.0)
    total_ascent = Column(Float, default=0.0)  # meter
    total_descent = Column(Float, default=0.0)  # meter
    
    # Gjennomsnittsverdier
    avg_heart_rate = Column(Float, nullable=True)  # bpm
    avg_speed = Column(Float, nullable=True)  # m/s
    avg_pace = Column(Float, nullable=True)  # sek/km
    avg_cadence = Column(Float, nullable=True)  # spm
    
    # Årlige målinger
    activities_per_day = Column(Float, nullable=True)
    distance_per_day = Column(Float, nullable=True)  # meter
    duration_per_day = Column(Float, nullable=True)  # sekunder
    activities_per_week = Column(Float, nullable=True)
    distance_per_week = Column(Float, nullable=True)  # meter
    duration_per_week = Column(Float, nullable=True)  # sekunder
    activities_per_month = Column(Float, nullable=True)
    distance_per_month = Column(Float, nullable=True)  # meter
    duration_per_month = Column(Float, nullable=True)  # sekunder
    
    # Aktivitetstyper
    activity_types_breakdown = Column(JSON, nullable=True)
    
    # Månedlig breakdown
    monthly_breakdown = Column(JSON, nullable=True)
    
    # Beste prestasjoner for året
    best_distance = Column(Float, nullable=True)  # meter
    best_duration = Column(Float, nullable=True)  # sekunder
    best_pace = Column(Float, nullable=True)  # sek/km
    best_speed = Column(Float, nullable=True)  # m/s
    
    # Trender (sammenligning med forrige år)
    distance_trend = Column(Float, nullable=True)  # prosent endring
    duration_trend = Column(Float, nullable=True)  # prosent endring
    activities_trend = Column(Float, nullable=True)  # prosent endring
    
    # Metadata
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class PersonalRecord(Base):
    __tablename__ = 'personal_records'
    
    id = Column(Integer, primary_key=True, index=True)
    record_type = Column(String(100), index=True)  # 'distance', 'duration', 'speed', etc.
    activity_type_id = Column(Integer, ForeignKey('activity_types.id'), nullable=True)
    
    # Rekordverdier
    value = Column(Float)
    unit = Column(String(20))  # 'meter', 'sekunder', 'm/s', etc.
    
    # Aktivitetsreferanse
    activity_id = Column(String(255), ForeignKey('activities.activity_id'))
    achieved_date = Column(Date)
    
    # Metadata
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    
    # Relasjoner
    activity = relationship("Activity")
    activity_type = relationship("ActivityType") 