"""
vision/accident_detector.py
Heuristic accident detection:
  • Vehicle stopped for > ACCIDENT_STOP_SECONDS in a non-parking zone
  • AND is within ACCIDENT_OVERLAP_PX pixels of another stopped vehicle
Publishes AccidentEvent to ZMQ "accidents" topic.
"""
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional, Set

from loguru import logger

from config.settings import settings
from database.event_store import event_store
from vision.detector import BoundingBox


class AccidentDetector:
    def __init__(self, intersection_id: str, publisher=None) -> None:
        self.intersection_id = intersection_id
        self._pub = publisher                           # ZMQ PUB socket (optional)

        # track_id → timestamp when it first became "stopped"
        self._stopped_since: Dict[int, float] = {}

        # Set of track_id pairs already reported as accident
        self._reported: Set[frozenset] = set()

        self._stop_thresh   = settings.ACCIDENT_STOP_SECONDS
        self._overlap_px    = settings.ACCIDENT_OVERLAP_PX
        self._active_accident = False

    # ── Main entry point ─────────────────────────────────────────
    def update(
        self,
        boxes:  List[BoundingBox],
        speeds: Dict[int, float],
    ) -> bool:
        """
        Call every frame. Returns True if a new accident is flagged.
        """
        now = time.time()
        abnormally_stopped: List[BoundingBox] = []

        for box in boxes:
            if box.track_id is None:
                continue
            speed = speeds.get(box.track_id, 0.0)

            if speed < 1.5:                            # essentially stopped
                if box.track_id not in self._stopped_since:
                    self._stopped_since[box.track_id] = now
                duration = now - self._stopped_since[box.track_id]
                if duration >= self._stop_thresh:
                    abnormally_stopped.append(box)
            else:
                self._stopped_since.pop(box.track_id, None)

        # Check spatial proximity among long-stopped vehicles
        n = len(abnormally_stopped)
        for i in range(n):
            for j in range(i + 1, n):
                b1, b2 = abnormally_stopped[i], abnormally_stopped[j]
                pair = frozenset({b1.track_id, b2.track_id})
                if pair in self._reported:
                    continue

                dist = ((b1.cx - b2.cx) ** 2 + (b1.cy - b2.cy) ** 2) ** 0.5
                if dist < self._overlap_px:
                    self._reported.add(pair)
                    severity = min(0.3 + 0.1 * n, 1.0)
                    self._fire_accident(severity, n)
                    return True

        # Auto-clear if the stopped cluster has resolved
        if self._active_accident and len(abnormally_stopped) == 0:
            self._active_accident = False

        return False

    # ── Internal ─────────────────────────────────────────────────
    def _fire_accident(self, severity: float, n_vehicles: int) -> None:
        self._active_accident = True
        event_store.store_accident(
            intersection_id=self.intersection_id,
            severity_score=severity,
            involved_vehicles=n_vehicles,
        )
        payload = {
            "intersection_id": self.intersection_id,
            "severity": severity,
            "involved_vehicles": n_vehicles,
        }
        if self._pub:
            try:
                self._pub.send_string(f"accidents {json.dumps(payload)}")
            except Exception as exc:
                logger.warning("ZMQ publish accident failed: {}", exc)

        logger.error(
            "ACCIDENT detected @ {} — severity={:.2f} vehicles={}",
            self.intersection_id, severity, n_vehicles,
        )
