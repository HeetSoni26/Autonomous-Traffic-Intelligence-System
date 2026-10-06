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
            logger.warning("CongestionAgent: {} at {} : broadcasting reroute", level, iid)
            # Variable message sign alert. Published on its own topic: writing
            # to signals.<id> here would corrupt the dashboard signal state.
            self.publish("alerts.vms", {
                "intersection_id": iid,
                "message": f"HEAVY TRAFFIC AT {iid} - USE ALTERNATE ROUTE",
                "level":   level,
            })
            # Nudge neighbouring intersections toward a green wave.
            parallel = self._get_parallel_corridor(iid)
            for node in parallel:
                self.publish("greenwave.request", {
                    "intersection_id": node,
                    "source": iid,
                })

    @staticmethod
    def _get_parallel_corridor(iid: str) -> list:
        """Adjacent intersections that can absorb diverted traffic."""
        mapping = {
            "INT_1": ["INT_2", "INT_4"],
            "INT_2": ["INT_1", "INT_3", "INT_5"],
            "INT_3": ["INT_2", "INT_6"],
            "INT_4": ["INT_1", "INT_5"],
            "INT_5": ["INT_2", "INT_4", "INT_6"],
            "INT_6": ["INT_3", "INT_5"],
        }
        return mapping.get(iid, [])
