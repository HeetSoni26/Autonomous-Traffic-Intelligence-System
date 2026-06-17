"""
agents/message_bus.py
ZeroMQ XPUB/XSUB broker + Redis shared-state helper.
Redis is optional — gracefully no-ops when REDIS_ENABLED=False.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import zmq
from loguru import logger

from config.settings import settings


# ── Redis helper ──────────────────────────────────────────────────────────────

class RedisState:
    """Thin wrapper around redis.Redis with graceful no-op fallback."""

    def __init__(self) -> None:
        self._r = None
        if settings.REDIS_ENABLED:
            try:
                import redis
                self._r = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
                self._r.ping()
                logger.info("Redis connected at {}:{}", settings.REDIS_HOST, settings.REDIS_PORT)
            except Exception as exc:
                logger.warning("Redis unavailable — shared state disabled: {}", exc)
                self._r = None
        else:
            logger.info("Redis disabled (REDIS_ENABLED=False) — using in-process dict")
        # In-process fallback store
        self._local: dict = {}

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value)
        if self._r:
            try:
                self._r.set(key, payload)
                return
            except Exception as exc:
                logger.warning("Redis set failed for '{}': {}", key, exc)
        self._local[key] = payload

    def get(self, key: str) -> Optional[Any]:
        if self._r:
            try:
                raw = self._r.get(key)
                return json.loads(raw) if raw else None
            except Exception as exc:
                logger.warning("Redis get failed for '{}': {}", key, exc)
        raw = self._local.get(key)
        return json.loads(raw) if raw else None


# ── ZeroMQ broker ─────────────────────────────────────────────────────────────

def run_broker() -> None:
    """
    XSUB/XPUB proxy — run in a daemon thread so publishers and subscribers
    can connect through a single rendezvous point.
    """
    ctx = zmq.Context.instance()
    frontend = ctx.socket(zmq.XSUB)   # publishers connect here
    backend  = ctx.socket(zmq.XPUB)   # subscribers connect here

    frontend.bind(settings.ZMQ_BROKER_FRONTEND)
    backend.bind(settings.ZMQ_BROKER_BACKEND)
    logger.info("ZMQ broker started — FE={} BE={}",
                settings.ZMQ_BROKER_FRONTEND, settings.ZMQ_BROKER_BACKEND)
    try:
        zmq.proxy(frontend, backend)   # blocks forever
    except zmq.ZMQError as exc:
        if "Context was terminated" not in str(exc):
            logger.error("ZMQ broker error: {}", exc)
    finally:
        frontend.close()
        backend.close()


# ── MessageBus helper for agents ─────────────────────────────────────────────

class MessageBus:
    """
    Convenience factory: creates PUB/SUB sockets connecting to the broker.
    Also wraps RedisState for shared key/value.
    """

    def __init__(self) -> None:
        self._ctx   = zmq.Context.instance()
        self.state  = RedisState()

    def make_publisher(self) -> zmq.Socket:
        sock = self._ctx.socket(zmq.PUB)
        sock.connect(settings.ZMQ_BROKER_FRONTEND)
        return sock

    def make_subscriber(self, topics: list[str]) -> zmq.Socket:
        sock = self._ctx.socket(zmq.SUB)
        sock.connect(settings.ZMQ_BROKER_BACKEND)
        for t in topics:
            sock.setsockopt_string(zmq.SUBSCRIBE, t)
        return sock


if __name__ == "__main__":
    run_broker()
