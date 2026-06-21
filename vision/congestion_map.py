"""
vision/congestion_map.py
Computes vehicle density, queue lengths, and congestion level from tracker output.
"""
from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel

from vision.detector import BoundingBox


class CongestionState(BaseModel):
    intersection_id: str
    level: str                       # FREE | MODERATE | HEAVY | GRIDLOCK
    queue_lengths:  Dict[str, int]   # approach → count of slow vehicles
    total_vehicles: int
    pedestrians_waiting: bool
    density_grid:   List[List[int]]  # 3×3 grid vehicle counts (top-left origin)


class CongestionMap:
    """
    Divides the camera frame into a 3×3 grid and 4 approach zones.
    Approach zones are simplified rectangular slabs around the intersection.
    """

    # Approach zones: (x1,y1,x2,y2) — tune per deployment
    _ZONES: Dict[str, Dict[str, int]] = {
        "N": {"x1": 200, "y1":   0, "x2": 440, "y2": 300},
        "S": {"x1": 200, "y1": 400, "x2": 440, "y2": 720},
        "E": {"x1": 500, "y1": 200, "x2": 800, "y2": 520},
        "W": {"x1":   0, "y1": 200, "x2": 180, "y2": 520},
    }
    _SLOW_KMH = 5.0    # below this → vehicle is queued

    def __init__(self, intersection_id: str, frame_w: int = 800, frame_h: int = 600) -> None:
        self.intersection_id = intersection_id
        self._w = frame_w
        self._h = frame_h

    def compute(
        self,
        boxes:  List[BoundingBox],
        speeds: Dict[int, float],
    ) -> CongestionState:
        """
        Parameters
        ----------
        boxes  : tracked bounding boxes (must have track_id)
        speeds : track_id → km/h
        """
        queue_lengths = {d: 0 for d in "NSEW"}
        total = len([b for b in boxes if b.class_id != 0])
        pedestrian_count = 0

        # 3×3 density grid
        grid = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        col_w = self._w / 3
        row_h = self._h / 3

        for box in boxes:
            cx, cy = box.cx, box.cy
            spd = speeds.get(box.track_id, 0.0) if box.track_id else 0.0

            if box.class_id == 0:
                pedestrian_count += 1
                continue

            # Grid cell
            col = min(int(cx / col_w), 2)
            row = min(int(cy / row_h), 2)
            grid[row][col] += 1

            # Approach zone queue
            for approach, z in self._ZONES.items():
                if z["x1"] <= cx <= z["x2"] and z["y1"] <= cy <= z["y2"]:
                    if spd < self._SLOW_KMH:
                        queue_lengths[approach] += 1

        max_q = max(queue_lengths.values()) if queue_lengths else 0
        if max_q >= 15:
            level = "GRIDLOCK"
        elif max_q >= 10:
            level = "HEAVY"
        elif max_q >= 4:
            level = "MODERATE"
        else:
            level = "FREE"

        return CongestionState(
            intersection_id=self.intersection_id,
            level=level,
            queue_lengths=queue_lengths,
            total_vehicles=total,
            pedestrians_waiting=(pedestrian_count > 0),
            density_grid=grid,
        )
