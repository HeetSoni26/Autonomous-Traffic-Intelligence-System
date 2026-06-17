"""
database/models.py
SQLAlchemy ORM models for persisting violation and accident events.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ViolationEvent(Base):
    __tablename__ = "violations"

    id            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp     = Column(DateTime, default=datetime.utcnow, index=True)
    intersection_id = Column(String(64), index=True)
    violation_type  = Column(String(32), index=True)   # RED_LIGHT | SPEEDING | WRONG_WAY
    vehicle_id      = Column(String(32))
    vehicle_class   = Column(String(32))
    speed           = Column(Float, nullable=True)
    confidence      = Column(Float, default=1.0)
    image_path      = Column(Text, nullable=True)      # optional saved frame path

    def __repr__(self) -> str:
        return f"<Violation {self.violation_type} @ {self.intersection_id} t={self.timestamp}>"


class AccidentEvent(Base):
    __tablename__ = "accidents"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp       = Column(DateTime, default=datetime.utcnow, index=True)
    intersection_id = Column(String(64), index=True)
    severity_score  = Column(Float, default=0.5)       # 0..1
    involved_vehicles = Column(Integer, default=2)
    status          = Column(String(16), default="ACTIVE")  # ACTIVE | CLEARED
    image_path      = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Accident severity={self.severity_score} @ {self.intersection_id} status={self.status}>"
