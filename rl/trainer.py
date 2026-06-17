import argparse
import ray
from ray import tune
from ray.tune.registry import register_env
from rl.multi_env import MultiIntersectionEnv
from rl.policy import get_policy_config
from config.settings import settings

def env_creator(env_config):
    return MultiIntersectionEnv(env_config)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--scenario", type=str, default="rush_hour")
    args = parser.parse_args()

    ray.init()
    register_env("MultiTrafficEnv", env_creator)
    
    config = get_policy_config()
    config.environment("MultiTrafficEnv")

    print(f"Starting MAPPO training for {args.iterations} iterations...")
    
    tune.run(
        "PPO",
        config=config.to_dict(),
        stop={"training_iteration": args.iterations},
        checkpoint_freq=50,
        checkpoint_at_end=True,
        local_dir=settings.RL_CHECKPOINT_DIR,
        name="TrafficIntelligence_MAPPO"
    )
    
    print("Training complete.")
