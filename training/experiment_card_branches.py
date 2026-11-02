"""Offline card-reward counterfactual experiment; does not modify or train PPO.

Collect real Regent simulator reward states. For each offered card and Skip,
clone the same state, apply the choice, then finish with the same frozen PPO
policy. Paired branches share their pre-choice RNG state. This is a diagnostic
rather than an unbiased value estimate: different decks consume RNG differently.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sts2_env.gym_env.run_env import STS2RunEnv
from sts2_env.regentrl.bridge import fullrun_request
from sts2_env.regentrl.fullrun_encoder import encode, FEATURES, FEATURE_VERSION


def load_actor(checkpoint):
    blob = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if blob.get('feature_version') != FEATURE_VERSION:
        raise ValueError(f"Expected encoder version {FEATURE_VERSION}, got {blob.get('feature_version')}")
    actor = nn.Sequential(nn.Linear(FEATURES, 128), nn.Tanh(), nn.Linear(128, 64), nn.Tanh(), nn.Linear(64, 1))
    actor.load_state_dict(blob['state_dict'])
    actor.eval()
    return actor


@torch.inference_mode()
def choose(actor, env):
    request, ids = fullrun_request(env, decision_id=env._step_count)
    features = torch.tensor([encode(request, action) for action in request['LegalActions']], dtype=torch.float32)
    index = int(actor(features).flatten().argmax())
    return ids[index], request['LegalActions'][index]


@torch.inference_mode()
def play_forward(env, actor, max_actions):
    initial_floor = env._mgr.run_state.total_floor
    initial_hp = env._mgr.run_state.player.current_hp
    done = False
    steps = 0
    while steps < max_actions and not done:
        action, _ = choose(actor, env)
        _, _, terminal, truncated, _ = env.step(action)
        done = terminal or truncated
        steps += 1
    rs = env._mgr.run_state
    won = bool(env._mgr.player_won)
    # Progress is primary; HP is a tie-breaker, not a reward-label claim.
    score = (rs.total_floor - initial_floor) + 0.01 * (rs.player.current_hp - initial_hp) + (50 if won else 0)
    return {'score': round(score, 4), 'floor': rs.total_floor, 'hp': rs.player.current_hp,
            'won': won, 'steps': steps, 'ended': done}


def decision_context(env):
    """JSON-safe snapshot of the observable drafting context."""
    rs = env._mgr.run_state
    player = rs.player
    deck = []
    for card in player.deck:
        cid = getattr(card, 'card_id', getattr(card, 'id', None))
        cid = getattr(cid, 'name', str(cid))
        deck.append({'card_id': cid,
                     'upgraded': bool(getattr(card, 'upgraded', False)),
                     'upgrade_level': int(getattr(card, 'upgrade_level', 0) or 0),
                     'cost': str(getattr(card, 'cost', ''))})
    return {'floor': int(rs.total_floor), 'act': str(getattr(rs, 'current_act', '')),
            'hp': int(player.current_hp), 'max_hp': int(player.max_hp),
            'gold': int(player.gold), 'deck': deck,
            'relics': [str(r) for r in player.relics],
            'potions': [None if p is None else str(getattr(p, 'potion_id', p)) for p in player.potions]}


def candidate_indices(env):
    req, ids = fullrun_request(env, decision_id=env._step_count)
    if req['Type'] != 'CardRewardDecision':
        return []
    return [(idx, action) for idx, action in zip(ids, req['LegalActions'])
            if action.get('Type') in ('SelectReward', 'SkipReward')]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', required=True)
    p.add_argument('--states', type=int, default=5, help='Number of card reward screens to compare')
    p.add_argument('--seed', type=int, default=800000)
    p.add_argument('--min-floor', type=int, default=1, help='Only collect rewards at this floor or later')
    p.add_argument('--max-floor', type=int, default=999, help='Only collect rewards up to this floor')
    p.add_argument('--max-collect-episodes', type=int, default=30)
    p.add_argument('--horizon', type=int, default=250, help='Future decisions per branch')
    p.add_argument('--max-steps', type=int, default=2000)
    p.add_argument('--output', default='output/card_branch_experiment.jsonl')
    args = p.parse_args()
    if args.min_floor < 1 or args.max_floor < args.min_floor:
        p.error('Invalid floor range')
    if args.states < 1 or args.horizon < 1 or args.max_collect_episodes < 1:
        p.error('states, horizon and max-collect-episodes must be positive')
    torch.set_num_threads(1)
    actor = load_actor(args.checkpoint)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    comparisons = 0
    with output.open('w', encoding='utf-8') as out:
        for episode in range(args.max_collect_episodes):
            if comparisons >= args.states:
                break
            env = STS2RunEnv(character_id='Regent', max_steps=args.max_steps, raise_on_simulator_error=True)
            env.reset(seed=args.seed + episode)
            for step in range(args.max_steps):
                candidates = candidate_indices(env)
                current_floor = int(env._mgr.run_state.total_floor)
                if len(candidates) >= 2 and args.min_floor <= current_floor <= args.max_floor:
                    # Preserve the exact action-conditioned encoder input used by this PPO.
                    # Unlike global card averages, these vectors contain decision context.
                    req, full_ids = fullrun_request(env, decision_id=env._step_count)
                    features_by_id = {int(idx): list(encode(req, desc)) for idx, desc in zip(full_ids, req['LegalActions'])}
                    context = decision_context(env)
                    results = []
                    for simulator_action, description in candidates:
                        branch = copy.deepcopy(env)
                        branch.step(simulator_action)
                        outcome = play_forward(branch, actor, args.horizon)
                        results.append({'action': description, 'simulator_action_id': int(simulator_action), **outcome})
                    results.sort(key=lambda x: x['score'], reverse=True)
                    skip = next((r for r in results if r['action'].get('Type') == 'SkipReward'), None)
                    for result in results:
                        result['encoded_features'] = features_by_id[result['simulator_action_id']]
                        result['censored'] = not result['ended']
                        result['ending_floor_observed'] = result['floor']
                        result['terminal_floor'] = result['floor'] if result['ended'] else None
                        result['floor_observation_kind'] = 'terminal' if result['ended'] else 'horizon_censored'
                        result['additional_floors'] = result['floor'] - current_floor
                        # Paired observed progress, NOT an estimate of eventual survival
                        # when either continuation was truncated.
                        result['delta_observed_floor_vs_skip'] = (result['floor'] - skip['floor']) if skip else None
                        result['delta_terminal_floor_vs_skip'] = (
                            result['floor'] - skip['floor'] if skip and result['ended'] and skip['ended'] else None)
                        result['delta_floor_vs_skip'] = result['delta_terminal_floor_vs_skip']
                    record = {'schema_version': 3, 'context': context, 'teacher_checkpoint': str(args.checkpoint),
                              'encoder_version': FEATURE_VERSION,
                              'episode_seed': args.seed + episode, 'floor': current_floor,
                              'candidate_count': len(results), 'results': results}
                    out.write(json.dumps(record, default=str) + '\n')
                    out.flush()
                    comparisons += 1
                    print(f"[{comparisons}/{args.states}] seed={record['episode_seed']} floor={record['floor']}")
                    for item in results:
                        print(f"  score={item['score']:+.2f} floor={item['floor']} HP={item['hp']} {item['action']}")
                    if comparisons >= args.states:
                        break
                action, _ = choose(actor, env)
                _, _, terminal, truncated, _ = env.step(action)
                if terminal or truncated:
                    break
    print(f'Wrote {comparisons} paired decision screens to {output}')
    if not comparisons:
        raise SystemExit('No card-reward decisions were reached; try more collection episodes')


if __name__ == '__main__':
    main()
