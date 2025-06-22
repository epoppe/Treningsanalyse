from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class Activity(Base):
    __tablename__ = 'activities'

    id = Column(String(255), primary_key=True, index=True)
    name = Column(String)
    type = Column(String)
    start_time = Column(DateTime)
    distance = Column(Float)
    duration = Column(Float)
    calories = Column(Float)
    vo2_max = Column(Float)
    average_hr = Column(Float)
    average_speed = Column(Float)
    average_pace = Column(Float)
    
    activity_type_id = Column(Integer, ForeignKey('activity_types.id'))
    activity_type = relationship("ActivityType")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ActivityType(Base):
    __tablename__ = 'activity_types'

    id = Column(Integer, primary_key=True, index=True)
    type_key = Column(String, unique=True, index=True)
    parent_type_key = Column(String)
