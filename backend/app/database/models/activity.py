from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from .base import Base

class Activity(Base):
    __tablename__ = 'activities'

    # Primærnøkkel - bruker Garmin activity ID
    activity_id = Column(String(255), primary_key=True, index=True)
    
    # Grunnleggende aktivitetsinfo
    activity_name = Column(String(255))
    description = Column(Text, nullable=True)
    start_time = Column(DateTime, index=True)
    end_time = Column(DateTime, nullable=True)
    
    # Målinger
    distance = Column(Float, nullable=True)  # meter
    duration = Column(Float, nullable=True)  # sekunder
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
    
    # Fysiologiske målinger
    vo2_max = Column(Float, nullable=True)
    lactate_threshold_heart_rate = Column(Float, nullable=True)
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
