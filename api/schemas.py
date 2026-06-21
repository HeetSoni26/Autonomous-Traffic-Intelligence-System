"""
api/schemas.py
Pydantic v2 models for all REST and WebSocket payloads.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class IntersectionState(BaseModel):
    id:               str
    phase:            str
    approaches:       Dict[str, str]     # N/S/E/W → RED/GREEN
    congestion_level: str
    queue_lengths:    Dict[str, int]


class ViolationResponse(BaseModel):
    id:              int
    timestamp:       datetime
    intersection_id: str
    violation_type:  str
    vehicle_class:   str
    speed:           Optional[float] = None
    license_plate:   Optional[str] = None
    confidence:      float = 1.0


class AccidentResponse(BaseModel):
    id:                int
    timestamp:         datetime
    intersection_id:   str
    severity_score:    float
    involved_vehicles: int
    status:            str


class SignalOverrideRequest(BaseModel):
    active:      bool = True
    force_phase: Optional[str] = None   # e.g. "ALL_RED"


class LiveEvent(BaseModel):
    topic:   str
    payload: dict
