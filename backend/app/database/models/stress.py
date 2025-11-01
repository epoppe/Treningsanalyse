from sqlalchemy import Column, Integer, String, Float, DateTime, Date, JSON
from .base import Base

class Stress(Base):
    __tablename__ = 'stress'
    
    id = Column(Integer, primary_key=True, index=True)
    stress_date = Column(Date, unique=True, index=True)
    
    # Stress-nivå
    stress_level = Column(Float, nullable=True)  # 0-100
    
    # Tidsbruk (i sekunder)
    total_time = Column(Float, nullable=True)  # sekunder
    stress_time = Column(Float, nullable=True)  # sekunder - total tid med stress (low+medium+high)
    rest_time = Column(Float, nullable=True)  # sekunder - hviletid
    
    # Stress-kategorier (i sekunder)
    low_stress_time = Column(Float, nullable=True)  # sekunder
    medium_stress_time = Column(Float, nullable=True)  # sekunder
    high_stress_time = Column(Float, nullable=True)  # sekunder
    
    # Aktivitets-stress (hvis tilgjengelig)
    activity_stress_duration = Column(Float, nullable=True)  # sekunder
    
    # Kvalitet
    data_quality = Column(String(20), nullable=True)  # 'excellent', 'good', 'fair', 'poor'
    
    # Metadata
    device_name = Column(String(100), nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    
    # Detaljerte data (JSON for fleksibilitet)
    detailed_stress_data = Column(JSON, nullable=True)

