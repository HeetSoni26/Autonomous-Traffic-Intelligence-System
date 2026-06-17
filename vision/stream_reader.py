"""
vision/stream_reader.py
Multi-source OpenCV video ingestion.
Sources: integer (webcam), file path, or RTSP URL.
"""
from __future__ import annotations

import cv2
import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Union

from loguru import logger


class StreamReader:
    def __init__(self, sources: List[Union[str, int]]) -> None:
        self._caps: List[cv2.VideoCapture] = []
        self._executor = ThreadPoolExecutor(
            max_workers=max(len(sources), 1),
            thread_name_prefix="stream_reader",
        )
        for src in sources:
            cap = cv2.VideoCapture(src)
            if cap.isOpened():
                logger.info("Opened video source: {}", src)
                self._caps.append(cap)
            else:
                logger.error("Failed to open video source: {}", src)

    @property
    def fps(self) -> float:
        if self._caps:
            return self._caps[0].get(cv2.CAP_PROP_FPS) or 30.0
        return 30.0

    def read_all(self) -> List[Optional[object]]:
        """Read one frame from every active source in parallel."""
        if not self._caps:
            return []
        futures = [self._executor.submit(self._read_one, cap) for cap in self._caps]
        return [f.result() for f in futures]

    @staticmethod
    def _read_one(cap: cv2.VideoCapture):
        ret, frame = cap.read()
        if not ret:
            return None
        return frame

    def release(self) -> None:
        for cap in self._caps:
            cap.release()
        self._executor.shutdown(wait=False)
        logger.info("StreamReader released all sources")


# ── CLI demo mode ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0",
                    help="Camera index, file path, or RTSP URL (comma-separated for multiple)")
    args = ap.parse_args()

    # Parse sources
    raw = [s.strip() for s in args.source.split(",")]
    sources = []
    for s in raw:
        sources.append(int(s) if s.isdigit() else s)

    reader = StreamReader(sources)

    try:
        while True:
            frames = reader.read_all()
            for i, frame in enumerate(frames):
                if frame is not None:
                    cv2.imshow(f"Stream {i}", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            time.sleep(1 / reader.fps)
    except KeyboardInterrupt:
        pass
    finally:
        reader.release()
        cv2.destroyAllWindows()
