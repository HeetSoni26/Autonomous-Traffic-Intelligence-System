"""
api/main.py  —  FastAPI REST + WebSocket + Static Dashboard
Listens to real ZeroMQ events from the Vision Node and Signal Agents to drive the dashboard.
Includes a fallback simulation mode if SIM_MODE=1.
"""
from __future__ import annotations

import asyncio
import sys
import os

# Windows: uvicorn uses ProactorEventLoop which is incompatible with ZMQ async reads.
# Patch BEFORE any zmq import.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import math
import random
import time
from datetime import datetime, timezone
from typing import List

import zmq
import zmq.asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import config.logging_config  # noqa: configure loguru
from loguru import logger

from api.schemas import (
    IntersectionState, ViolationResponse,
    AccidentResponse, SignalOverrideRequest,
)
from api.websocket_manager import ws_manager
from agents.message_bus import MessageBus
from database.event_store import event_store
from config.settings import settings

app  = FastAPI(title="Traffic Intelligence API", version="1.0.0")
_bus = MessageBus()

# ── Mount static files (dashboard HTML/CSS/JS) ────────────────────────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# ── Intersection registry ─────────────────────────────────────────────────────
_INTERSECTIONS = {
    "INT_1": {"lat": 19.0760, "lon": 72.8777, "name": "MG Road & FC Road"},
    "INT_2": {"lat": 19.0800, "lon": 72.8810, "name": "Andheri East Junction"},
    "INT_3": {"lat": 19.0820, "lon": 72.8850, "name": "Bandra Kurla Complex"},
    "INT_4": {"lat": 19.0740, "lon": 72.8850, "name": "Worli Sea Link Entry"},
    "INT_5": {"lat": 19.0780, "lon": 72.8820, "name": "Dadar Central"},
    "INT_6": {"lat": 19.0760, "lon": 72.8840, "name": "Parel Junction"},
}

