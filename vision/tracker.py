"""
vision/tracker.py
ByteTrack multi-object tracker via the supervision library.
Computes per-vehicle speed (px/s → km/h) and direction vector.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple

import numpy as np
import supervision as sv
from loguru import logger

from config.settings import settings
from vision.detector import BoundingBox


class TrackedVehicle:
    """Running stats for a single tracked vehicle."""
    __slots__ = ("track_id", "history", "class_name", "first_seen", "last_seen")

    def __init__(self, track_id: int, class_name: str) -> None:
        self.track_id  = track_id
        self.class_name = class_name
        # history: deque of (cx, cy, timestamp)
        self.history: deque[Tuple[float, float, float]] = deque(maxlen=60)
        self.first_seen = time.time()
        self.last_seen  = time.time()


class Tracker:
    """
    Wraps supervision's ByteTrack, enriches detections with:
      • persistent track_id
      • speed (km/h)
      • direction unit vector [dx, dy]
      • dwell time (seconds since first seen)
    """

    # Rough calibration: 1 pixel ≈ 0.05 m  (adjust per camera/intersection)
    PX_TO_M = 0.05

    def __init__(self, fps: int = 30) -> None:
        self.fps = fps
        self.byte_tracker = sv.ByteTrack(
            track_activation_threshold=settings.CONFIDENCE_THRESHOLD,
            lost_track_buffer=settings.TRACKER_MAX_AGE,
            frame_rate=fps,
        )
        self._vehicles: Dict[int, TrackedVehicle] = {}
        logger.info("ByteTrack tracker initialised (fps={})", fps)

    # ── Main update ───────────────────────────────────────────────
    def update(self, detections: List[BoundingBox]) -> List[BoundingBox]:
        """
        Feed detections, get back the same list annotated with track_id.
        """
        if not detections:
            return []

        # Build supervision Detections object
        xyxy       = np.array([[b.x1, b.y1, b.x2, b.y2] for b in detections], dtype=np.float32)
        confidence = np.array([b.confidence for b in detections], dtype=np.float32)
        class_id   = np.zeros(len(detections), dtype=int)   # ByteTrack doesn't need class

        sv_dets = sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)
        tracked = self.byte_tracker.update_with_detections(sv_dets)

        now = time.time()
        result: List[BoundingBox] = []

        for i in range(len(tracked.xyxy)):
            x1, y1, x2, y2 = map(int, tracked.xyxy[i])
            tid = int(tracked.tracker_id[i])

            # Find best-matching original detection by centre proximity
            tx_c = (x1 + x2) / 2; ty_c = (y1 + y2) / 2
            best, best_d = None, float("inf")
            for b in detections:
                d = (b.cx - tx_c) ** 2 + (b.cy - ty_c) ** 2
                if d < best_d:
                    best_d = d; best = b

            class_name = best.class_name if best else "car"

            # Update history
            if tid not in self._vehicles:
                self._vehicles[tid] = TrackedVehicle(tid, class_name)
            veh = self._vehicles[tid]
            veh.last_seen = now
            veh.history.append((tx_c, ty_c, now))

            result.append(BoundingBox(
                class_name=class_name,
                confidence=best.confidence if best else 0.5,
                x1=x1, y1=y1, x2=x2, y2=y2,
                track_id=tid,
            ))

        # Evict stale tracks from memory (> 5 s unseen)
        stale = [tid for tid, v in self._vehicles.items()
                 if now - v.last_seen > 5.0]
        for tid in stale:
            del self._vehicles[tid]

        return result

    # ── Speed & direction ─────────────────────────────────────────
    def get_speed_kmh(self, track_id: int) -> float:
        veh = self._vehicles.get(track_id)
        if veh is None or len(veh.history) < 5:
            return 0.0

        oldest = veh.history[0]
        newest = veh.history[-1]
        dt = newest[2] - oldest[2]
        if dt <= 0:
            return 0.0

        dx = newest[0] - oldest[0]
        dy = newest[1] - oldest[1]
        dist_m = np.hypot(dx, dy) * self.PX_TO_M
        speed_mps = dist_m / dt
        return speed_mps * 3.6   # → km/h

    def get_direction(self, track_id: int) -> np.ndarray:
        """Returns a unit vector [dx, dy] or [0, 0] if unknown."""
        veh = self._vehicles.get(track_id)
        if veh is None or len(veh.history) < 5:
            return np.array([0.0, 0.0])

        oldest = veh.history[0]
        newest = veh.history[-1]
        vec = np.array([newest[0] - oldest[0], newest[1] - oldest[1]])
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else np.array([0.0, 0.0])

    def get_dwell_time(self, track_id: int) -> float:
        veh = self._vehicles.get(track_id)
        return (time.time() - veh.first_seen) if veh else 0.0
