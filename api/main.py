"""
api/main.py :: FastAPI REST + WebSocket + Static Dashboard

Listens to real ZeroMQ events from the Vision Node and Signal Agents to
drive the dashboard.

With DEMO_MODE=1 the API process also boots the ZeroMQ broker, every agent,
and a synthetic traffic simulator (simulation/sim_node.py). The demo then
runs the genuine pipeline end to end: simulator -> broker -> agents ->
broker -> API -> dashboard. No camera required, no faked dashboard state.

Run:
    python run.py               # API only; connect real agents/cameras yourself
    DEMO_MODE=1 python run.py   # self-contained demo
"""
from __future__ import annotations

import asyncio
import sys

# Windows: the default Proactor loop cannot read from pyzmq async sockets.
# run.py sets the selector policy before creating the loop; this module-level
# patch covers direct `uvicorn api.main:app` launches where possible.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List

import zmq
import zmq.asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

import config.logging_config  # noqa: configure loguru

from api.schemas import SignalOverrideRequest
from api.websocket_manager import ws_manager
from agents.message_bus import run_broker
from config.settings import settings
from database.event_store import event_store

# ── Intersection registry ────────────────────────────────────────────────────
_INTERSECTIONS = {
    "INT_1": {"lat": 19.0760, "lon": 72.8777, "name": "MG Road & FC Road"},
    "INT_2": {"lat": 19.0800, "lon": 72.8810, "name": "Andheri East Junction"},
    "INT_3": {"lat": 19.0820, "lon": 72.8850, "name": "Bandra Kurla Complex"},
    "INT_4": {"lat": 19.0740, "lon": 72.8850, "name": "Worli Sea Link Entry"},
    "INT_5": {"lat": 19.0780, "lon": 72.8820, "name": "Dadar Central"},
    "INT_6": {"lat": 19.0760, "lon": 72.8840, "name": "Parel Junction"},
}

