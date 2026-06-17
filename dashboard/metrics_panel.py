"""
dashboard/metrics_panel.py
KPI cards, charts, and scrolling event log for the Streamlit dashboard.
Uses only standard library + streamlit — no package-level imports.
"""
from __future__ import annotations

import random
from datetime import datetime
from typing import Any, Dict, List

import streamlit as st


def render_kpi_row(metrics: Dict[str, Any]) -> None:
    """Top KPI metric cards in a 4-column row."""
    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "🚗 Throughput (veh/hr)",
        f"{metrics.get('throughput', 0):,}",
    )
    c2.metric(
        "⏱ Avg Wait (s)",
        f"{metrics.get('avg_wait', 0.0):.1f}",
    )
    accidents = metrics.get("active_accidents", 0)
    c3.metric(
        "🚨 Active Accidents",
        str(accidents),
        delta="CRITICAL" if accidents else "Clear",
        delta_color="inverse",
    )
    c4.metric(
        "⚠️ Violations (recent)",
        str(metrics.get("violations", 0)),
    )


def render_signal_status(intersections: List[Dict]) -> None:
    """Compact signal-phase pills for each intersection."""
    st.subheader("🚦 Signal Phases")
    cols = st.columns(len(intersections) if intersections else 1)
    _PHASE_EMOJI = {
        "NS_GREEN":  "🟢 N/S",
        "EW_GREEN":  "🟢 E/W",
        "ALL_RED":   "🔴 ALL",
        "ALL_RED_2": "🔴 ALL",
        "UNKNOWN":   "⚪ ?",
    }
    for col, idata in zip(cols, intersections):
        phase = idata.get("phase", "UNKNOWN")
        col.markdown(
            f"**{idata['id']}**  \n{_PHASE_EMOJI.get(phase, phase)}",
            unsafe_allow_html=False,
        )


def render_event_log(events: List[Dict]) -> None:
    """Colour-coded scrollable event feed."""
    st.subheader("📋 Event Feed")
    with st.container(height=260):
        if not events:
            st.caption("No recent events — system nominal.")
            return
        for ev in events[:30]:
            ts  = ev.get("time", "")
            msg = ev.get("msg", "")
            etype = ev.get("type", "INFO")
            if etype == "ACCIDENT":
                st.error(f"🚨 {ts} — {msg}")
            elif etype == "VIOLATION":
                st.warning(f"⚠️ {ts} — {msg}")
            elif etype == "SIGNAL":
                st.info(f"🚦 {ts} — {msg}")
            else:
                st.caption(f"ℹ️ {ts} — {msg}")


def render_queue_chart(intersections: List[Dict]) -> None:
    """Bar chart of queue lengths per intersection."""
    import pandas as pd

    if not intersections:
        return

    rows = []
    for i in intersections:
        ql = i.get("queue_lengths", {})
        for approach, count in ql.items():
            rows.append({"Intersection": i["id"], "Approach": approach, "Queue": count})

    if not rows:
        return

    df = pd.DataFrame(rows)
    st.subheader("📊 Queue Lengths by Approach")
    st.bar_chart(df.pivot(index="Approach", columns="Intersection", values="Queue").fillna(0))
