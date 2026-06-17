"""
agents/emergency_agent.py
Emergency vehicle routing and signal preemption.
"""
from __future__ import annotations

import asyncio
from typing import List

import networkx as nx
from loguru import logger

from agents.base_agent import BaseAgent


class EmergencyAgent(BaseAgent):
    def __init__(self, agent_id: str) -> None:
        super().__init__(agent_id, "global")
        self.subscribe(["accidents", "emergency_vehicle_detected"])

        # Road network graph (loaded from shared state / SUMO net in production)
        self._graph = nx.DiGraph()
        for src, dst in [("INT_1","INT_2"),("INT_2","INT_3"),
                         ("INT_3","INT_4"),("INT_1","INT_3")]:
            self._graph.add_edge(src, dst, weight=1)

    async def _run_loop(self) -> None:
        while self._running:
            await asyncio.sleep(1)

    async def handle_message(self, topic: str, payload: dict) -> None:
        if topic == "accidents":
            await self._respond_to_accident(payload)
        elif topic == "emergency_vehicle_detected":
            await self._route_emergency(payload)

    async def _respond_to_accident(self, payload: dict) -> None:
        iid = payload.get("intersection_id", "")
        logger.warning("EmergencyAgent: accident at {} — issuing preemption", iid)
        self.publish("signals.override", {"intersection_id": iid, "active": True, "force_phase": "ALL_RED"})
        await asyncio.sleep(10)
        self.publish("signals.override", {"intersection_id": iid, "active": False})

    async def _route_emergency(self, payload: dict) -> None:
        src  = payload.get("intersection_id", "INT_1")
        dest = payload.get("destination_id",  "INT_4")
        try:
            path: List[str] = nx.shortest_path(self._graph, src, dest, weight="weight")
            logger.info("Emergency path: {}", " → ".join(path))
            for node in path:
                self.publish("signals.override", {
                    "intersection_id": node, "active": True, "force_phase": "ALL_RED"
                })
            await asyncio.sleep(15)
            for node in path:
                self.publish("signals.override", {"intersection_id": node, "active": False})
        except nx.NetworkXNoPath:
            logger.error("No path from {} to {}", src, dest)
