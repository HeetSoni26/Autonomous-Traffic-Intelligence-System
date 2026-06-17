from ray.rllib.algorithms.ppo import PPOConfig
from rl.multi_env import MultiIntersectionEnv

def get_policy_config():
    """
    Defines the MAPPO (Multi-Agent PPO) policy configuration.
    """
    config = (
        PPOConfig()
        .environment(env=MultiIntersectionEnv, env_config={"num_agents": 4})
        .framework("torch")
        .rollouts(num_rollout_workers=2)
        .training(
            gamma=0.99,
            lr=1e-4,
            train_batch_size=1000,
            sgd_minibatch_size=128
        )
        .multi_agent(
            # Parameter sharing: all intersections use the same policy network
            policies={"shared_policy"},
            policy_mapping_fn=lambda agent_id, episode, worker, **kwargs: "shared_policy"
        )
    )
    return config
