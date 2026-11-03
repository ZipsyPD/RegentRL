# Headless STS2 Simulator

This directory contains the headless Slay the Spire 2 simulation environment used to train and evaluate RegentRL's reinforcement learning agents.

## Origin

Based on [zhiyue/sts2-rl-agent](https://github.com/zhiyue/sts2-rl-agent).

The simulator has been integrated into RegentRL so that training scripts can import `sts2_env` without requiring a separate local project directory.

RegentRL's PPO training scripts are located in `../training/`, while the live game-inference implementation is located in `../python/` and `../RegentRLCode/`.

## Installation

From the RegentRL repository root:

```powershell
py -3.12 -m venv .venv-training
.\.venv-training\Scripts\python.exe -m pip install -e ".\simulator[train]"
```

## Purpose

The simulator executes gameplay without launching the graphical game, allowing PPO to collect trajectories and optimize a policy.

The simulator is an approximate model of STS2 mechanics and may differ from the actual game.

## Attribution and rights

The simulator is derived from upstream research software and is not an official Mega Crit product. Upstream authorship and any applicable source-code, game-content, and redistribution rights remain with their
