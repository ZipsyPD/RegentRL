# RegentRL Training

This directory contains RegentRL's PPO training and counterfactual evaluation scripts.

## Components

- `train_regentrl_fullrun_ppo_v4.py` — Trains the actor-critic reinforcement learning policy using PyTorch and Proximal Policy Optimization.
- `experiment_card_branches.py` — Evaluates alternative card-reward decisions by simulating continuations from the same starting game state.

## Results

The PPO agent was trained for 1 million environment steps.

In a 50-episode checkpoint-selection evaluation, the mean floor reached increased from 5.76 at 50K steps to 8.84 at approximately 850K steps.

A separate experiment evaluated 2,000 reward-decision states, including 4,014 card-versus-Skip comparisons.

These results measure floor progression rather than successful game completion.

## Dependencies

The scripts depend on the separate `sts2-rl-agent` headless simulator and its Python modules. They are included here to document the training and evaluation implementation, but are not standalone executables.

The simulator is maintained separately; its original authorship and redistribution terms should be respected.
