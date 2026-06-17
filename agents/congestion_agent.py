"""
agents/congestion_agent.py
Monitors congestion and triggers rerouting recommendations.
"""
from __future__ import annotations

import asyncio

from loguru import logger

from agents.base_agent import BaseAgent


class CongestionAgent(BaseAgent):
    def __init__(self, agent_id: str) -> None:
        super().__init__(agent_id, "global_congestion")
        self.subscribe(["congestion"])

    async def _run_loop(self) -> None:
        while self._running:
            await asyncio.sleep(1)

    async def handle_message(self, topic: str, payload: dict) -> None:
        level = payload.get("level", "FREE")
        iid   = payload.get("intersection_id", "")

        if level in ("HEAVY", "GRIDLOCK"):
            logger.warning("CongestionAgent: {} at {} — broadcasting reroute", level, iid)
            self.publish("vms.update", {
                "intersection_id": iid,
                "message": f"HEAVY TRAFFIC ON {iid} — USE ALTERNATE ROUTE",
                "level":   level,
            })
            # Create a "green wave" on a parallel corridor
            parallel = self._get_parallel_corridor(iid)
            for node in parallel:
                self.publish(f"signals.{node}", {
                    "intersection_id": node,
                    "green_wave":      True,
                })

    @staticmethod
    def _get_parallel_corridor(iid: str) -> list:
        """Very simplified: return hardcoded alternate intersections."""
        mapping = {"INT_1": ["INT_5", "INT_6"], "INT_2": ["INT_7", "INT_8"]}
        return mapping.get(iid, [])
