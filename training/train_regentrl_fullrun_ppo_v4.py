"""Batched, on-policy full-run RegentRL PPO (experimental v4 trainer).

Preserves the v3 shared 256-feature encoder and actor checkpoint architecture.
Rollout collection spans episodes; GAE and PPO updates happen once per rollout.
No modifications to RegentRL's observation or wire protocol.
"""
from __future__ import annotations
import argparse
import json
import os
import random
from collections import deque
from pathlib import Path

import numpy as np
import torch
from torch import nn
from sts2_env.gym_env.run_env import STS2RunEnv
from sts2_env.regentrl.bridge import fullrun_request
from sts2_env.regentrl.fullrun_encoder import encode, FEATURE_VERSION, FEATURES


def make_actor():
    return nn.Sequential(nn.Linear(FEATURES, 128), nn.Tanh(), nn.Linear(128, 64), nn.Tanh(), nn.Linear(64, 1))


def make_critic():
    return nn.Sequential(nn.Linear(FEATURES, 128), nn.Tanh(), nn.Linear(128, 1))


def features_for(env, decision_id):
    req, ids = fullrun_request(env, decision_id=decision_id)
    if not ids:
        raise RuntimeError('No mappable legal actions in simulator state')
    features = torch.tensor([encode(req, action) for action in req['LegalActions']], dtype=torch.float32)
    return features, ids, req


def compute_gae(rewards, values, next_values, dones, gamma, gae_lambda):
    """GAE with explicit next-state values, zeroing on episode termination."""
    advantages = [0.0] * len(rewards)
    gae = 0.0
    for t in reversed(range(len(rewards))):
        keep = 0.0 if dones[t] else 1.0
        delta = rewards[t] + gamma * next_values[t] * keep - values[t]
        gae = delta + gamma * gae_lambda * keep * gae
        advantages[t] = gae
    return torch.tensor(advantages, dtype=torch.float32)


