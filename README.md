# RegentRL

**A reinforcement learning agent that trains in a headless Slay the Spire 2 simulator and plays the real game through a C# mod and Python inference server.**

RegentRL combines a PyTorch Proximal Policy Optimization (PPO) training pipeline, a headless game simulator, and a live game-integration bridge.

The system supports combat and noncombat decisions, including card rewards, map navigation, events, and shops.

## Architecture

```text
                TRAINING
   PPO Trainer (training/)
              |
              v
   Headless STS2 Simulator
       (simulator/)
              |
              v
     PyTorch Checkpoint
          (*.pt)

                INFERENCE
     Trained Checkpoint
              |
              v
   Python Agent Server
   (python/agent_server.py)
              |
              | TCP / JSON
              v
      RegentRL C# Mod
      (RegentRLCode/)
              |
              v
       Slay the Spire 2
```

Training occurs in the headless simulator. During inference, the trained policy chooses actions using observations from the real game.

## Requirements

- Windows with PowerShell (tested development environment)
- Python 3.12
- .NET 9 SDK
- A legitimate installation of Slay the Spire 2 for live gameplay
- The game's required mod dependencies, including BaseLib
- Godot/MegaDot 4.5.1 tooling if exporting a PCK is required

The headless training workflow does not require launching the graphical game.

## Installation

Clone the repository:

```powershell
git clone https://github.com/ZipsyPD/RegentRL.git
cd RegentRL
```

Create an isolated Python environment:

```powershell
py -3.12 -m venv .venv-training
```

Install the bundled simulator and training dependencies:

```powershell
.\.venv-training\Scripts\python.exe -m pip install -e ".\simulator[train]"
```

Verify the package:

```powershell
.\.venv-training\Scripts\python.exe -c "import sts2_env; print(sts2_env.__file__)"
```

**Note:** These instructions assume that the simulator is included in the distributed repository. If it is not included, it must be obtained separately from an authorized source.

## Training an Agent

Run a small PPO smoke test:

```powershell
.\.venv-training\Scripts\python.exe training\train_regentrl_fullrun_ppo_v4.py `
  --timesteps 1024 `
  --rollout-steps 256 `
  --epochs 2 `
  --output training\output\smoke_test.pt
```

For a longer experiment:

```powershell
.\.venv-training\Scripts\python.exe training\train_regentrl_fullrun_ppo_v4.py `
  --timesteps 1000000 `
  --output training\output\regentrl_1m.pt
```

Checkpoints are saved under `training/output/`.

Training can be resumed using `--resume` with a compatible `.resume.pt` checkpoint. Actor-only `.pt` checkpoints are used for inference.

## Building and Installing the Game Mod

The C# mod is defined by `RegentRL.csproj` at the repository root.

Install Slay the Spire 2 through Steam, together with the required modding dependencies.

Check your .NET installation:

```powershell
dotnet --version
```

The project targets .NET 9.

Build the mod from the repository root:

```powershell
dotnet build RegentRL.csproj
```

The project contains an MSBuild target that copies the compiled mod DLL and manifest into the detected Slay the Spire 2 mods directory.

If your Steam installation is not detected automatically, specify the game directory:

```powershell
dotnet build RegentRL.csproj -p:Sts2Path="C:\Path\To\Slay the Spire 2"
```

For PCK export, configure the local `GodotPath` in `Directory.Build.props` and use:

```powershell
dotnet publish RegentRL.csproj
```

The exact mod loader, BaseLib installation, and PCK requirements must match the installed game version. Check the game's mod-loading screen before starting inference.

## Running the Agent in the Real Game

Start the Python inference server with a trained checkpoint:

```powershell
.\.venv-training\Scripts\python.exe python\agent_server.py `
  --policy fullrunppo `
  --checkpoint training\output\regentrl_1m.pt
```

The default TCP port is `5050`.

Then launch the modded game with RegentRL enabled.

The C# mod sends observations and legal actions to the Python server. The policy selects an action, and the mod executes the result.

For testing, the short-run `smoke_test.pt` checkpoint can also be loaded, but it is not expected to perform well.

## Counterfactual Card-Reward Experiments

RegentRL includes an experiment that compares alternative card-reward decisions by continuing simulated runs from comparable states.

Example:

```powershell
.\.venv-training\Scripts\python.exe training\experiment_card_branches.py `
  --checkpoint training\output\regentrl_1m.pt `
  --states 5 `
  --horizon 250 `
  --max-collect-episodes 30 `
  --output training\output\card_branches.jsonl
```

This is a simulator-based evaluation, separate from the live inference server.

## Experimental Results

In a previous one-million-step PPO training experiment, the mean floor reached improved from 5.76 at the 50K-step checkpoint to 8.84 at approximately 850K steps, evaluated over 50 episodes using the same evaluation seeds.

A separate card-reward experiment collected 2,000 reward-decision states and 4,014 card-versus-Skip comparisons.

These results reflect progression and experimental comparisons, not successful full-run completion.

## Limitations

- The headless simulator approximates the real game's mechanics and may differ from live gameplay.
- Checkpoint compatibility depends on policy architecture and observation encoding.
- The live mod depends on game and modding API versions.
- The short smoke-test checkpoint is intended to validate integration, not agent quality.
- Training performance is not guaranteed to improve monotonically.

## Attribution

RegentRL's integrated headless simulator is derived from [zhiyue/sts2-rl-agent](https://github.com/zhiyue/sts2-rl-agent).

The RegentRL C# integration, training experiments, and policy-serving implementation are documented separately from the upstream simulator. Redistribution of third-party code and reference data remains subject to their applicable rights and permissions.

This is an independent research project and is not affiliated with Mega Crit.
