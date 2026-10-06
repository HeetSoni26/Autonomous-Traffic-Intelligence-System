"""
api/websocket_manager.py
Manages connected WebSocket clients for the live dashboard feed.
ZeroMQ events are bridged by api.main's subscriber loop, which calls
broadcast(); this module stays transport-only.
"""
from __future__ import annotations

from typing import List

from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    def __init__(self) -> None:
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        logger.info("WS client connected, total: {}", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        logger.info("WS client disconnected, total: {}", len(self.active))

    async def broadcast(self, message: str) -> None:
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# Singleton used by api/main.py
ws_manager = ConnectionManager()
