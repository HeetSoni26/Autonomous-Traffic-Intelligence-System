"""
vision/anpr.py
Automated Number Plate Recognition using EasyOCR.

The OCR reader is heavyweight (model download on first use), so it is
created lazily on the first plate read and can be disabled entirely with
ANPR_ENABLED=False. When easyocr is not installed the detector degrades
gracefully: violations are still logged, just without a plate number.
"""
from __future__ import annotations

from loguru import logger

import cv2
import numpy as np

from config.settings import settings


class ANPR:
    def __init__(self) -> None:
        self._reader = None          # created lazily on first use
        self._enabled = settings.ANPR_ENABLED
        self._init_attempted = False

    def _ensure_reader(self) -> None:
        """Try to build the EasyOCR reader exactly once."""
        if self._init_attempted or not self._enabled:
            return
        self._init_attempted = True
        try:
            import easyocr
            # Force CPU for stability on varying systems; switch to gpu=True
            # on machines with a working CUDA stack.
            self._reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            logger.info("ANPR initialized successfully.")
        except ImportError:
            self._enabled = False
            logger.warning("easyocr not installed. ANPR is disabled.")
        except Exception as exc:
            self._enabled = False
            logger.error("Failed to initialize EasyOCR: {}", exc)

    def read_license_plate(self, frame: np.ndarray, box) -> str | None:
        """
        Crop the bounding box from the frame and attempt to read text.
        Returns None when ANPR is disabled or nothing legible is found.
        """
        if not self._enabled:
            return None
        self._ensure_reader()
        if self._reader is None:
            return None

        # Ensure box is within frame dimensions
        h, w = frame.shape[:2]
        x1, y1 = max(0, int(box.x1)), max(0, int(box.y1))
        x2, y2 = min(w, int(box.x2)), min(h, int(box.y2))

        if x2 <= x1 or y2 <= y1:
            return None

        cropped = frame[y1:y2, x1:x2]

        # Convert to grayscale for better OCR
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)

        try:
            results = self._reader.readtext(gray, detail=0)
            if results:
                # Often multiple texts are detected (car brand, bumper
                # stickers). Simple heuristic: plates have >= 4 characters.
                candidates = [t.strip().upper() for t in results if len(t.strip()) >= 4]
                if candidates:
                    return candidates[0]
        except Exception as exc:
            logger.error("OCR error: {}", exc)

        return None
