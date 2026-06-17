"""
dashboard/map_view.py
PyDeck 3D intersection map with congestion-coloured markers.
Uses RELATIVE imports only — no package-level prefix needed.
"""
from __future__ import annotations

from typing import List, Dict, Any

import pydeck as pdk

# Hardcoded map coordinates for demo intersections
# Replace with real GPS lat/lon from your deployment config
_INTERSECTION_COORDS: Dict[str, List[float]] = {
    "INT_1": [72.8777, 19.0760],   # Mumbai demo
    "INT_2": [72.8800, 19.0780],
    "INT_3": [72.8820, 19.0800],
    "INT_4": [72.8840, 19.0820],
}

_LEVEL_COLOR: Dict[str, List[int]] = {
    "FREE":     [0,   210, 100, 180],
    "MODERATE": [255, 200,   0, 180],
    "HEAVY":    [255, 120,   0, 180],
    "GRIDLOCK": [220,  30,  30, 220],
}


def build_deck(intersections: List[Dict[str, Any]]) -> pdk.Deck:
    """
    Build a PyDeck Deck object from a list of intersection state dicts.
    Each dict must have keys: id, phase, congestion_level, queue_lengths.
    """
    data = []
    for i in intersections:
        iid  = i.get("id", "")
        lon, lat = _INTERSECTION_COORDS.get(iid, [72.88, 19.07])
        level = i.get("congestion_level", "FREE")
        ql    = i.get("queue_lengths", {})
        q_sum = sum(ql.values()) if ql else 0

        data.append({
            "id":        iid,
            "position":  [lon, lat],
            "radius":    60 + q_sum * 5,
            "color":     _LEVEL_COLOR.get(level, [100, 100, 100, 180]),
            "tooltip":   f"{iid}\nPhase: {i.get('phase','?')}\nCongestion: {level}\nQueue: {q_sum}",
        })

    scatter = pdk.Layer(
        "ScatterplotLayer",
        data,
        pickable=True,
        opacity=0.85,
        stroked=True,
        filled=True,
        radius_scale=1,
        radius_min_pixels=14,
        radius_max_pixels=80,
        line_width_min_pixels=2,
        get_position="position",
        get_radius="radius",
        get_fill_color="color",
        get_line_color=[255, 255, 255, 200],
    )

    view_state = pdk.ViewState(
        longitude=72.882,
        latitude=19.078,
        zoom=14,
        pitch=45,
        bearing=0,
    )

    return pdk.Deck(
        layers=[scatter],
        initial_view_state=view_state,
        tooltip={"text": "{tooltip}"},
        map_style="mapbox://styles/mapbox/dark-v10",
    )
