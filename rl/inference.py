import os
import glob
from ray.rllib.algorithms.ppo import PPO
from rl.policy import get_policy_config
from config.settings import settings
from loguru import logger
from ray.tune.registry import register_env
from rl.multi_env import MultiIntersectionEnv

def env_creator(env_config):
    return MultiIntersectionEnv(env_config)

class InferenceEngine:
    def __init__(self):
        self.algo = None
        self._load_latest_checkpoint()

    def _load_latest_checkpoint(self):
        import ray
        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True)
            
        register_env("MultiTrafficEnv", env_creator)
        
        # Find latest checkpoint
        search_path = os.path.join(settings.RL_CHECKPOINT_DIR, "TrafficIntelligence_MAPPO", "PPO_*", "checkpoint_*")
        checkpoints = glob.glob(search_path)
        
        if not checkpoints:
            logger.warning("No RL checkpoints found. Agents will use rule-based fallback.")
            return
            
        # Sort by modification time
        latest_checkpoint = max(checkpoints, key=os.path.getmtime)
        logger.info(f"Loading RL checkpoint from {latest_checkpoint}")
        
        config = get_policy_config()
        config.environment("MultiTrafficEnv")
        
        self.algo = PPO(config=config)
        self.algo.restore(latest_checkpoint)

    def get_action(self, agent_id: str, obs):
        if not self.algo:
            return None # Trigger fallback
        
        # Compute single action using the shared policy
        action = self.algo.compute_single_action(
            observation=obs,
            policy_id="shared_policy"
        )
        return action

# Singleton
inference_engine = InferenceEngine()
