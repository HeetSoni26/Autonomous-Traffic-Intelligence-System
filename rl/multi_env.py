from ray.rllib.env.multi_agent_env import MultiAgentEnv
from gymnasium import spaces
import numpy as np
from rl.environment import TrafficEnvironment

class MultiIntersectionEnv(MultiAgentEnv):
    """
    Ray RLlib wrapper for multi-agent traffic control.
    Instantiates multiple TrafficEnvironments (one per intersection) 
    and steps them synchronously (or communicates via SUMO bridge).
    """
    def __init__(self, config):
        super().__init__()
        self.num_agents = config.get("num_agents", 4)
        self.agent_ids = [f"INT_{i}" for i in range(1, self.num_agents + 1)]
        
        # In a real setup, all agents would share a single SUMO simulation.
        # For simplicity here, we assume the TrafficEnvironment can handle it or we use sumo-rl.
        # This is a skeleton of how RLlib expects a MultiAgentEnv.
        self.envs = {agent_id: TrafficEnvironment({"tls_id": agent_id, **config}) for agent_id in self.agent_ids}
        
        # Share observation and action spaces across agents
        self._obs_space_in_preferred_format = True
        self.observation_space = self.envs[self.agent_ids[0]].observation_space
        self.action_space = self.envs[self.agent_ids[0]].action_space
        self._agent_ids = set(self.agent_ids)

    def reset(self, *, seed=None, options=None):
        obs = {}
        for agent_id in self.agent_ids:
            obs[agent_id], _ = self.envs[agent_id].reset(seed=seed)
        return obs, {}

    def step(self, action_dict):
        obs, rewards, terminateds, truncateds, infos = {}, {}, {}, {}, {}
        
        # In a true joint simulation, we'd apply all actions then step SUMO once.
        # Here we simulate the interface.
        for agent_id, action in action_dict.items():
            env = self.envs[agent_id]
            o, r, d, t, i = env.step(action)
            obs[agent_id] = o
            rewards[agent_id] = r
            terminateds[agent_id] = d
            truncateds[agent_id] = t
            infos[agent_id] = i
            
        terminateds["__all__"] = all(terminateds.values())
        truncateds["__all__"] = all(truncateds.values())
        
        return obs, rewards, terminateds, truncateds, infos
        
    def close(self):
        for env in self.envs.values():
            env.close()
