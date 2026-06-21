"""
agents/signal_agent.py
Traffic signal controller agent.
Uses a Deterministic Adaptive algorithm (Dynamic Webster's split) based on live queue lengths.
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from loguru import logger

from agents.base_agent import BaseAgent


_PHASES: List[str] = ["NS_GREEN", "ALL_RED", "EW_GREEN", "ALL_RED_2"]


class SignalAgent(BaseAgent):
    def __init__(self, agent_id: str, intersection_id: str) -> None:
        super().__init__(agent_id, intersection_id)
        self.subscribe([
            "signals.override",
            f"congestion.{intersection_id}",
            "accidents",
        ])

        self._phase_idx:      int   = 0
        self._phase_start:    float = time.time()
        self._override_active: bool = False

        # Phase durations (seconds) — dynamically updated
        self._phase_durations: Dict[str, float] = {
            "NS_GREEN":   30.0,
            "EW_GREEN":   30.0,
            "ALL_RED":     5.0,
            "ALL_RED_2":   5.0,
        }

        # Cache current phase in shared state
        self._write_phase()

    # ── Current state helpers ─────────────────────────────────────
    @property
    def current_phase(self) -> str:
        return _PHASES[self._phase_idx]

    def phase_for_approaches(self) -> Dict[str, str]:
        """Returns per-approach signal colour."""
        if self.current_phase == "NS_GREEN":
            return {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"}
        elif self.current_phase == "EW_GREEN":
            return {"N": "RED",   "S": "RED",   "E": "GREEN", "W": "GREEN"}
        else:
            return {"N": "RED",   "S": "RED",   "E": "RED",   "W": "RED"}

    # ── Internal ─────────────────────────────────────────────────
    def _write_phase(self) -> None:
        self.set_shared_state(
            f"signal_state:{self.intersection_id}",
            {"phase": self.current_phase, "approaches": self.phase_for_approaches()},
        )
        self.publish(f"signals.{self.intersection_id}", {
            "intersection_id": self.intersection_id,
            "phase": self.current_phase,
            "approaches": self.phase_for_approaches(),
        })
        logger.info("Signal {} → {} (Duration: {:.1f}s)", self.intersection_id, self.current_phase, self._phase_durations[self.current_phase])

    def _advance_phase(self) -> None:
        self._phase_idx  = (self._phase_idx + 1) % len(_PHASES)
        self._phase_start = time.time()
        self._write_phase()

    def _force_phase(self, phase_name: str) -> None:
        if phase_name in _PHASES:
            self._phase_idx  = _PHASES.index(phase_name)
            self._phase_start = time.time()
            self._write_phase()

    # ── Loops ─────────────────────────────────────────────────────
    async def _run_loop(self) -> None:
        while self._running:
            if not self._override_active:
                elapsed  = time.time() - self._phase_start
                duration = self._phase_durations.get(self.current_phase, 30.0)
                if elapsed >= duration:
                    self._advance_phase()
            await asyncio.sleep(0.5)

    async def handle_message(self, topic: str, payload: dict) -> None:
        if topic == "signals.override":
            target = payload.get("intersection_id", "")
            if target in ("", self.intersection_id):
                self._override_active = payload.get("active", False)
                if "force_phase" in payload:
                    self._force_phase(payload["force_phase"])
                logger.warning("Override @ {} → active={}", self.intersection_id, self._override_active)

        elif topic.startswith("congestion."):
            # Deterministic Adaptive Control (Dynamic Split)
            queues = payload.get("queue_lengths", {})
            pedestrians = payload.get("pedestrians_waiting", False)
            if queues:
                # Max queue for NS approaches vs EW approaches
                ns_max = max(queues.get("N", 0), queues.get("S", 0))
                ew_max = max(queues.get("E", 0), queues.get("W", 0))
                
                total = ns_max + ew_max
                if total == 0:
                    ns_split = 0.5
                    ew_split = 0.5
                else:
                    ns_split = ns_max / total
                    ew_split = ew_max / total

                # Base cycle time = 60s
                base_cycle = 60.0
                
                # Minimum green time bounds
                min_green = 20.0 if pedestrians else 10.0
                
                # Calculate new durations, bounded between min_green and 50s
                ns_dur = max(min_green, min(50.0, base_cycle * ns_split))
                ew_dur = max(min_green, min(50.0, base_cycle * ew_split))

                self._phase_durations["NS_GREEN"] = ns_dur
                self._phase_durations["EW_GREEN"] = ew_dur
                
                if pedestrians:
                    logger.debug("Pedestrians detected at {}, enforcing {}s min green", self.intersection_id, min_green)

        elif topic == "accidents":
            # Emergency pre-emption
            if payload.get("intersection_id") == self.intersection_id:
                self._force_phase("ALL_RED")
                self._override_active = True
