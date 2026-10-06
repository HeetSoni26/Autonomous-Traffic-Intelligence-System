"""
tests/test_sim_node.py
Sanity tests for the synthetic traffic generator: queue dynamics must
respect the signal state and the level classification must match the
congestion thresholds used by the real vision pipeline.
"""
from simulation.sim_node import IntersectionSim


def test_queues_build_while_red():
    sim = IntersectionSim("INT_1", seed=7)
    sim.queues = {"N": 5, "S": 4, "E": 3, "W": 2}
    sim.signal = {a: "RED" for a in "NSEW"}
    before = sum(sim.queues.values())

    for _ in range(30):
        sim.tick(t=1.0, incident=False)

    assert sum(sim.queues.values()) > before


def test_queues_drain_while_green():
    sim = IntersectionSim("INT_1", seed=7)
    sim.queues = {"N": 20, "S": 18, "E": 6, "W": 5}
    sim.signal = {a: "GREEN" for a in "NSEW"}

    for _ in range(12):
        sim.tick(t=1.0, incident=False)

    assert max(sim.queues.values()) < 10


def test_incident_floods_queue():
    sim = IntersectionSim("INT_1", seed=7)
    sim.queues = {"N": 0, "S": 0, "E": 0, "W": 0}
    sim.signal = {a: "RED" for a in "NSEW"}

    for _ in range(8):
        sim.tick(t=1.0, incident=True)

    assert max(sim.queues.values()) >= 10


def test_level_classification_thresholds():
    sim = IntersectionSim("INT_1", seed=7)

    sim.queues = {"N": 16, "S": 0, "E": 0, "W": 0}
    assert sim.classify() == "GRIDLOCK"
    sim.queues = {"N": 11, "S": 0, "E": 0, "W": 0}
    assert sim.classify() == "HEAVY"
    sim.queues = {"N": 5, "S": 0, "E": 0, "W": 0}
    assert sim.classify() == "MODERATE"
    sim.queues = {"N": 2, "S": 0, "E": 0, "W": 0}
    assert sim.classify() == "FREE"


def test_state_payload_shape():
    sim = IntersectionSim("INT_1", seed=7)
    payload = sim.state_payload()

    assert payload["intersection_id"] == "INT_1"
    assert set(payload["queue_lengths"].keys()) == {"N", "S", "E", "W"}
    assert payload["level"] in ("FREE", "MODERATE", "HEAVY", "GRIDLOCK")
    assert payload["total_vehicles"] >= sum(payload["queue_lengths"].values())
    assert isinstance(payload["throughput_per_hour"], int)
