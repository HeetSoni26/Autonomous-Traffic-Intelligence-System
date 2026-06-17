import pytest
import numpy as np
from rl.environment import TrafficEnvironment

# We mock SumoBridge to run tests without SUMO installed on the CI runner
class MockSumoBridge:
    def __init__(self, *args, **kwargs):
        self.queue = 5
        self.wait = 10.0
    def start(self): pass
    def step(self): pass
    def close(self): pass
    def get_queue_length(self, edge): return self.queue
    def get_avg_wait_time(self, edge): return self.wait
    def set_phase(self, tls, phase): pass

def test_env_step_reward():
    env = TrafficEnvironment({"tls_id": "INT_1"})
    # Inject mock
    env.bridge = MockSumoBridge()
    env.current_phase = 0
    env.time_since_switch = 0
    env.step_count = 0
    
    # Take step
    obs, reward, done, truncated, info = env.step(1) # Action 1: Switch phase
    
    # Expect negative reward based on queues and waits + switch penalty
    # waits = 10 * 4 = 40. queues = 5 * 4 = 20
    # Reward = -0.5*40 - 0.5*20 - 5.0 (penalty) = -20 - 10 - 5 = -35.0
    assert reward == -35.0
    assert env.current_phase == 1
    assert env.time_since_switch == 0
