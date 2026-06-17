import pytest
import asyncio
from agents.signal_agent import SignalAgent
from agents.emergency_agent import EmergencyAgent

@pytest.mark.asyncio
async def test_signal_phase_switch():
    agent = SignalAgent("test_agent", "INT_1")
    assert agent.current_phase_idx == 0
    assert agent.phases[0] == "NS_GREEN"
    
    agent._switch_phase(1)
    assert agent.current_phase_idx == 1
    assert agent.phases[1] == "ALL_RED"

@pytest.mark.asyncio
async def test_emergency_override_handling():
    agent = SignalAgent("test_agent", "INT_1")
    
    # Mock override message
    payload = {"intersection_id": "INT_1", "active": True, "force_phase": "ALL_RED"}
    await agent._handle_message("signals.override", payload)
    
    assert agent.override_active is True
    assert agent.phases[agent.current_phase_idx] == "ALL_RED"
