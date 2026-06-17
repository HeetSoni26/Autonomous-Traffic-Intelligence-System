import pytest
import numpy as np
from vision.detector import BoundingBox
from vision.violation_detector import ViolationDetector

def test_speeding_detection():
    detector = ViolationDetector("INT_1")
    box = BoundingBox(id=1, class_name="car", confidence=0.9, x1=0, y1=0, x2=10, y2=10, track_id=100)
    
    # 65 km/h in a 50 km/h zone
    detector.check_speeding(box, speed_kmh=65.0, approach="N")
    
    # Violation should be logged in memory set
    assert "100_speeding" in detector.logged_violations

def test_red_light_detection():
    detector = ViolationDetector("INT_1")
    # Box center is at (200, 410) which is inside the "N" stop line polygon
    box = BoundingBox(id=1, class_name="car", confidence=0.9, x1=190, y1=400, x2=210, y2=420, track_id=101)
    
    signal_phase = {"N": "RED", "S": "GREEN"}
    
    detector.check_red_light(box, signal_phase)
    assert "101_red_light_N" in detector.logged_violations