def train(args):
    if args.timesteps <= 0 or args.rollout_steps <= 0:
        raise ValueError('timesteps and rollout-steps must be positive')
    if args.torch_threads <= 0:
        raise ValueError('torch-threads must be positive')
    # CPU training repeatedly scores small variable-sized action sets. Avoid
    # excessive intra-op threading overhead on large-core desktops.
    torch.set_num_threads(args.torch_threads)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    actor, critic = make_actor(), make_critic()
    opt = torch.optim.Adam([*actor.parameters(), *critic.parameters()], lr=args.lr, eps=1e-5)
    env = STS2RunEnv(character_id='Regent', max_steps=args.max_steps)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    metric_file = out.with_suffix('.metrics.jsonl')
    if not args.resume:
        metric_file.write_text('', encoding='utf8')
    choice_file = out.with_suffix('.card_choices.jsonl')
    if not args.resume:
        choice_file.write_text('', encoding='utf8')
    steps = episodes = updates = 0
    phase_counts = {}
    recent = deque(maxlen=100)
    done = True
    current_floor = 0
    episode_reward = 0.0
    episode_steps = 0
    latest_stats = {}
    resume_path = out.with_suffix('.resume.pt')
    last_snapshot_step = 0
    last_milestone_step = 0

    def atomic_save(blob, path):
        """Write complete PyTorch checkpoints before replacing existing files."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        torch.save(blob, tmp)
        os.replace(tmp, path)

    def save(path):
        # The actor state_dict keys and FEATURE_VERSION remain compatible with
        # RegentRL --policy fullrunppo (and existing fullrun_eval.py).
        atomic_save({'feature_version': FEATURE_VERSION, 'state_dict': actor.state_dict(),
                    'algorithm': 'fullrun_action_scoring_ppo_v4_gae',
                    'training_steps': steps, 'episodes': episodes,
                    'phase_counts': dict(phase_counts)}, path)

    def save_resume():
        # The resume checkpoint is for TRAINING only; --policy fullrunppo
        # accepts the separate actor-only .pt milestones.
        atomic_save({'feature_version': FEATURE_VERSION,
                    'feature_size': FEATURES,
                    'actor_state_dict': actor.state_dict(),
                    'critic_state_dict': critic.state_dict(),
                    'optimizer_state_dict': opt.state_dict(),
                    'training_steps': steps, 'episodes': episodes,
                    'updates': updates, 'phase_counts': dict(phase_counts),
                    'recent': list(recent), 'latest_stats': latest_stats,
                    'torch_rng_state': torch.get_rng_state(),
                    'python_rng_state': random.getstate(),
                    'shuffle_rng_state': rng.getstate(),
                    'config': {k: getattr(args,k) for k in
                               ('seed','max_steps','lr','gamma','gae_lambda',
                                'clip','value_coef','entropy_coef','floor_reward',
                                'hp_reward','step_penalty')}
                    }, resume_path)

    if args.resume:
        state = torch.load(args.resume, map_location='cpu', weights_only=True)
        if state.get('feature_version') != FEATURE_VERSION or state.get('feature_size') != FEATURES:
            raise ValueError('Resume checkpoint incompatible with the current feature encoder')
        for key,value in state.get('config',{}).items():
            if getattr(args,key) != value:
                raise ValueError(f'Resume config mismatch for {key}: saved {value}, requested {getattr(args,key)}')
        actor.load_state_dict(state['actor_state_dict'])
        critic.load_state_dict(state['critic_state_dict'])
        opt.load_state_dict(state['optimizer_state_dict'])
        steps = int(state['training_steps'])
        episodes = int(state['episodes'])
        updates = int(state['updates'])
        phase_counts = dict(state['phase_counts'])
        recent.extend(state.get('recent',[]))
        latest_stats = dict(state.get('latest_stats',{}))
        torch.set_rng_state(state['torch_rng_state'])
        random.setstate(state['python_rng_state'])
        rng.setstate(state['shuffle_rng_state'])
        last_snapshot_step = steps
        last_milestone_step = steps
        print(f'Resumed PPO actor/critic/optimizer at steps={steps} episodes={episodes}; '
              'in-progress simulator episode restarted.', flush=True)


    def start_episode():
        nonlocal done, current_floor, episode_reward, episode_steps
        _, info = env.reset(seed=args.seed + episodes)
        current_floor = int(info.get('floor', 0))
        episode_reward = 0.0
        episode_steps = 0
        done = False

    start_episode()
    while steps < args.timesteps:
        rollout = []
        for _ in range(min(args.rollout_steps, args.timesteps - steps)):
            if done:
                start_episode()
            fs, ids, req = features_for(env, steps)
            phase = req['Type']
            with torch.no_grad():
                dist = torch.distributions.Categorical(logits=actor(fs).view(-1))
                selected = dist.sample()
                old_lp = float(dist.log_prob(selected))
                value = float(critic(fs.mean(dim=0)).view(()))
            choice = ids[selected.item()]
            if phase in ('CardRewardDecision','CardSelection','ShopDecision','EventDecision','BundleDecision','RestSiteDecision'):
                # Pre-decision context only; do not leak future outcome into features.
                entry={'episode':episodes+1,'step':steps,'phase':phase,
                       'decision':req.get('LegalActions',[{}])[selected.item()],
                       'offered':req.get('LegalActions',[]),
                       'purpose':req.get('Purpose'), 'source':req.get('Source'),
                       'selected_before':req.get('SelectedIndices',[]),
                       'deck':req.get('RunObservation',{}).get('Deck',[])}
                with choice_file.open('a',encoding='utf8') as fh:
                    fh.write(json.dumps(entry,default=str)+'\n')
            if not bool(env.action_masks()[choice]):
                raise RuntimeError(f'Bridge produced illegal simulator action {choice}')
            old_hp = env._mgr.run_state.player.current_hp
            old_floor = current_floor
            _, raw_reward, terminated, truncated, info = env.step(choice)
            current_floor = max(current_floor, int(info.get('floor', 0)))
            hp = env._mgr.run_state.player.current_hp
            done = bool(terminated or truncated)
            # Progress shaping gives learnable feedback before a rare full-run win.
            # This is a surrogate objective, not proof the policy will win.
            shaped = (float(raw_reward)
                      + args.floor_reward * max(0, current_floor - old_floor)
                      + args.hp_reward * (hp - old_hp)
                      - args.step_penalty)
            episode_reward += float(raw_reward)
            episode_steps += 1
            steps += 1
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            with torch.no_grad():
                if done:
                    next_value = 0.0
                else:
                    next_fs, _, _ = features_for(env, steps)
                    next_value = float(critic(next_fs.mean(dim=0)).view(()))
            rollout.append((fs, selected.item(), old_lp, value, shaped, done, next_value))
            if done:
                episodes += 1
                result = {'episode': episodes,
                          'win': bool(terminated and env._mgr.player_won),
                          'truncated': bool(truncated),
                          'floor': current_floor,
                          'reward': episode_reward,
                          'steps': episode_steps,
                          'hp': int(info.get('hp', hp))}
                recent.append(result)
                with metric_file.open('a', encoding='utf8') as f:
                    f.write(json.dumps(result) + '\n')
                if args.log_every and episodes % args.log_every == 0:
                    print(f'episodes={episodes} steps={steps} updates={updates} '
                          f'last_{len(recent)}_wins={sum(r["win"] for r in recent)} '
                          f'mean_floor={sum(r["floor"] for r in recent)/len(recent):.2f} '
                          f'phase_counts={phase_counts} ppo={latest_stats}', flush=True)
                # Do not save here: the corresponding rollout has not yet been
                # optimized. Actor snapshots are written after PPO updates.

        rewards = [r[4] for r in rollout]
        values = [r[3] for r in rollout]
        adv = compute_gae(rewards, values, [r[6] for r in rollout],
                          [r[5] for r in rollout], args.gamma, args.gae_lambda)
        ret = adv + torch.tensor(values)
        adv = (adv - adv.mean()) / (adv.std(unbiased=False) + 1e-8)
        indices = list(range(len(rollout)))
        policy_losses = []; value_losses = []; kls = []; entropies = []; clips = []
        early_stop = False
        for _ in range(args.epochs):
            rng.shuffle(indices)
            for start in range(0, len(indices), args.batch_size):
                batch = indices[start:start + args.batch_size]
                pol_terms = []; val_terms = []; entropy_terms = []
                for i in batch:
                    fs, choice, old_lp, *_ = rollout[i]
                    dist = torch.distributions.Categorical(logits=actor(fs).view(-1))
                    logp = dist.log_prob(torch.tensor(choice))
                    logratio = logp - old_lp
                    ratio = logratio.exp()
                    pol_terms.append(-torch.minimum(ratio * adv[i],
                                     ratio.clamp(1 - args.clip, 1 + args.clip) * adv[i]))
                    val_terms.append((critic(fs.mean(dim=0)).view(()) - ret[i]).square())
                    entropy_terms.append(dist.entropy())
                    kls.append(float(((ratio - 1) - logratio).detach()))
                    clips.append(float(((ratio - 1).abs() > args.clip).detach()))
                pol_loss = torch.stack(pol_terms).mean()
                value_loss = torch.stack(val_terms).mean()
                entropy = torch.stack(entropy_terms).mean()
                loss = pol_loss + args.value_coef * value_loss - args.entropy_coef * entropy
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_([*actor.parameters(), *critic.parameters()], args.max_grad_norm)
                opt.step()
                updates += 1
                policy_losses.append(float(pol_loss.detach()))
                value_losses.append(float(value_loss.detach()))
                entropies.append(float(entropy.detach()))
                if args.target_kl > 0 and np.mean(kls[-len(batch):]) > args.target_kl:
                    early_stop = True
                    break
            if early_stop:
                break
        latest_stats = {'policy_loss': round(float(np.mean(policy_losses)), 4),
                        'value_loss': round(float(np.mean(value_losses)), 4),
                        'entropy': round(float(np.mean(entropies)), 4),
                        'approx_kl': round(float(np.mean(kls)), 5),
                        'clip_fraction': round(float(np.mean(clips)), 4)}
        if args.save_every_steps and steps - last_snapshot_step >= args.save_every_steps:
            save_resume()
            last_snapshot_step = steps
        if args.milestone_steps and steps // args.milestone_steps > last_milestone_step // args.milestone_steps:
            milestone = out.with_name(f'{out.stem}_step{steps:07d}{out.suffix}')
            save(milestone)
            print(f'Saved inference milestone: {milestone}', flush=True)
            last_milestone_step = steps
        if args.log_rollout:
            print(f'rollout steps={steps} episodes={episodes} updates={updates} ppo={latest_stats}', flush=True)
    save(out)
    save_resume()
    print(f'Full-run PPO v4 checkpoint: {out} steps={steps} episodes={episodes} '
          f'updates={updates} phases={phase_counts}', flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--timesteps', type=int, default=100000)
    p.add_argument('--torch-threads', type=int, default=1)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--max-steps', type=int, default=2000)
    p.add_argument('--output', default='output/regentrl_fullrun_v4_100k.pt')
    p.add_argument('--rollout-steps', type=int, default=1024)
    p.add_argument('--epochs', type=int, default=4)
    p.add_argument('--batch-size', type=int, default=128)
    p.add_argument('--lr', type=float, default=3e-4)
    p.add_argument('--gamma', type=float, default=.99)
    p.add_argument('--gae-lambda', type=float, default=.95)
    p.add_argument('--clip', type=float, default=.2)
    p.add_argument('--value-coef', type=float, default=.5)
    p.add_argument('--entropy-coef', type=float, default=.01)
    p.add_argument('--target-kl', type=float, default=.03)
    p.add_argument('--max-grad-norm', type=float, default=.5)
    p.add_argument('--floor-reward', type=float, default=.08)
    p.add_argument('--hp-reward', type=float, default=.005)
    p.add_argument('--step-penalty', type=float, default=.0001)
    p.add_argument('--log-every', type=int, default=25)
    p.add_argument('--save-every', type=int, default=0,
                   help='Legacy episodes-based option; use --milestone-steps instead')
    p.add_argument('--save-every-steps', type=int, default=10000,
                   help='Atomically overwrite the full PPO resume state every N optimized steps')
    p.add_argument('--milestone-steps', type=int, default=50000,
                   help='Save a playable actor-only checkpoint every N optimized steps')
    p.add_argument('--resume', default=None,
                   help='Resume actor, critic and optimizer from a .resume.pt checkpoint')
    p.add_argument('--log-rollout', action='store_true')
    train(p.parse_args())

if __name__ == '__main__':
    main()
