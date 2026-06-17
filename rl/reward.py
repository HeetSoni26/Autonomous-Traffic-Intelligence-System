def compute_reward(queues, wait_times, action_taken, is_switching):
    """
    Reward shaping function extracted for modularity.
    r = - α * avg_wait_time - β * queue_length_sum + γ * vehicles_cleared - δ * phase_switches
    """
    alpha = 0.5
    beta = 0.5
    delta = 5.0
    
    wait_penalty = sum(wait_times) * alpha
    queue_penalty = sum(queues) * beta
    switch_penalty = delta if is_switching else 0.0
    
    return -(wait_penalty + queue_penalty + switch_penalty)
