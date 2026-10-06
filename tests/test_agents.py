"""
tests/test_agents.py
Unit tests for the SignalAgent against the real implementation.
"""
from agents.signal_agent import SignalAgent, _PHASES


async def test_signal_phase_switch():
    agent = SignalAgent("test_agent", "INT_1")
    try:
        assert agent._phase_idx == 0
        assert _PHASES[0] == "NS_GREEN"

        agent._force_phase("EW_GREEN")
        assert agent.current_phase == "EW_GREEN"
        approaches = agent.phase_for_approaches()
        assert approaches["E"] == "GREEN" and approaches["W"] == "GREEN"
        assert approaches["N"] == "RED" and approaches["S"] == "RED"
    finally:
        agent.stop()


async def test_emergency_override_handling():
    agent = SignalAgent("test_agent", "INT_1")
    try:
        payload = {"intersection_id": "INT_1", "active": True, "force_phase": "ALL_RED"}
        await agent.handle_message("signals.override", payload)

        assert agent._override_active is True
        assert agent.current_phase == "ALL_RED"
        assert all(v == "RED" for v in agent.phase_for_approaches().values())
    finally:
        agent.stop()


async def test_adaptive_split_reacts_to_queues():
    agent = SignalAgent("test_agent", "INT_1")
    try:
        # Heavy north/south demand should earn the NS axis a longer green.
        await agent.handle_message("congestion.INT_1", {
            "intersection_id": "INT_1",
            "queue_lengths": {"N": 20, "S": 16, "E": 2, "W": 3},
        })
        assert agent._phase_durations["NS_GREEN"] > agent._phase_durations["EW_GREEN"]
        assert agent._phase_durations["NS_GREEN"] <= 50.0
        assert agent._phase_durations["EW_GREEN"] >= 10.0
    finally:
        agent.stop()
