from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean, Text, Index
from sqlalchemy.orm import relationship
from .base import Base

class Activity(Base):
    __tablename__ = 'activities'
    
    # Sammensatte indekser for ytelse
    __table_args__ = (
        # Eksisterende indekser
        Index('idx_start_time_activity_type', 'start_time', 'activity_type_id'),
        Index('idx_duration_distance', 'duration', 'distance'),
        Index('idx_epoc_tss', 'epoc', 'training_stress_score'),
        Index('idx_start_time_desc', 'start_time'),  # For DESC ordering
        
        # Nye indekser for bulk operations og queries
        Index('idx_activity_type_start_time', 'activity_type_id', 'start_time'),  # For type-filtrerte queries
        Index('idx_start_time_range', 'start_time', 'end_time'),  # For tidsperiode-queries
        Index('idx_power_null', 'average_power'),  # For å finne aktiviteter som mangler power
        Index('idx_tss_null', 'training_stress_score'),  # For å finne aktiviteter som mangler TSS
        Index('idx_vo2max', 'vo2_max'),  # For VO2max queries
        Index('idx_distance_duration', 'distance', 'duration', 'start_time'),  # Composite for statistikk
    )

    # Primærnøkkel - bruker Garmin activity ID
    activity_id = Column(String(255), primary_key=True, index=True)
    
    # Grunnleggende aktivitetsinfo
    activity_name = Column(String(255))
    description = Column(Text, nullable=True)
    start_time = Column(DateTime, index=True)
    end_time = Column(DateTime, nullable=True)
    
    # Målinger
    distance = Column(Float, nullable=True, index=True)  # meter - nå indeksert
    duration = Column(Float, nullable=True, index=True)  # sekunder - nå indeksert
    moving_duration = Column(Float, nullable=True)  # sekunder
    elapsed_duration = Column(Float, nullable=True)  # sekunder
    calories = Column(Float, nullable=True)
    
    # Hastighet og tempo
    average_speed = Column(Float, nullable=True)  # m/s
    max_speed = Column(Float, nullable=True)  # m/s
    average_pace = Column(Float, nullable=True)  # sek/km
    
    # Puls
    average_heart_rate = Column(Float, nullable=True)  # bpm
    max_heart_rate = Column(Float, nullable=True)  # bpm
    min_heart_rate = Column(Float, nullable=True)  # bpm
    
    # Kadanse og steg
    average_running_cadence = Column(Float, nullable=True)  # spm
    max_running_cadence = Column(Float, nullable=True)  # spm
    total_steps = Column(Integer, nullable=True)
    
    # Høyde og gradient
    total_ascent = Column(Float, nullable=True)  # meter
    total_descent = Column(Float, nullable=True)  # meter
    min_elevation = Column(Float, nullable=True)  # meter
    max_elevation = Column(Float, nullable=True)  # meter
    
    # Effekt (for sykling)
    average_power = Column(Float, nullable=True)  # watt
    max_power = Column(Float, nullable=True)  # watt
    normalized_power = Column(Float, nullable=True)  # watt
    
    # Treningsbelastning
    training_stress_score = Column(Float, nullable=True)
    intensity_factor = Column(Float, nullable=True)
    total_training_effect = Column(Float, nullable=True)  # Aerobic Training Effect (1.0-5.0)
    total_anaerobic_training_effect = Column(Float, nullable=True)  # Anaerobic Training Effect (1.0-5.0)
    epoc = Column(Float, nullable=True)  # Exercise Post Oxygen Consumption (Training Load)
    
    # Fysiologiske målinger
    vo2_max = Column(Float, nullable=True)
    lactate_threshold_heart_rate = Column(Float, nullable=True)
    lactate_threshold_speed = Column(Float, nullable=True)  # m/s
    recovery_time = Column(Integer, nullable=True)  # timer
    
    # Værforhold
    weather_condition = Column(String(100), nullable=True)
    temperature = Column(Float, nullable=True)  # celsius
    humidity = Column(Float, nullable=True)  # prosent
    wind_speed = Column(Float, nullable=True)  # m/s
    
    # Cache for beregnede verdier
    negative_split_percent = Column(Float, nullable=True)
    running_economy = Column(Float, nullable=True)
    decoupling_percent = Column(Float, nullable=True)
    avg_efficiency_factor = Column(Float, nullable=True)
    median_efficiency_factor = Column(Float, nullable=True)
    steady_state_efficiency_factor = Column(Float, nullable=True)
    efficiency_data_quality = Column(Float, nullable=True)
    decoupling_suitability_flag = Column(String(50), nullable=True)
    decoupling_reason_if_unsuitable = Column(String(255), nullable=True)
    decoupling_data_quality_score = Column(Float, nullable=True)
    fatigue_resistance_score = Column(Float, nullable=True)
    pace_drop_pct = Column(Float, nullable=True)
    hr_drift_pct = Column(Float, nullable=True)
    cadence_drop_pct = Column(Float, nullable=True)
    ef_drop_pct = Column(Float, nullable=True)
    training_readiness_score = Column(Float, nullable=True)  # Training readiness score (0-100)
    body_battery_start = Column(Float, nullable=True)  # Body Battery ved start av aktivitet (0-100)
    
    # Metadata
    device_name = Column(String(100), nullable=True)
    activity_type_id = Column(Integer, ForeignKey('activity_types.id'))
    has_detailed_data = Column(Boolean, default=False)
    
    # JSON for utvidet data
    detailed_metrics = Column(JSON, nullable=True)
    
    # Relasjoner
    activity_type = relationship("ActivityType", back_populates="activities")
    laps = relationship("ActivityLap", back_populates="activity", cascade="all, delete-orphan")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ActivityType(Base):
    __tablename__ = 'activity_types'

    id = Column(Integer, primary_key=True, index=True)
    type_key = Column(String(100), unique=True, index=True)
    type_name = Column(String(100))
    parent_type_key = Column(String(100), nullable=True)
    
    # Relasjoner
    activities = relationship("Activity", back_populates="activity_type")

class ActivityLap(Base):
    __tablename__ = 'activity_laps'
    
    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(String(255), ForeignKey('activities.activity_id'))
    lap_number = Column(Integer)
    
    # Lap-målinger
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration = Column(Float)  # sekunder
    distance = Column(Float, nullable=True)  # meter
    
    # Hastighet og tempo
    average_speed = Column(Float, nullable=True)  # m/s
    max_speed = Column(Float, nullable=True)  # m/s
    
    # Puls
    average_heart_rate = Column(Float, nullable=True)  # bpm
    max_heart_rate = Column(Float, nullable=True)  # bpm
    
    # Kadanse
    average_cadence = Column(Float, nullable=True)  # spm
    max_cadence = Column(Float, nullable=True)  # spm
    
    # Høyde
    total_ascent = Column(Float, nullable=True)  # meter
    total_descent = Column(Float, nullable=True)  # meter
    
    # Effekt
    average_power = Column(Float, nullable=True)  # watt
    max_power = Column(Float, nullable=True)  # watt
    
    # Kalorier
    calories = Column(Float, nullable=True)
    
    # Relasjoner
    activity = relationship("Activity", back_populates="laps")


class AnalyticsSnapshot(Base):
    __tablename__ = 'analytics_snapshots'

    id = Column(Integer, primary_key=True, index=True)
    metric_key = Column(String(100), unique=True, nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    calculated_at = Column(DateTime, nullable=True)
    data_quality_score = Column(Float, nullable=True)
    model_quality = Column(String(50), nullable=True)
