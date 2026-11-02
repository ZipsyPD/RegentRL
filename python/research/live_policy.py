"""Legal-action-safe live policy adapters for RegentRL protocol v2.

No learning is performed here. Toy showcase models are intentionally excluded.
"""
from __future__ import annotations
import random

POLICIES = ('legacy', 'first', 'random', 'hierarchical')


def choose(request: dict, policy: str, rng: random.Random) -> dict | None:
    """Return protocol response; None means preserve server's legacy policy.

    CardSelection has a multi-select response and is handled separately.
    """
    if policy == 'legacy':
        return None
    kind = request.get('Type')
    decision = request.get('DecisionId')
    if kind == 'CardSelection':
        count = min(int(request['MaxSelect']), len(request['Options']))
        minimum = int(request['MinSelect'])
        if count < minimum:
            raise ValueError('CardSelection has insufficient options')
        if policy == 'random':
            chosen = sorted(rng.sample(range(len(request['Options'])), count))
        else:
            chosen = list(range(count))
        return {'DecisionId': decision, 'SelectedIndices': chosen}

    actions = request.get('LegalActions')
    if not isinstance(actions, list) or not actions:
        raise ValueError(f'{kind}: no legal actions')
    index = 0
    if policy == 'random':
        index = rng.randrange(len(actions))
    elif policy == 'hierarchical' and kind == 'CombatDecision':
        # A hand-coded tactical specialist, NOT learned hierarchical RL.
        index = next((i for i,a in enumerate(actions)
                      if a.get('Type') == 'PlayCard' and a.get('TargetId') is not None), 0)
    # first and strategy specialist choose index 0.
    return {'DecisionId': decision, 'ActionIndex': index}
