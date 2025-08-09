from sqlalchemy import Column, Integer, Float, Date, DateTime, String, Text
from sqlalchemy.sql import func
from .base import Base


class BodyBattery(Base):
    __tablename__ = 'body_battery'
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True, nullable=False)
    
    # Body Battery verdier
    body_battery_charged = Column(Float, nullable=True)  # Oppladet (0-100)
    body_battery_drained = Column(Float, nullable=True)  # Utladet (0-100)
    body_battery_charged_start = Column(Float, nullable=True)  # Start oppladet (0-100)
    body_battery_drained_start = Column(Float, nullable=True)  # Start utladet (0-100)
    
    # Høyeste og laveste verdier for dagen
    max_body_battery = Column(Float, nullable=True)  # Høyeste Body Battery for dagen
    min_body_battery = Column(Float, nullable=True)  # Laveste Body Battery for dagen
    
    # Netto endring
    net_charge = Column(Float, nullable=True)  # Netto opplading/utlading
    
    # Metadata
    device_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'body_battery_charged': self.body_battery_charged,
            'body_battery_drained': self.body_battery_drained,
            'body_battery_charged_start': self.body_battery_charged_start,
            'body_battery_drained_start': self.body_battery_drained_start,
            'max_body_battery': self.max_body_battery,
            'min_body_battery': self.min_body_battery,
            'net_charge': self.net_charge,
            'device_name': self.device_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        } 