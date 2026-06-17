"""
database/influx_logger.py
Writes time-series metrics to InfluxDB 2.x.
Gracefully no-ops when INFLUXDB_ENABLED=False (no Docker).
"""
from __future__ import annotations

import time
from typing import Dict, Any

from loguru import logger
from config.settings import settings


class InfluxLogger:
    def __init__(self) -> None:
        self._enabled = settings.INFLUXDB_ENABLED
        self._client = None
        self._write_api = None

        if self._enabled:
            try:
                from influxdb_client import InfluxDBClient
                from influxdb_client.client.write_api import SYNCHRONOUS

                self._client = InfluxDBClient(
                    url=settings.INFLUXDB_URL,
                    token=settings.INFLUXDB_TOKEN,
                    org=settings.INFLUXDB_ORG,
                )
                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
                logger.info("InfluxDB connected at {}", settings.INFLUXDB_URL)
            except Exception as exc:
                logger.warning("InfluxDB unavailable — metrics disabled: {}", exc)
                self._enabled = False
        else:
            logger.info("InfluxDB disabled (INFLUXDB_ENABLED=False) — metrics skipped")

    def _write(self, measurement: str, tags: Dict[str, str], fields: Dict[str, Any]) -> None:
        if not self._enabled or self._write_api is None:
            return
        try:
            from influxdb_client import Point
            point = Point(measurement)
            for k, v in tags.items():
                point = point.tag(k, v)
            for k, v in fields.items():
                point = point.field(k, v)
            point = point.time(time.time_ns())
            self._write_api.write(bucket=settings.INFLUXDB_BUCKET, record=point)
        except Exception as exc:
            logger.error("InfluxDB write error: {}", exc)

    def log_queue_length(self, intersection_id: str, approach: str, count: int) -> None:
        self._write("queue_length",
                    {"intersection": intersection_id, "approach": approach},
                    {"count": count})

    def log_throughput(self, intersection_id: str, direction: str, count: int) -> None:
        self._write("throughput",
                    {"intersection": intersection_id, "direction": direction},
                    {"count": count})

    def log_wait_time(self, intersection_id: str, approach: str, avg_wait_s: float) -> None:
        self._write("wait_time",
                    {"intersection": intersection_id, "approach": approach},
                    {"avg_seconds": avg_wait_s})

    def log_signal_phase(self, intersection_id: str, phase: str) -> None:
        self._write("signal_phase",
                    {"intersection": intersection_id},
                    {"phase": phase})


# Singleton
influx_logger = InfluxLogger()
