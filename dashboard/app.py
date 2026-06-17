"""
dashboard/app.py
Streamlit real-time Traffic Intelligence Dashboard.

IMPORTANT — import path fix:
  Streamlit executes this file directly, so 'dashboard/' is on sys.path,
  not the project root. We prepend the parent directory so that
  config / database / agents packages resolve correctly.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# ── Fix Python path BEFORE any project imports ────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
# ─────────────────────────────────────────────────────────────────────────────

import requests
import streamlit as st

# Now project packages resolve correctly
from map_view     import build_deck       # relative — same dashboard/ dir
from metrics_panel import (               # relative — same dashboard/ dir
    render_kpi_row,
    render_signal_status,
    render_event_log,
    render_queue_chart,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Traffic Intelligence",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

API_BASE = "http://127.0.0.1:8000"


# ── Data fetchers (graceful empty on API down) ────────────────────────────────
def _get(path: str, default=None):
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=2)
        r.raise_for_status()
        return r.json()
    except Exception:
        return default if default is not None else []


# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Dark theme tweaks */
    .stMetric > div { border-radius: 10px; padding: 12px; }
    header { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🚦 Autonomous Multi-Agent Traffic Intelligence System")
st.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}  |  API: {API_BASE}")
st.divider()

# ── Fetch data ────────────────────────────────────────────────────────────────
intersections: List[Dict] = _get("/intersections", [])
violations:    List[Dict] = _get("/violations?limit=20", [])
accidents:     List[Dict] = _get("/accidents", [])

# ── KPI row ───────────────────────────────────────────────────────────────────
total_queue = sum(
    sum(i.get("queue_lengths", {}).values())
    for i in intersections
)
metrics = {
    "throughput":       max(0, 600 - total_queue * 3),   # rough proxy
    "avg_wait":         total_queue * 2.5,
    "active_accidents": len(accidents),
    "violations":       len(violations),
}
render_kpi_row(metrics)
st.divider()

# ── Main layout: Map | Events ─────────────────────────────────────────────────
col_map, col_right = st.columns([3, 2])

with col_map:
    st.subheader("🗺 Network Map")
    if intersections:
        deck = build_deck(intersections)
        st.pydeck_chart(deck, width="stretch")
    else:
        st.info("Waiting for API connection …  \nStart the API with `uvicorn api.main:app --port 8000`")

with col_right:
    render_signal_status(intersections)

    st.divider()

    # Build event list
    events: List[Dict] = []
    for a in accidents:
        events.append({
            "type": "ACCIDENT",
            "time": a.get("timestamp", "")[:19],
            "msg":  f"Accident at {a.get('intersection_id','?')} — severity {a.get('severity_score',0):.2f}",
        })
    for v in violations:
        events.append({
            "type": "VIOLATION",
            "time": v.get("timestamp", "")[:19],
            "msg":  f"{v.get('violation_type','?')} — {v.get('vehicle_class','?')} @ {v.get('intersection_id','?')}",
        })
    events.sort(key=lambda e: e.get("time", ""), reverse=True)
    render_event_log(events)

st.divider()
render_queue_chart(intersections)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
time.sleep(2)
st.rerun()
