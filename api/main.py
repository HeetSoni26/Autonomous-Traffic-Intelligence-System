"""
api/main.py  —  FastAPI REST + WebSocket + Static Dashboard
Serves simulated live traffic data so the dashboard always has content.
"""
from __future__ import annotations

import asyncio
import sys

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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

import config.logging_config  # noqa: configure loguru

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

_PHASES      = ["NS_GREEN", "ALL_RED", "EW_GREEN", "ALL_RED_2"]
_phase_state: dict = {iid: {"idx": i % 4, "t": time.time()} for i, iid in enumerate(_INTERSECTIONS)}

# ── Live simulation state ─────────────────────────────────────────────────────
_sim_violations: List[dict] = []
_sim_accidents:  List[dict] = []

_V_TYPES   = ["RED_LIGHT", "SPEEDING", "WRONG_WAY"]
_V_CLASSES = ["car", "truck", "motorcycle", "bus"]
_ACTIVE_ACCIDENT: dict | None = None


def _sim_tick() -> None:
    """Called every second to advance simulation state."""
    global _ACTIVE_ACCIDENT
    now_str = datetime.now(timezone.utc).isoformat()

    # Advance signal phases (30 s NS_GREEN, 5 s ALL_RED, 30 s EW_GREEN, 5 s ALL_RED)
    DURATIONS = [30, 5, 30, 5]
    for iid, st in _phase_state.items():
        elapsed = time.time() - st["t"]
        if elapsed >= DURATIONS[st["idx"]]:
            st["idx"] = (st["idx"] + 1) % 4
            st["t"]   = time.time()

    # Random violation (5 % chance per tick)
    if random.random() < 0.05:
        iid = random.choice(list(_INTERSECTIONS.keys()))
        ev  = {
            "id":              len(_sim_violations) + 1,
            "timestamp":       now_str,
            "intersection_id": iid,
            "violation_type":  random.choice(_V_TYPES),
            "vehicle_class":   random.choice(_V_CLASSES),
            "speed":           round(random.uniform(55, 120), 1),
            "confidence":      round(random.uniform(0.7, 0.98), 2),
        }
        _sim_violations.insert(0, ev)
        if len(_sim_violations) > 100:
            _sim_violations.pop()

    # Random accident (0.5 % chance)
    if _ACTIVE_ACCIDENT is None and random.random() < 0.005:
        iid = random.choice(list(_INTERSECTIONS.keys()))
        _ACTIVE_ACCIDENT = {
            "id":                len(_sim_accidents) + 1,
            "timestamp":         now_str,
            "intersection_id":   iid,
            "severity_score":    round(random.uniform(0.4, 0.95), 2),
            "involved_vehicles": random.randint(2, 4),
            "status":            "ACTIVE",
        }
        _sim_accidents.insert(0, _ACTIVE_ACCIDENT)

    # Auto-clear accident after 60 s
    if _ACTIVE_ACCIDENT and (
        datetime.now(timezone.utc) - datetime.fromisoformat(_ACTIVE_ACCIDENT["timestamp"])
    ).seconds > 60:
        _ACTIVE_ACCIDENT["status"] = "CLEARED"
        _ACTIVE_ACCIDENT = None


def _get_intersection_state(iid: str) -> dict:
    st  = _phase_state[iid]
    idx = st["idx"]
    phase = _PHASES[idx]
    if phase == "NS_GREEN":
        approaches = {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"}
    elif phase == "EW_GREEN":
        approaches = {"N": "RED", "S": "RED", "E": "GREEN", "W": "GREEN"}
    else:
        approaches = {"N": "RED", "S": "RED", "E": "RED", "W": "RED"}

    # Simulate queue lengths — use a sine wave for realism
    t    = time.time()
    base = 5 + 10 * abs(math.sin(t / 60 + hash(iid) % 10))
    queue = {
        "N": max(0, int(base + random.gauss(0, 2))),
        "S": max(0, int(base * 0.8 + random.gauss(0, 2))),
        "E": max(0, int(base * 0.6 + random.gauss(0, 1.5))),
        "W": max(0, int(base * 0.7 + random.gauss(0, 1.5))),
    }
    total_q = sum(queue.values())
    if total_q > 40: level = "GRIDLOCK"
    elif total_q > 25: level = "HEAVY"
    elif total_q > 12: level = "MODERATE"
    else:              level = "FREE"

    meta = _INTERSECTIONS[iid]
    return {
        "id":               iid,
        "name":             meta["name"],
        "lat":              meta["lat"],
        "lon":              meta["lon"],
        "phase":            phase,
        "phase_idx":        idx,
        "approaches":       approaches,
        "congestion_level": level,
        "queue_lengths":    queue,
        "total_queue":      total_q,
    }


# ── Background tasks ──────────────────────────────────────────────────────────
async def _sim_loop() -> None:
    while True:
        _sim_tick()
        # Broadcast live update to all WebSocket clients
        data = {
            "intersections": [_get_intersection_state(i) for i in _INTERSECTIONS],
            "violations":    _sim_violations[:10],
            "accidents":     [a for a in _sim_accidents[:5] if a["status"] == "ACTIVE"],
        }
        await ws_manager.broadcast(json.dumps({"topic": "tick", "payload": data}))
        await asyncio.sleep(1)


@app.on_event("startup")
async def startup() -> None:
    # ZMQ async bridge disabled on Windows (ProactorEventLoop incompatibility).
    # The built-in _sim_loop() drives all WebSocket updates instead.
    asyncio.create_task(_sim_loop(), name="sim_loop")


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
    return _sim_violations[:limit]


@app.get("/accidents")
def get_accidents():
    return [a for a in _sim_accidents if a["status"] == "ACTIVE"]


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
        "violations_today": len(_sim_violations),
        "active_accidents": sum(1 for a in _sim_accidents if a["status"] == "ACTIVE"),
    }


@app.post("/signals/{iid}/override")
def override_signal(iid: str, req: SignalOverrideRequest):
    if iid not in _INTERSECTIONS:
        from fastapi import HTTPException
        raise HTTPException(404)
    if req.force_phase and req.force_phase in _PHASES:
        _phase_state[iid]["idx"] = _PHASES.index(req.force_phase)
        _phase_state[iid]["t"]   = time.time()
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
    # Send initial state immediately
    data = {
        "intersections": [_get_intersection_state(i) for i in _INTERSECTIONS],
        "violations":    _sim_violations[:10],
        "accidents":     [a for a in _sim_accidents[:5] if a["status"] == "ACTIVE"],
    }
    await ws.send_text(json.dumps({"topic": "tick", "payload": data}))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
