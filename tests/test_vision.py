"""
tests/test_vision.py
Unit tests for the violation detector against the real implementation.
ANPR is disabled via conftest so no OCR engine loads.
"""
import numpy as np

from vision.detector import BoundingBox
from vision.violation_detector import ViolationDetector


def _box(tid: int, x1: int, y1: int, x2: int, y2: int) -> BoundingBox:
    return BoundingBox(
        det_id=0, class_name="car", confidence=0.9,
        x1=x1, y1=y1, x2=x2, y2=y2, track_id=tid,
    )


def _frame() -> np.ndarray:
    return np.zeros((720, 800, 3), dtype=np.uint8)


def test_speeding_detection():
    detector = ViolationDetector("INT_1")

    # 65 km/h in a 50 km/h zone with a 10 km/h grace margin
    detector.check_speeding(_frame(), _box(100, 0, 0, 10, 10), speed_kmh=65.0)
    assert "100_speeding" in detector.logged_violations

    # 55 km/h is within the grace margin: no violation
    detector.check_speeding(_frame(), _box(101, 0, 0, 10, 10), speed_kmh=55.0)
    assert "101_speeding" not in detector.logged_violations

    # Deduplication: the same track is only flagged once
    detector.check_speeding(_frame(), _box(100, 0, 0, 10, 10), speed_kmh=70.0)
    assert sum(1 for k in detector.logged_violations if k == "100_speeding") == 1


def test_red_light_detection():
    detector = ViolationDetector("INT_1")
    # Box center (200, 410) sits inside the N stop-line zone (100,390,300,420)
    box = _box(101, 190, 400, 210, 420)

    detector.check_red_light(_frame(), box, {"N": "RED"})
    assert "101_red_light_N" in detector.logged_violations


def test_red_light_green_signal_no_violation():
    detector = ViolationDetector("INT_1")
    box = _box(102, 190, 400, 210, 420)

    detector.check_red_light(_frame(), box, {"N": "GREEN"})
    assert "102_red_light_N" not in detector.logged_violations


def test_congestion_map_counts_vehicles_not_people():
    from vision.congestion_map import CongestionMap

    boxes = [
        BoundingBox(det_id=0, class_name="car", confidence=0.9,
                    x1=250, y1=100, x2=290, y2=140, track_id=1),
        BoundingBox(det_id=1, class_name="person", confidence=0.9,
                    x1=250, y1=150, x2=260, y2=175, track_id=2),
    ]
    state = CongestionMap("INT_1").compute(boxes, {1: 0.0, 2: 0.0})
    assert state.total_vehicles == 1
    assert state.pedestrians_waiting is True
    assert state.queue_lengths["N"] == 1     # car in the N zone, stopped