# ── Live State (fed exclusively by bus events) ───────────────────────────────
_live_signals: dict = {
    iid: {"phase": "NS_GREEN",
          "approaches": {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"}}
    for iid in _INTERSECTIONS
}
_live_queues: dict = {iid: {"N": 0, "S": 0, "E": 0, "W": 0} for iid in _INTERSECTIONS}
_live_levels: dict = {iid: "FREE" for iid in _INTERSECTIONS}
_live_totals: dict = {iid: 0 for iid in _INTERSECTIONS}
_live_throughput: dict = {iid: 0 for iid in _INTERSECTIONS}
_violations: List[dict] = []
_accidents: List[dict] = []
_alerts: List[dict] = []
_event_seq = 0


def _next_event_id() -> int:
    global _event_seq
    _event_seq += 1
    return _event_seq


def _get_intersection_state(iid: str) -> dict:
    meta = _INTERSECTIONS[iid]
    sig = _live_signals.get(iid, {})
    queue = _live_queues.get(iid, {"N": 0, "S": 0, "E": 0, "W": 0})

    return {
        "id":               iid,
        "name":             meta["name"],
        "lat":              meta["lat"],
        "lon":              meta["lon"],
        "phase":            sig.get("phase", "NS_GREEN"),
        "approaches":       sig.get("approaches",
                                    {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"}),
        "congestion_level": _live_levels.get(iid, "FREE"),
        "queue_lengths":    queue,
        "total_queue":      sum(queue.values()),
    }


# ── ZMQ subscriber: bus events -> live state ─────────────────────────────────
async def _zmq_subscriber_loop() -> None:
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.connect(settings.ZMQ_BROKER_BACKEND)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")   # subscribe to all topics

    logger.info("API ZMQ Subscriber connected to {}", settings.ZMQ_BROKER_BACKEND)
    try:
        while True:
            msg = await sub.recv_string()
            parts = msg.split(" ", 1)
            if len(parts) != 2:
                continue
            topic, payload_str = parts
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            _handle_event(topic, payload)
    except asyncio.CancelledError:
        pass
    finally:
        sub.close()


def _handle_event(topic: str, payload: dict) -> None:
    iid = payload.get("intersection_id")
    now_str = datetime.now(timezone.utc).isoformat()

    if topic.startswith("signals.") and iid:
        if iid in _INTERSECTIONS:
            _live_signals[iid] = {
                "phase": payload.get("phase", "NS_GREEN"),
                "approaches": payload.get("approaches", {}),
            }

    elif topic.startswith("congestion.") and iid:
        if iid in _INTERSECTIONS:
            _live_queues[iid] = payload.get("queue_lengths", _live_queues.get(iid))
            _live_levels[iid] = payload.get("level", _live_levels.get(iid))
            _live_totals[iid] = payload.get("total_vehicles", _live_totals.get(iid))
            _live_throughput[iid] = payload.get("throughput_per_hour",
                                                _live_throughput.get(iid))

    elif topic == "violations":
        ev = payload.copy()
        ev["timestamp"] = now_str
        ev["id"] = _next_event_id()
        _violations.insert(0, ev)
        if len(_violations) > 100:
            _violations.pop()
        # Persist for the REST history endpoint
        event_store.store_violation(
            intersection_id=iid or "UNKNOWN",
            violation_type=ev.get("violation_type", "UNKNOWN"),
            vehicle_id=str(ev.get("vehicle_id", "")),
            vehicle_class=ev.get("vehicle_class", "vehicle"),
            speed=ev.get("speed"),
            license_plate=ev.get("license_plate"),
        )

    elif topic == "accidents":
        ev = payload.copy()
        ev["timestamp"] = now_str
        ev["id"] = _next_event_id()
        ev["status"] = "ACTIVE"
        _accidents.insert(0, ev)
        logger.warning("Accident reported @ {}", iid)

    elif topic == "accident_cleared":
        for acc in _accidents:
            if acc.get("intersection_id") == iid and acc.get("status") == "ACTIVE":
                acc["status"] = "CLEARED"
        logger.info("Accident cleared @ {}", iid)

    elif topic == "alerts.vms":
        ev = payload.copy()
        ev["timestamp"] = now_str
        ev["id"] = _next_event_id()
        _alerts.insert(0, ev)
        if len(_alerts) > 50:
            _alerts.pop()

    elif topic == "emergency_vehicle_detected":
        logger.warning("Emergency vehicle: {} -> {}",
                       iid, payload.get("destination_id", "?"))


def _ws_tick_payload() -> dict:
    return {
        "intersections": [_get_intersection_state(i) for i in _INTERSECTIONS],
        "violations":    _violations[:10],
        "accidents":     [a for a in _accidents[:5] if a["status"] == "ACTIVE"],
        "alerts":        _alerts[:5],
    }


async def _ws_broadcast_loop() -> None:
    while True:
        await ws_manager.broadcast(json.dumps({"topic": "tick",
                                               "payload": _ws_tick_payload()}))
        await asyncio.sleep(1)


# ── Demo wiring: broker + agents + simulator in-process ─────────────────────
class DemoStack:
    """Runs the full agent society inside the API process for DEMO_MODE."""

    def __init__(self) -> None:
        self._broker_thread = None
        self._agents = []
        self._sim_task = None
        self._agent_tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        import threading

        self._broker_thread = threading.Thread(
            target=run_broker, daemon=True, name="zmq_broker")
        self._broker_thread.start()
        logger.info("DEMO: ZMQ broker thread started")
        await asyncio.sleep(0.75)   # give the broker time to bind

        from agents.signal_agent import SignalAgent
        from agents.emergency_agent import EmergencyAgent
        from agents.congestion_agent import CongestionAgent
        from simulation.sim_node import SimTrafficNode

        self._agents = [
            SignalAgent(f"sig_agent_INT_{i}", f"INT_{i}") for i in range(1, 7)
        ] + [EmergencyAgent("em_agent"), CongestionAgent("cg_agent")]

        for agent in self._agents:
            self._agent_tasks.append(asyncio.create_task(
                self._run_agent(agent), name=f"agent_{agent.agent_id}"))
        logger.info("DEMO: {} agents started", len(self._agents))

        sim = SimTrafficNode()
        self._sim_task = asyncio.create_task(sim.run(), name="sim_traffic_node")
        logger.info("DEMO: traffic simulator started")

    @staticmethod
    async def _run_agent(agent) -> None:
        await agent.start()
        # agent.start() spawns its loops as tasks and returns; park a dummy
        # await so the wrapper task stays alive and shows exceptions.
        while True:
            await asyncio.sleep(3600)

    async def stop(self) -> None:
        for agent in self._agents:
            try:
                agent.stop()
            except Exception:
                pass
        for task in self._agent_tasks + [self._sim_task]:
            if task and not task.done():
                task.cancel()


_demo = DemoStack()
_override_pub: zmq.asyncio.Socket | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _override_pub
    zmq_task = asyncio.create_task(_zmq_subscriber_loop(), name="zmq_sub_loop")
    ws_task = asyncio.create_task(_ws_broadcast_loop(), name="ws_broadcast_loop")

    ctx = zmq.asyncio.Context.instance()
    _override_pub = ctx.socket(zmq.PUB)
    _override_pub.connect(settings.ZMQ_BROKER_FRONTEND)
    await asyncio.sleep(0.5)   # let the publisher connect before first use

    if settings.DEMO_MODE:
        await _demo.start()
    try:
        yield
    finally:
        if settings.DEMO_MODE:
            await _demo.stop()
        zmq_task.cancel()
        ws_task.cancel()
        if _override_pub is not None:
            _override_pub.close(linger=0)


app = FastAPI(title="Traffic Intelligence API", version="2.0.0", lifespan=lifespan)

# ── Mount static files (dashboard assets) ────────────────────────────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    message: str


# ── REST endpoints ───────────────────────────────────────────────────────────
@app.get("/intersections")
def list_intersections():
    return [_get_intersection_state(i) for i in _INTERSECTIONS]


@app.get("/intersections/{iid}/state")
def get_state(iid: str):
    if iid not in _INTERSECTIONS:
        from fastapi import HTTPException
        raise HTTPException(404, f"{iid} not found")
    return _get_intersection_state(iid)


@app.get("/violations")
def get_violations(limit: int = 50):
    return _violations[:limit]


@app.get("/violations/history")
def get_violation_history(limit: int = 100):
    rows = event_store.get_recent_violations(limit=limit)
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "intersection_id": r.intersection_id,
            "violation_type": r.violation_type,
            "vehicle_id": r.vehicle_id,
            "vehicle_class": r.vehicle_class,
            "speed": r.speed,
            "license_plate": r.license_plate,
        }
        for r in rows
    ]


@app.get("/accidents")
def get_accidents():
    return [a for a in _accidents if a["status"] == "ACTIVE"]


@app.get("/alerts")
def get_alerts():
    return _alerts[:20]


@app.get("/stats")
def get_stats():
    states = [_get_intersection_state(i) for i in _INTERSECTIONS]
    total_q = sum(s["total_queue"] for s in states)
    throughput = sum(_live_throughput.values())
    return {
        "throughput": round(throughput),
        "avg_wait": round(total_q * 2.3, 1),
        "total_vehicles": sum(_live_totals.values()),
        "violations_today": len(_violations),
        "active_accidents": sum(1 for a in _accidents if a["status"] == "ACTIVE"),
        "demo_mode": settings.DEMO_MODE,
    }


@app.post("/signals/{iid}/override")
async def override_signal(iid: str, req: SignalOverrideRequest):
    if iid not in _INTERSECTIONS:
        from fastapi import HTTPException
        raise HTTPException(404)

    await _override_pub.send_string(f"signals.override {json.dumps({
        'intersection_id': iid,
        'active': req.active,
        'force_phase': req.force_phase,
    })}")

    return {"status": "ok", "intersection": iid, "active": req.active}


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    from api.chatbot import chatbot
    network_state = {
        "intersections": [_get_intersection_state(i) for i in _INTERSECTIONS],
        "violations_today": len(_violations),
        "accidents": [a for a in _accidents if a.get("status") == "ACTIVE"],
    }
    reply = chatbot.chat(req.message, network_state)
    return {"reply": reply}


# ── Dashboard HTML (served at root) ──────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the standalone dashboard."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Dashboard not found - run build step</h1>", status_code=404)


# ── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws/live")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    await ws.send_text(json.dumps({"topic": "tick", "payload": _ws_tick_payload()}))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
