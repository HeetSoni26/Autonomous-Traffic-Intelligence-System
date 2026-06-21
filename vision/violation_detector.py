"""
vision/violation_detector.py
Detects: RED_LIGHT, SPEEDING, WRONG_WAY violations per intersection.
Persists to SQLite via event_store and publishes to ZeroMQ "violations" topic.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from shapely.geometry import Point, Polygon
from loguru import logger

from config.settings import settings
from database.event_store import event_store
from vision.detector import BoundingBox
from vision.anpr import ANPR


def _parse_zone(csv: str) -> Polygon:
    """Parse 'x1,y1,x2,y2' into a thin stop-line Polygon."""
    x1, y1, x2, y2 = map(int, csv.split(","))
    return Polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])


class ViolationDetector:
    """
    Per-intersection violation detector.
    Violations are deduplicated per (track_id, type) to avoid flooding the DB.
    """

    def __init__(self, intersection_id: str, publisher=None) -> None:
        self.intersection_id = intersection_id
        self._pub = publisher  # optional ZMQ publisher socket
        self.anpr = ANPR()

        # Stop-line polygons keyed by approach direction
        self._stop_lines: Dict[str, Polygon] = {
            "N": _parse_zone(settings.STOP_LINE_N),
            "S": _parse_zone(settings.STOP_LINE_S),
            "E": _parse_zone(settings.STOP_LINE_E),
            "W": _parse_zone(settings.STOP_LINE_W),
        }

        # Allowed direction unit vectors per approach (configurable)
        self._allowed_dirs: Dict[str, np.ndarray] = {
            "N": np.array([0.0, -1.0]),   # northbound: moving upward
            "S": np.array([0.0,  1.0]),   # southbound: moving downward
            "E": np.array([1.0,  0.0]),   # eastbound:  moving right
            "W": np.array([-1.0, 0.0]),   # westbound:  moving left
        }

        # Speed limits per approach (km/h)
        self._speed_limits: Dict[str, float] = {
            d: settings.SPEED_LIMIT_KMPH for d in "NSEW"
        }
        self._GRACE_KMPH = 10.0       # tolerance before flagging
        self._logged: Set[str] = set()  # (track_id, type, approach) keys to dedup

    # ── Public API ────────────────────────────────────────────────

    def check_all(
        self,
        frame:       np.ndarray,
        boxes:       List[BoundingBox],
        speeds:      Dict[int, float],       # track_id → km/h
        directions:  Dict[int, np.ndarray],  # track_id → unit vec
        signal_phase: Dict[str, str],         # approach → "RED"/"GREEN"
    ) -> None:
        for box in boxes:
            if box.track_id is None:
                continue
            tid = box.track_id
            spd = speeds.get(tid, 0.0)
            dirv = directions.get(tid, np.zeros(2))

            self.check_red_light(frame, box, signal_phase)
            self.check_speeding(frame, box, spd)
            self.check_wrong_way(frame, box, dirv)

    def check_red_light(
        self,
        frame: np.ndarray,
        box: BoundingBox,
        signal_phase: Dict[str, str],
    ) -> None:
        center = Point(box.cx, box.cy)
        for approach, poly in self._stop_lines.items():
            if signal_phase.get(approach, "GREEN") == "RED" and poly.contains(center):
                key = f"{box.track_id}_red_light_{approach}"
                if key not in self._logged:
                    self._logged.add(key)
                    self._log_violation("RED_LIGHT", frame, box, approach=approach)

    def check_speeding(self, frame: np.ndarray, box: BoundingBox, speed_kmh: float) -> None:
        limit = self._speed_limits.get("N", settings.SPEED_LIMIT_KMPH)
        if speed_kmh > limit + self._GRACE_KMPH:
            key = f"{box.track_id}_speeding"
            if key not in self._logged:
                    self._logged.add(key)
                    self._log_violation("SPEEDING", frame, box, speed=speed_kmh)

    def check_wrong_way(
        self, frame: np.ndarray, box: BoundingBox, direction: np.ndarray, approach: str = "N"
    ) -> None:
        allowed = self._allowed_dirs.get(approach, np.zeros(2))
        if np.linalg.norm(direction) > 0.3:           # moving fast enough
            cosine = np.dot(direction, allowed)
            if cosine < -0.5:                          # > 120° off
                key = f"{box.track_id}_wrong_way"
                if key not in self._logged:
                    self._logged.add(key)
                    self._log_violation("WRONG_WAY", frame, box, approach=approach)

    # ── Internal ─────────────────────────────────────────────────
    def _log_violation(
        self,
        vtype: str,
        frame: np.ndarray,
        box:   BoundingBox,
        approach: str = "",
        speed: Optional[float] = None,
    ) -> None:
        # Extract License Plate if possible
        plate = self.anpr.read_license_plate(frame, box)
        
        event_store.store_violation(
            intersection_id=self.intersection_id,
            violation_type=vtype,
            vehicle_id=str(box.track_id),
            vehicle_class=box.class_name,
            speed=speed,
            confidence=box.confidence,
            license_plate=plate,
        )
        if self._pub:
            import json
            payload = {
                "intersection_id": self.intersection_id,
                "violation_type": vtype,
                "vehicle_id": box.track_id,
                "vehicle_class": box.class_name,
                "speed": speed,
                "license_plate": plate,
            }
            try:
                self._pub.send_string(f"violations {json.dumps(payload)}")
            except Exception as exc:
                logger.warning("ZMQ publish violation failed: {}", exc)

        logger.warning("{} violation — {} {} @ {} [Plate: {}]", vtype, box.class_name,
                       box.track_id, self.intersection_id, plate or "UNKNOWN")
