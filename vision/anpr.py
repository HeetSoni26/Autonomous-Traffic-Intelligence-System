"""
vision/anpr.py
Automated Number Plate Recognition using EasyOCR.
"""
from __future__ import annotations

import cv2
import numpy as np
from loguru import logger

class ANPR:
    def __init__(self) -> None:
        try:
            import easyocr
            # Force CPU for stability on varying systems, can change gpu=True if CUDA is robust
            self.reader = easyocr.Reader(['en'], gpu=False)
            self._enabled = True
            logger.info("ANPR initialized successfully.")
        except ImportError:
            self._enabled = False
            logger.warning("EasyOCR not installed. ANPR is disabled.")
        except Exception as e:
            self._enabled = False
            logger.error(f"Failed to initialize EasyOCR: {e}")

    def read_license_plate(self, frame: np.ndarray, box) -> str | None:
        """
        Crop the bounding box from the frame and attempt to read text.
        """
        if not self._enabled:
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
            results = self.reader.readtext(gray, detail=0)
            if results:
                # Often multiple texts are detected (car brand, bumper stickers).
                # Simple heuristic: license plates usually have > 5 characters.
                candidates = [text.strip().upper() for text in results if len(text.strip()) >= 4]
                if candidates:
                    return candidates[0]
        except Exception as e:
            logger.error(f"OCR error: {e}")
            
        return None
