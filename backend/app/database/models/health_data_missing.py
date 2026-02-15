"""
Lagrer datoer vi har prøvd å hente helsedata for uten å finne noe.
Brukes for å unngå unødvendige Garmin API-kall ved senere synkroniseringer.
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from .base import Base


class HealthDataMissing(Base):
    __tablename__ = "health_data_missing"
    __table_args__ = (UniqueConstraint("data_type", "missing_date", name="uq_health_data_missing_type_date"),)

    id = Column(Integer, primary_key=True, index=True)
    data_type = Column(String(50), nullable=False, index=True)  # 'stress' | 'hrv' | 'sleep'
    missing_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