# ── Live State ────────────────────────────────────────────────────────────────
_live_signals: dict = {iid: {"phase": "NS_GREEN", "approaches": {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"}} for iid in _INTERSECTIONS}
_live_queues: dict = {iid: {"N": 0, "S": 0, "E": 0, "W": 0} for iid in _INTERSECTIONS}
_live_levels: dict = {iid: "FREE" for iid in _INTERSECTIONS}
_violations: List[dict] = []
_accidents:  List[dict] = []
_ACTIVE_ACCIDENT: dict | None = None

SIM_MODE = os.environ.get("SIM_MODE", "0") == "1"


def _get_intersection_state(iid: str) -> dict:
    meta = _INTERSECTIONS[iid]
    sig = _live_signals.get(iid, {})
    
    queue = _live_queues.get(iid, {"N": 0, "S": 0, "E": 0, "W": 0})
    level = _live_levels.get(iid, "FREE")
    total_q = sum(queue.values())

    return {
        "id":               iid,
        "name":             meta["name"],
        "lat":              meta["lat"],
        "lon":              meta["lon"],
        "phase":            sig.get("phase", "NS_GREEN"),
        "phase_idx":        0, # Not strictly needed by UI
        "approaches":       sig.get("approaches", {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"}),
        "congestion_level": level,
        "queue_lengths":    queue,
        "total_queue":      total_q,
    }


# ── Background tasks ──────────────────────────────────────────────────────────
async def _zmq_subscriber_loop() -> None:
    """Listens to real events from Vision Nodes and Signal Agents."""
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.connect(settings.ZMQ_BROKER_BACKEND)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")  # subscribe to all

    logger.info(f"API ZMQ Subscriber connected to {settings.ZMQ_BROKER_BACKEND}")

    global _ACTIVE_ACCIDENT
    try:
        while True:
            msg = await sub.recv_string()
            parts = msg.split(" ", 1)
            if len(parts) != 2: continue
            topic, payload_str = parts[0], parts[1]
            try:
                payload = json.loads(payload_str)
            except:
                continue

            iid = payload.get("intersection_id")

            if topic.startswith("signals.") and iid:
                _live_signals[iid] = {
                    "phase": payload.get("phase", "NS_GREEN"),
                    "approaches": payload.get("approaches", {})
                }
            
            elif topic.startswith("congestion.") and iid:
                _live_queues[iid] = payload.get("queue_lengths", _live_queues.get(iid))
                _live_levels[iid] = payload.get("level", _live_levels.get(iid))

            elif topic == "violations":
                ev = payload.copy()
                ev["timestamp"] = datetime.now(timezone.utc).isoformat()
                ev["id"] = len(_violations) + 1
                _violations.insert(0, ev)
                if len(_violations) > 100:
                    _violations.pop()

            elif topic == "accidents":
                ev = payload.copy()
                ev["timestamp"] = datetime.now(timezone.utc).isoformat()
                ev["id"] = len(_accidents) + 1
                ev["status"] = "ACTIVE"
                _ACTIVE_ACCIDENT = ev
                _accidents.insert(0, ev)

    except asyncio.CancelledError:
        pass
    finally:
        sub.close()


def _sim_tick() -> None:
    """Optional fallback simulation if no cameras are available."""
    global _ACTIVE_ACCIDENT
    now_str = datetime.now(timezone.utc).isoformat()

    # Random queues
    for iid in _INTERSECTIONS:
        t    = time.time()
        base = 5 + 10 * abs(math.sin(t / 60 + hash(iid) % 10))
        queue = {
            "N": max(0, int(base + random.gauss(0, 2))),
            "S": max(0, int(base * 0.8 + random.gauss(0, 2))),
            "E": max(0, int(base * 0.6 + random.gauss(0, 1.5))),
            "W": max(0, int(base * 0.7 + random.gauss(0, 1.5))),
        }
        _live_queues[iid] = queue
        total_q = sum(queue.values())
        if total_q > 40: _live_levels[iid] = "GRIDLOCK"
        elif total_q > 25: _live_levels[iid] = "HEAVY"
        elif total_q > 12: _live_levels[iid] = "MODERATE"
        else:              _live_levels[iid] = "FREE"

    # Auto-clear accident after 60 s
    if _ACTIVE_ACCIDENT and (
        datetime.now(timezone.utc) - datetime.fromisoformat(_ACTIVE_ACCIDENT["timestamp"])
    ).seconds > 60:
        _ACTIVE_ACCIDENT["status"] = "CLEARED"
        _ACTIVE_ACCIDENT = None


async def _ws_broadcast_loop() -> None:
    while True:
        if SIM_MODE:
            _sim_tick()

        data = {
            "intersections": [_get_intersection_state(i) for i in _INTERSECTIONS],
            "violations":    _violations[:10],
            "accidents":     [a for a in _accidents[:5] if a["status"] == "ACTIVE"],
        }
        await ws_manager.broadcast(json.dumps({"topic": "tick", "payload": data}))
        await asyncio.sleep(1)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_zmq_subscriber_loop(), name="zmq_sub_loop")
    asyncio.create_task(_ws_broadcast_loop(), name="ws_broadcast_loop")


# ── REST endpoints ────────────────────────────────────────────────────────────
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


@app.get("/accidents")
def get_accidents():
    return [a for a in _accidents if a["status"] == "ACTIVE"]


@app.get("/stats")
def get_stats():
    states = [_get_intersection_state(i) for i in _INTERSECTIONS]
    total_q = sum(s["total_queue"] for s in states)
    avg_wait = round(total_q * 2.3, 1)
    throughput = max(0, 720 - total_q * 4)
    return {
        "throughput":    throughput,
        "avg_wait":      avg_wait,
        "total_vehicles": total_q + random.randint(80, 120),
        "violations_today": len(_violations),
        "active_accidents": sum(1 for a in _accidents if a["status"] == "ACTIVE"),
    }


@app.post("/signals/{iid}/override")
def override_signal(iid: str, req: SignalOverrideRequest):
    if iid not in _INTERSECTIONS:
        from fastapi import HTTPException
        raise HTTPException(404)
    
    # We still want to let ZMQ know via MessageBus
    _bus.publish("signals.override", {"intersection_id": iid, "active": req.active, "force_phase": req.force_phase})

    return {"status": "ok", "intersection": iid, "active": req.active}


# ── Dashboard HTML (served at root) ──────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the standalone dashboard."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Dashboard not found — run build step</h1>", status_code=404)


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/live")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    data = {
        "intersections": [_get_intersection_state(i) for i in _INTERSECTIONS],
        "violations":    _violations[:10],
        "accidents":     [a for a in _accidents[:5] if a["status"] == "ACTIVE"],
    }
    await ws.send_text(json.dumps({"topic": "tick", "payload": data}))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
