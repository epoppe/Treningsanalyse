from sqlalchemy import Column, Integer, String, Float, DateTime, Date, JSON, Boolean
from sqlalchemy.orm import relationship
from .base import Base

class Sleep(Base):
    __tablename__ = 'sleep'
    
    id = Column(Integer, primary_key=True, index=True)
    sleep_date = Column(Date, unique=True, index=True)
    
    # Søvntider
    bedtime = Column(DateTime, nullable=True)
    wake_time = Column(DateTime, nullable=True)
    
    # Søvnvarighet (i sekunder)
    total_sleep_time = Column(Float, nullable=True)  # sekunder
    deep_sleep_time = Column(Float, nullable=True)  # sekunder
    light_sleep_time = Column(Float, nullable=True)  # sekunder
    rem_sleep_time = Column(Float, nullable=True)  # sekunder
    awake_time = Column(Float, nullable=True)  # sekunder
    
    # Søvnkvalitet
    sleep_score = Column(Float, nullable=True)  # 0-100
    sleep_quality = Column(String(20), nullable=True)  # 'excellent', 'good', 'fair', 'poor'
    
    # Søvnfaser (prosent)
    deep_sleep_percent = Column(Float, nullable=True)
    light_sleep_percent = Column(Float, nullable=True)
    rem_sleep_percent = Column(Float, nullable=True)
    awake_percent = Column(Float, nullable=True)
    
    # Søvnmønster
    sleep_efficiency = Column(Float, nullable=True)  # prosent
    sleep_latency = Column(Float, nullable=True)  # sekunder til å sovne
    wake_episodes = Column(Integer, nullable=True)  # antall oppvåkninger
    
    # Fysiologiske målinger
    average_heart_rate = Column(Float, nullable=True)  # bpm
    lowest_heart_rate = Column(Float, nullable=True)  # bpm
    highest_heart_rate = Column(Float, nullable=True)  # bpm
    heart_rate_variability = Column(Float, nullable=True)  # ms
    
    # Oksygenmetning
    average_spo2 = Column(Float, nullable=True)  # prosent
    lowest_spo2 = Column(Float, nullable=True)  # prosent
    
    # Pust
    average_respiration_rate = Column(Float, nullable=True)  # åndedretter per minutt
    
    # Stress og restitusjon
    stress_score = Column(Float, nullable=True)  # 0-100
    recovery_score = Column(Float, nullable=True)  # 0-100
    
    # Bevegelse
    movement_score = Column(Float, nullable=True)  # 0-100
    restless_moments = Column(Integer, nullable=True)
    
    # Metadata
    device_name = Column(String(100), nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    
    # Detaljerte data (JSON for fleksibilitet)
    detailed_sleep_data = Column(JSON, nullable=True)

class SleepStage(Base):
    __tablename__ = 'sleep_stages'
    
    id = Column(Integer, primary_key=True, index=True)
    sleep_date = Column(Date, index=True)
    
    # Tidspunkt og varighet
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration = Column(Float)  # sekunder
    
    # Søvnfase
    stage = Column(String(20))  # 'deep', 'light', 'rem', 'awake'
    
    # Fysiologiske data
    heart_rate = Column(Float, nullable=True)  # bpm
    heart_rate_variability = Column(Float, nullable=True)  # ms
    respiration_rate = Column(Float, nullable=True)  # åndedretter per minutt
    spo2 = Column(Float, nullable=True)  # prosent
    
    # Bevegelse
    movement_intensity = Column(Float, nullable=True)  # 0-100
    
    # Metadata
    created_at = Column(DateTime)

class HRV(Base):
    __tablename__ = 'hrv'
    
    id = Column(Integer, primary_key=True, index=True)
    measurement_date = Column(Date, index=True)
    measurement_time = Column(DateTime)
    
    # HRV-målinger
    rmssd = Column(Float, nullable=True)  # ms
    pnn50 = Column(Float, nullable=True)  # prosent
    stress_score = Column(Float, nullable=True)  # 0-100
    
    # Baseline-verdier fra Garmin
    baseline_balanced_lower = Column(Float, nullable=True)  # ms
    baseline_balanced_upper = Column(Float, nullable=True)  # ms
    baseline_low_upper = Column(Float, nullable=True)  # ms
    status = Column(String(50), nullable=True)  # HRV status fra Garmin
    
    # Kontekst
    measurement_type = Column(String(50), nullable=True)  # 'morning', 'during_sleep', 'activity'
    activity_id = Column(String(255), nullable=True)  # referanse til aktivitet hvis relevant
    
    # Fysiologiske data
    heart_rate = Column(Float, nullable=True)  # bpm
    breathing_rate = Column(Float, nullable=True)  # åndedretter per minutt
    
    # Kvalitet
    measurement_quality = Column(String(20), nullable=True)  # 'excellent', 'good', 'fair', 'poor'
    measurement_duration = Column(Float, nullable=True)  # sekunder
    
    # Metadata
    device_name = Column(String(100), nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class RestingHeartRate(Base):
    __tablename__ = 'resting_heart_rate'
    
    id = Column(Integer, primary_key=True, index=True)
    measurement_date = Column(Date, unique=True, index=True)
    
    # Hvilepuls
    resting_heart_rate = Column(Float)  # bpm
    
    # Kontekst
    measurement_method = Column(String(50), nullable=True)  # 'automatic', 'manual'
    measurement_time = Column(DateTime, nullable=True)
    
    # Kvalitet
    measurement_quality = Column(String(20), nullable=True)  # 'excellent', 'good', 'fair', 'poor'
    confidence_level = Column(Float, nullable=True)  # 0-100
    
    # Metadata
    device_name = Column(String(100), nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class Weight(Base):
    __tablename__ = 'weight'
    
    id = Column(Integer, primary_key=True, index=True)
    measurement_date = Column(Date, index=True)
    measurement_time = Column(DateTime)
    
    # Vektmålinger
    weight = Column(Float)  # kg
    body_fat_percent = Column(Float, nullable=True)  # prosent
    muscle_mass = Column(Float, nullable=True)  # kg
    bone_mass = Column(Float, nullable=True)  # kg
    body_water_percent = Column(Float, nullable=True)  # prosent
    visceral_fat = Column(Float, nullable=True)  # rating
    
    # BMI
    bmi = Column(Float, nullable=True)
    
    # Metadata
    measurement_method = Column(String(50), nullable=True)  # 'scale', 'manual'
    device_name = Column(String(100), nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
