"""
api/websocket_manager.py
Manages connected WebSocket clients and bridges ZeroMQ events to them.
"""
from __future__ import annotations

import asyncio
import json
from typing import List

import zmq
import zmq.asyncio
from fastapi import WebSocket
from loguru import logger

from config.settings import settings


class ConnectionManager:
    def __init__(self) -> None:
        self.active: List[WebSocket] = []
        # Async ZMQ subscriber — subscribes to ALL topics
        self._ctx = zmq.asyncio.Context.instance()
        self._sub: zmq.asyncio.Socket = self._ctx.socket(zmq.SUB)
        self._sub.connect(settings.ZMQ_BROKER_BACKEND)
        self._sub.setsockopt_string(zmq.SUBSCRIBE, "")   # all topics

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        logger.info("WS client connected — total: {}", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        logger.info("WS client disconnected — total: {}", len(self.active))

    async def broadcast(self, message: str) -> None:
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def zmq_to_ws_loop(self) -> None:
        """
        Background task: receive ZMQ messages and push them to all WS clients.
        """
        logger.info("WebSocket ZMQ bridge started")
        while True:
            try:
                raw = await asyncio.wait_for(self._sub.recv_string(), timeout=1.0)
                topic, _, body = raw.partition(" ")
                payload = json.loads(body) if body else {}
                msg = json.dumps({"topic": topic, "payload": payload})
                await self.broadcast(msg)
            except asyncio.TimeoutError:
                pass
            except Exception as exc:
                logger.error("zmq_to_ws_loop error: {}", exc)


# Singleton used by api/main.py
ws_manager = ConnectionManager()
