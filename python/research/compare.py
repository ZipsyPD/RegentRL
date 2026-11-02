"""Baseline action agreement on recorded verified states — NOT win rate."""
import argparse
from collections import defaultdict
from pathlib import Path
from .core import FirstLegalAgent, RandomAgent, load_verified

def compare(path: Path, seed: int = 0) -> None:
    agents = {'first_legal': FirstLegalAgent(), 'random': RandomAgent(seed)}
    stats = defaultdict(lambda: [0, 0])
    total = 0
    for decision in load_verified(path):
        if decision.chosen_index is None or not decision.legal_actions:
            continue
        total += 1
        for name, agent in agents.items():
            picked = agent.act(decision.observation, decision.legal_actions)
            entry = stats[(decision.phase, name)]
            entry[0] += (picked == decision.chosen_index)
            entry[1] += 1
    print(f'Dataset: {path}\nComparable verified decisions: {total}')
    print('WARNING: Action agreement with recorded policy is NOT policy quality or RL training.')
    for (phase, name), (matches, n) in sorted(stats.items()):
        print(f'  {phase:22s} {name:12s} {matches:4d}/{n:<4d} ({100*matches/n:.1f}%)')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', nargs='?', type=Path)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    path = args.file
    if path is None:
        files = list((Path(__file__).parents[1] / 'trajectories').glob('*_verified.jsonl'))
        if not files:
            parser.error('No verified trajectories. Run export_trajectories.py first.')
        path = max(files, key=lambda p: p.stat().st_mtime)
    compare(path, args.seed)

if __name__ == '__main__':
    main()
