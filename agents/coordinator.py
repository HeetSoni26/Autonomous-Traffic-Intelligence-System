"""
agents/coordinator.py
Entry point: starts the ZMQ broker, all agents, and global optimization.
Run with:  python -m agents.coordinator
"""
from __future__ import annotations

import asyncio
import threading

from loguru import logger

import config.logging_config  # configure loguru

from agents.message_bus import run_broker
from agents.signal_agent import SignalAgent
from agents.emergency_agent import EmergencyAgent
from agents.congestion_agent import CongestionAgent


def _start_broker_thread() -> None:
    """Run ZMQ broker in a daemon thread — it blocks indefinitely."""
    t = threading.Thread(target=run_broker, daemon=True, name="zmq_broker")
    t.start()
    logger.info("ZMQ broker thread started")


async def _global_optimization_loop() -> None:
    while True:
        logger.info("Global optimization pass …")
        await asyncio.sleep(30)


async def main() -> None:
    logger.info("═══ Autonomous Traffic Intelligence System ═══")

    # 1. Start broker in background thread
    _start_broker_thread()
    await asyncio.sleep(0.5)   # give broker time to bind

    # 2. Instantiate agents
    agents = [
        SignalAgent("sig_agent_INT_1", "INT_1"),
        SignalAgent("sig_agent_INT_2", "INT_2"),
        SignalAgent("sig_agent_INT_3", "INT_3"),
        SignalAgent("sig_agent_INT_4", "INT_4"),
        EmergencyAgent("em_agent"),
        CongestionAgent("cg_agent"),
    ]

    # 3. Start all agents concurrently
    for agent in agents:
        await agent.start()

    logger.info("{} agents started", len(agents))

    # 4. Global optimization loop runs alongside everything else
    await _global_optimization_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Coordinator shutting down")
