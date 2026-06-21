"""
database/event_store.py
Thin repository layer over SQLite for violation and accident events.
Thread-safe: uses scoped_session.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from loguru import logger

from config.settings import settings
from database.models import Base, ViolationEvent, AccidentEvent


class EventStore:
    def __init__(self) -> None:
        self.engine = create_engine(
            settings.DATABASE_URL,
            connect_args={"check_same_thread": False},  # SQLite + threads
            echo=False,
        )
        Base.metadata.create_all(bind=self.engine)
        factory = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.Session = scoped_session(factory)
        logger.info("SQLite EventStore ready — {}", settings.DATABASE_URL)

    # ── Violations ────────────────────────────────────────────────
    def store_violation(
        self,
        intersection_id: str,
        violation_type: str,
        vehicle_id: str,
        vehicle_class: str,
        speed: Optional[float] = None,
        confidence: float = 1.0,
        license_plate: Optional[str] = None,
        image_path: Optional[str] = None,
    ) -> None:
        session = self.Session()
        try:
            event = ViolationEvent(
                intersection_id=intersection_id,
                violation_type=violation_type,
                vehicle_id=vehicle_id,
                vehicle_class=vehicle_class,
                speed=speed,
                confidence=confidence,
                license_plate=license_plate,
                image_path=image_path,
            )
            session.add(event)
            session.commit()
            logger.info("Violation stored: {} by {} at {}", violation_type, vehicle_class, intersection_id)
        except Exception as exc:
            session.rollback()
            logger.error("store_violation failed: {}", exc)
        finally:
            self.Session.remove()

    def get_recent_violations(self, limit: int = 50) -> List[ViolationEvent]:
        session = self.Session()
        try:
            return (
                session.query(ViolationEvent)
                .order_by(ViolationEvent.timestamp.desc())
                .limit(limit)
                .all()
            )
        finally:
            self.Session.remove()

    # ── Accidents ─────────────────────────────────────────────────
    def store_accident(
        self,
        intersection_id: str,
        severity_score: float,
        involved_vehicles: int,
        image_path: Optional[str] = None,
    ) -> None:
        session = self.Session()
        try:
            event = AccidentEvent(
                intersection_id=intersection_id,
                severity_score=severity_score,
                involved_vehicles=involved_vehicles,
                image_path=image_path,
            )
            session.add(event)
            session.commit()
            logger.warning(
                "Accident stored: severity={} vehicles={} at {}",
                severity_score, involved_vehicles, intersection_id,
            )
        except Exception as exc:
            session.rollback()
            logger.error("store_accident failed: {}", exc)
        finally:
            self.Session.remove()

    def get_active_accidents(self) -> List[AccidentEvent]:
        session = self.Session()
        try:
            return (
                session.query(AccidentEvent)
                .filter(AccidentEvent.status == "ACTIVE")
                .order_by(AccidentEvent.timestamp.desc())
                .all()
            )
        finally:
            self.Session.remove()

    def clear_accident(self, accident_id: int) -> None:
        session = self.Session()
        try:
            event = session.query(AccidentEvent).get(accident_id)
            if event:
                event.status = "CLEARED"
                session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("clear_accident failed: {}", exc)
        finally:
            self.Session.remove()


# Module-level singleton — imported everywhere
event_store = EventStore()
