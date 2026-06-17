import gymnasium as gym
from gymnasium import spaces
import numpy as np
from simulation.sumo_bridge import SumoBridge

class TrafficEnvironment(gym.Env):
    """
    OpenAI Gym environment for a single intersection.
    """
    def __init__(self, config: dict):
        super().__init__()
        self.sumo_cfg = config.get("sumo_cfg", "simulation/sumo_config/network.sumocfg")
        self.tls_id = config.get("tls_id", "INT_1")
        
        # State: queues(4), wait_times(4), phase(4), time_since_switch(1) = 13
        self.observation_space = spaces.Box(
            low=0, high=np.inf, shape=(13,), dtype=np.float32
        )
        
        # Action: 0:keep, 1:switch_next
        self.action_space = spaces.Discrete(2)
        
        self.bridge = None
        self.edges = ["N_in", "S_in", "E_in", "W_in"]
        self.current_phase = 0
        self.time_since_switch = 0
        self.step_count = 0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self.bridge:
            self.bridge.close()
            
        self.bridge = SumoBridge(self.sumo_cfg)
        self.bridge.start()
        
        self.current_phase = 0
        self.time_since_switch = 0
        self.step_count = 0
        
        return self._get_obs(), {}

    def _get_obs(self):
        queues = [self.bridge.get_queue_length(edge) for edge in self.edges]
        waits = [self.bridge.get_avg_wait_time(edge) for edge in self.edges]
        
        phase_onehot = [0, 0, 0, 0]
        phase_onehot[self.current_phase] = 1
        
        obs = queues + waits + phase_onehot + [self.time_since_switch]
        return np.array(obs, dtype=np.float32)

    def step(self, action):
        if action == 1: # switch phase
            self.current_phase = (self.current_phase + 1) % 4
            self.time_since_switch = 0
        else:
            self.time_since_switch += 1
            
        self.bridge.set_phase(self.tls_id, self.current_phase)
        
        # Advance simulation by 5 seconds per decision step
        for _ in range(5):
            self.bridge.step()
            
        self.step_count += 5
        
        obs = self._get_obs()
        
        # Calculate Reward
        queues = obs[0:4]
        waits = obs[4:8]
        
        # Reward shaping logic
        # Negative reward for waiting time and queue length
        reward = -0.5 * sum(waits) - 0.5 * sum(queues)
        if action == 1:
            reward -= 5.0 # penalty for switching
            
        done = self.step_count >= 3600 # End episode after 1 hour of simulation time
        truncated = False
        
        return obs, float(reward), done, truncated, {}

    def close(self):
        if self.bridge:
            self.bridge.close()
