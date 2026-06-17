"""
agents/signal_agent.py
Traffic signal controller agent.
Uses RL policy if available, falls back to Webster's fixed-cycle formula.
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from loguru import logger

from agents.base_agent import BaseAgent


_PHASES: List[str] = ["NS_GREEN", "ALL_RED", "EW_GREEN", "ALL_RED_2"]

# Phase durations (seconds) — Webster's formula approximation for fixed-cycle
_PHASE_DURATIONS: Dict[str, float] = {
    "NS_GREEN":   30.0,
    "EW_GREEN":   30.0,
    "ALL_RED":     5.0,
    "ALL_RED_2":   5.0,
}


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
        logger.info("Signal {} → {}", self.intersection_id, self.current_phase)

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
                duration = _PHASE_DURATIONS.get(self.current_phase, 30.0)
                if elapsed >= duration:
                    self._advance_phase()
            await asyncio.sleep(1)

    async def handle_message(self, topic: str, payload: dict) -> None:
        if topic == "signals.override":
            target = payload.get("intersection_id", "")
            if target in ("", self.intersection_id):
                self._override_active = payload.get("active", False)
                if "force_phase" in payload:
                    self._force_phase(payload["force_phase"])
                logger.warning("Override @ {} → active={}", self.intersection_id, self._override_active)

        elif topic.startswith("congestion."):
            # Adaptive extension: if HEAVY, extend current green by 5 s
            if payload.get("level") in ("HEAVY", "GRIDLOCK"):
                if "GREEN" in self.current_phase:
                    self._phase_start += 5.0
                    logger.info("Extended green at {} due to {}", self.intersection_id, payload["level"])

        elif topic == "accidents":
            # Emergency pre-emption
            if payload.get("intersection_id") == self.intersection_id:
                self._force_phase("ALL_RED")
                self._override_active = True
