"""
vision/detector.py
YOLOv8 vehicle and pedestrian detector.
Weights are auto-downloaded on first run and cached locally.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import numpy as np
from pydantic import BaseModel
from loguru import logger

from config.settings import settings

# COCO class IDs we care about
_TARGET_CLASSES = [0, 1, 2, 3, 5, 7]  # person, bicycle, car, motorcycle, bus, truck
_CLASS_NAMES    = {0: "person", 1: "bicycle", 2: "car",
                   3: "motorcycle", 5: "bus", 7: "truck"}


class BoundingBox(BaseModel):
    """Detected object with optional tracker ID attached."""
    det_id:     int = -1
    class_name: str
    confidence: float
    x1: int; y1: int; x2: int; y2: int
    track_id: Optional[int] = None

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def area(self) -> int:
        return (self.x2 - self.x1) * (self.y2 - self.y1)


class Detector:
    """
    Wraps ultralytics YOLOv8. On first run the model file is downloaded and
    cached to the current directory; subsequent runs use the local file.
    """

    def __init__(self) -> None:
        from ultralytics import YOLO
        model_path = settings.YOLO_MODEL_PATH
        logger.info("Loading YOLO model: {}", model_path)
        self.model = YOLO(model_path)
        self._executor = ThreadPoolExecutor(max_workers=4,
                                            thread_name_prefix="yolo_worker")
        logger.info("Detector ready — target classes: {}", list(_CLASS_NAMES.values()))

    # ── Single-frame inference ─────────────────────────────────────
    def detect(self, frame: np.ndarray) -> List[BoundingBox]:
        if frame is None or frame.size == 0:
            return []
        return self._parse_results(
            self.model.predict(
                frame,
                conf=settings.CONFIDENCE_THRESHOLD,
                classes=_TARGET_CLASSES,
                verbose=False,
            )
        )

    # ── Batch inference (parallel) ─────────────────────────────────
    def detect_batch(self, frames: List[Optional[np.ndarray]]) -> List[List[BoundingBox]]:
        valid = [(i, f) for i, f in enumerate(frames) if f is not None and f.size > 0]
        output: List[List[BoundingBox]] = [[] for _ in frames]

        if not valid:
            return output

        futures = {
            self._executor.submit(self.detect, f): i
            for i, f in valid
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                output[idx] = fut.result()
            except Exception as exc:
                logger.error("Batch detect error at frame {}: {}", idx, exc)

        return output

    # ── Internal parsing ───────────────────────────────────────────
    @staticmethod
    def _parse_results(results) -> List[BoundingBox]:
        boxes: List[BoundingBox] = []
        for result in results:
            for i, box in enumerate(result.boxes):
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_id = int(box.cls[0])
                boxes.append(BoundingBox(
                    det_id=i,
                    class_name=_CLASS_NAMES.get(cls_id, "unknown"),
                    confidence=float(box.conf[0]),
                    x1=x1, y1=y1, x2=x2, y2=y2,
                ))
        return boxes
