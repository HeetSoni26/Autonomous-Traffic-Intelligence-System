"""
agents/base_agent.py
Abstract base for all traffic agents.
Each agent runs as an asyncio coroutine and communicates via ZeroMQ + Redis.
"""
from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, List

import zmq
import zmq.asyncio
from loguru import logger

from agents.message_bus import MessageBus
from config.settings import settings


class BaseAgent(ABC):
    def __init__(self, agent_id: str, intersection_id: str) -> None:
        self.agent_id       = agent_id
        self.intersection_id = intersection_id
        self._running       = False

        # Use asyncio-compatible ZMQ context
        self._ctx  = zmq.asyncio.Context.instance()
        self._bus  = MessageBus()

        # PUB socket — agents publish events
        self._pub: zmq.asyncio.Socket = self._ctx.socket(zmq.PUB)
        self._pub.connect(settings.ZMQ_BROKER_FRONTEND)

        # SUB socket — set up in subscribe()
        self._sub: zmq.asyncio.Socket | None = None

    # ── Pub/Sub helpers ───────────────────────────────────────────
    def subscribe(self, topics: List[str]) -> None:
        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.connect(settings.ZMQ_BROKER_BACKEND)
        for t in topics:
            self._sub.setsockopt_string(zmq.SUBSCRIBE, t)

    def publish(self, topic: str, payload: dict) -> None:
        try:
            msg = f"{topic} {json.dumps(payload)}"
            self._pub.send_string(msg, flags=zmq.NOBLOCK)
        except zmq.ZMQError as exc:
            logger.warning("Publish failed on '{}': {}", topic, exc)

    # ── Shared state ─────────────────────────────────────────────
    def set_shared_state(self, key: str, value: Any) -> None:
        self._bus.state.set(key, value)

    def get_shared_state(self, key: str) -> Any:
        return self._bus.state.get(key)

    # ── Lifecycle ─────────────────────────────────────────────────
    async def start(self) -> None:
        self._running = True
        logger.info("Agent '{}' starting at intersection '{}'", self.agent_id, self.intersection_id)
        asyncio.create_task(self._heartbeat_loop(), name=f"heartbeat_{self.agent_id}")
        asyncio.create_task(self._listen_loop(),    name=f"listen_{self.agent_id}")
        asyncio.create_task(self._run_loop(),       name=f"run_{self.agent_id}")

    def stop(self) -> None:
        self._running = False
        if self._sub:
            self._sub.close()
        self._pub.close()
        logger.info("Agent '{}' stopped", self.agent_id)

    # ── Internal coroutines ───────────────────────────────────────
    async def _heartbeat_loop(self) -> None:
        while self._running:
            self.publish("agent.health", {
                "agent_id":       self.agent_id,
                "intersection_id": self.intersection_id,
                "status":         "ALIVE",
            })
            await asyncio.sleep(5)

    async def _listen_loop(self) -> None:
        """Read from SUB socket and dispatch to handle_message."""
        if self._sub is None:
            return
        while self._running:
            try:
                raw = await asyncio.wait_for(self._sub.recv_string(), timeout=0.5)
                topic, _, body = raw.partition(" ")
                payload = json.loads(body) if body else {}
                await self.handle_message(topic, payload)
            except asyncio.TimeoutError:
                pass
            except Exception as exc:
                logger.error("Agent '{}' _listen_loop error: {}", self.agent_id, exc)

    @abstractmethod
    async def _run_loop(self) -> None:
        """Main decision/control loop — implemented by subclasses."""
        ...

    @abstractmethod
    async def handle_message(self, topic: str, payload: dict) -> None:
        """Called when a subscribed message arrives."""
        ...
