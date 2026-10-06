"""
simulation/sim_node.py
Synthetic traffic data generator that plays the role of a vision node.

Publishes exactly what a real vision node publishes, over exactly the same
ZeroMQ topics:

    congestion.<intersection_id>   queue lengths + congestion level + stats
    violations                     occasional red-light / speeding events
    accidents                      occasional collisions (auto-cleared later)
    accident_cleared               scene resolved
    emergency_vehicle_detected     triggers the emergency green-wave routing

Queue dynamics are honest: vehicles arrive per approach at a demand rate
that follows daily rush curves, queues build while the approach signal is
RED and drain while it is GREEN. The SignalAgents see these queues and
adapt their green splits, which in turn changes how the queues drain.
That feedback loop is the real system, just with synthetic arrivals.

Run standalone:
    PYTHONPATH=. python -m simulation.sim_node
Or let DEMO_MODE=1 start it inside the API process.
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import zmq
import zmq.asyncio
from loguru import logger

import config.logging_config  # configure loguru
from config.settings import settings

INTERSECTIONS = ["INT_1", "INT_2", "INT_3", "INT_4", "INT_5", "INT_6"]
APPROACHES = ["N", "S", "E", "W"]

MAX_QUEUE = 35
DEPARTURE_PER_GREEN_TICK = 2.6   # vehicles an approach clears per second of green


class IntersectionSim:
    """One simulated intersection: arrivals, queues, and signal coupling."""

    def __init__(self, iid: str, seed: int) -> None:
        self.iid = iid
        self.rng = random.Random(seed)
        # Demand profile per approach: base rate + individual phase offset.
        # Calibrated so the peak arrival rate stays close to a lane's green
        # discharge rate (DEPARTURE_PER_GREEN_TICK): rush hours saturate the
        # dominant axis but the adaptive split can still recover it.
        self.base_rate = {a: self.rng.uniform(0.2, 0.5) for a in APPROACHES}
        self.phase = {a: self.rng.uniform(0, 6.28) for a in APPROACHES}
        # Each intersection leans toward one axis at first; the lean drifts.
        self.axis_bias = self.rng.choice([("NS", "EW"), ("EW", "NS")])
        self.bias_strength = self.rng.uniform(0.55, 0.9)
        self.queues = {a: 0 for a in APPROACHES}
        self.signal = {a: "GREEN" if a in ("N", "S") else "RED" for a in APPROACHES}
        self.cleared_total = 0
        self.throughput_ema = 0.0

    @staticmethod
    def rush_hour(t: float) -> float:
        """Two rush peaks (morning, evening) on a ~10 minute demo day cycle."""
        day_t = (t % 600) / 600.0                      # one "day" every 10 min
        morning = 0.9 * pow(max(0.0, 1 - abs(day_t - 0.22) * 7), 2)
        evening = 1.05 * pow(max(0.0, 1 - abs(day_t - 0.62) * 7), 2)
        return 0.55 + morning + evening

    def approach_rate(self, approach: str, t: float) -> float:
        rate = self.base_rate[approach]
        rate *= 1.0 + 0.5 * (1 + math.sin(t / 47 + self.phase[approach]))
        # Axis bias: the dominant axis carries more demand and slowly rotates,
        # so the adaptive controller has to keep re-balancing.
        dominant = 0.5 + 0.5 * (1 + math.sin(t / 90))
        on_axis = approach in ("N", "S") if self.axis_bias[0] == "NS" else approach in ("E", "W")
        factor = 1 + self.bias_strength * (dominant if on_axis else -dominant * 0.55)
        return max(0.05, rate * factor * self.rush_hour(t))

    def set_signal(self, approaches: dict) -> None:
        if approaches:
            self.signal = {a: approaches.get(a, "RED").upper() for a in APPROACHES}

    def tick(self, t: float, incident: bool) -> dict:
        for a in APPROACHES:
            arrivals = self.rng.expovariate(1 / max(0.05, self.approach_rate(a, t)))
            if incident:
                arrivals += self.rng.uniform(2.5, 4.5)   # rubbernecking backup
            queue = self.queues[a] + arrivals
            if self.signal.get(a) == "GREEN":
                queue -= DEPARTURE_PER_GREEN_TICK * self.rng.uniform(0.75, 1.15)
            self.queues[a] = int(max(0, min(MAX_QUEUE, queue)))
        return self.queues

    def classify(self) -> str:
        max_q = max(self.queues.values())
        if max_q >= 15:
            return "GRIDLOCK"
        if max_q >= 10:
            return "HEAVY"
        if max_q >= 4:
            return "MODERATE"
        return "FREE"

    def register_departures(self, prev: dict) -> None:
        cleared = sum(max(0, prev[a] - self.queues[a]) for a in APPROACHES)
        self.cleared_total += cleared
        # EMA of hourly throughput derived from last tick's departures
        self.throughput_ema = 0.9 * self.throughput_ema + 0.1 * (cleared * 3600)

    def state_payload(self) -> dict:
        return {
            "intersection_id": self.iid,
            "level": self.classify(),
            "queue_lengths": dict(self.queues),
            "total_vehicles": sum(self.queues.values()) + self.rng.randint(6, 14),
            "throughput_per_hour": round(self.throughput_ema),
            "pedestrians_waiting": self.rng.random() < 0.12,
        }


class SimTrafficNode:
    """Publishes synthetic but self-consistent traffic data on the real bus."""

    VIOLATION_TYPES = ("RED_LIGHT", "SPEEDING")

    def __init__(self, intersections: list[str] | None = None) -> None:
        self._iids = list(intersections or INTERSECTIONS)
        self._sims = {
            iid: IntersectionSim(iid, seed=100 + i * 37)
            for i, iid in enumerate(self._iids)
        }
        self._running = False
        self._pub: zmq.asyncio.Socket | None = None
        self._sub: zmq.asyncio.Socket | None = None
        self._rng = random.Random(42)
        self._incident: dict | None = None          # active incident state
        self._next_accident_in = self._rng.uniform(35, 70)
        self._next_emergency_in = self._rng.uniform(100, 180)

    # ── Sockets ──────────────────────────────────────────────────────
    def _connect(self) -> None:
        ctx = zmq.asyncio.Context.instance()
        self._pub = ctx.socket(zmq.PUB)
        self._pub.connect(settings.ZMQ_BROKER_FRONTEND)
        self._sub = ctx.socket(zmq.SUB)
        self._sub.connect(settings.ZMQ_BROKER_BACKEND)
        self._sub.setsockopt_string(zmq.SUBSCRIBE, "signals.")

    async def _publish(self, topic: str, payload: dict) -> None:
        await self._pub.send_string(f"{topic} {json.dumps(payload)}")

    async def _fire_now(self, topic: str, payload: dict) -> None:
        """Publish an event that must not wait for the next tick."""
        if self._pub is not None:
            await self._pub.send_string(f"{topic} {json.dumps(payload)}")

    # ── Main loop ────────────────────────────────────────────────────
    async def run(self) -> None:
        self._running = True
        self._connect()
        logger.info("Sim node publishing on {} for {}",
                    settings.ZMQ_BROKER_FRONTEND, ", ".join(self._iids))

        listener = asyncio.create_task(self._signal_listener(),
                                       name="sim_signal_listener")
        await asyncio.sleep(1.0)   # let PUB/SUB connections settle (slow joiner)

        t = 0.0
        try:
            while self._running:
                t += 1.0

                incident = self._incident is not None
                for iid, sim in self._sims.items():
                    prev = dict(sim.queues)
                    sim.tick(t, incident and self._incident["iid"] == iid)
                    sim.register_departures(prev)
                    await self._publish(f"congestion.{iid}", sim.state_payload())

                await self._maybe_accident(t)
                await self._maybe_violation()
                await self._maybe_emergency()
                await self._maybe_clear_accident(t)

                await asyncio.sleep(max(0.05, 1.0 / settings.SIM_SPEED))
        except asyncio.CancelledError:
            pass
        finally:
            listener.cancel()
            self.stop()

    async def _signal_listener(self) -> None:
        """Keep every intersection's signal state current from the bus."""
        while True:
            raw = await self._sub.recv_string()
            topic, _, body = raw.partition(" ")
            if not body or not topic.startswith("signals."):
                continue
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                continue
            sim = self._sims.get(payload.get("intersection_id"))
            if sim:
                sim.set_signal(payload.get("approaches", {}))

    # ── Events ───────────────────────────────────────────────────────
    async def _maybe_accident(self, t: float) -> None:
        self._next_accident_in -= 1.0
        if self._incident is not None or self._next_accident_in > 0:
            return
        iid = self._rng.choice(self._iids)
        self._incident = {
            "iid": iid,
            "started": t,
            "duration": self._rng.uniform(18, 32),
            "vehicles": self._rng.randint(2, 3),
            "severity": round(self._rng.uniform(0.45, 0.85), 2),
        }
        self._next_accident_in = self._rng.uniform(70, 140)
        logger.warning("Sim accident @ {} for {:.0f}s", iid, self._incident["duration"])
        await self._fire_now("accidents", {
            "intersection_id": iid,
            "severity": self._incident["severity"],
            "involved_vehicles": self._incident["vehicles"],
        })

    async def _maybe_clear_accident(self, t: float) -> None:
        if self._incident and (t - self._incident["started"]) >= self._incident["duration"]:
            iid = self._incident["iid"]
            logger.info("Sim accident cleared @ {}", iid)
            self._incident = None
            await self._fire_now("accident_cleared", {"intersection_id": iid})

    async def _maybe_violation(self) -> None:
        if self._rng.random() >= 0.10:
            return
        vtype = self._rng.choice(self.VIOLATION_TYPES)
        payload = {
            "intersection_id": self._rng.choice(self._iids),
            "violation_type": vtype,
            "vehicle_id": self._rng.randint(100, 999),
            "vehicle_class": self._rng.choice(["car", "car", "motorcycle", "truck"]),
            "speed": round(self._rng.uniform(62, 95), 1) if vtype == "SPEEDING"
                     else round(self._rng.uniform(10, 40), 1),
            "license_plate": None,
        }
        await self._fire_now("violations", payload)

    async def _maybe_emergency(self) -> None:
        self._next_emergency_in -= 1.0
        if self._next_emergency_in > 0:
            return
        self._next_emergency_in = self._rng.uniform(120, 220)
        src, dest = self._rng.sample(INTERSECTIONS, 2)
        logger.warning("Sim emergency vehicle {} -> {}", src, dest)
        await self._fire_now("emergency_vehicle_detected", {
            "intersection_id": src,
            "destination_id": dest,
            "vehicle_type": "ambulance",
        })

    # ── Lifecycle ────────────────────────────────────────────────────
    def stop(self) -> None:
        self._running = False
        if self._pub is not None:
            self._pub.close(linger=0)
            self._pub = None
        if self._sub is not None:
            self._sub.close(linger=0)
            self._sub = None
        logger.info("Sim node stopped")


async def main() -> None:
    node = SimTrafficNode()
    await node.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Sim node interrupted")
