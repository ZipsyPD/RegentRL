"""Human demonstrations via the RegentRL *terminal*, not passive GUI capture.

Only the person at stdin chooses actions. The C# mod executes the choices;
existing native execution acknowledgments determine which become training data.
"""
from __future__ import annotations

import json


def _describe_action(action):
    if isinstance(action, dict):
        return ', '.join(f'{k}={v}' for k, v in action.items() if v is not None and v != '')
    return str(action)


def choose_human(request, input_fn=input, output_fn=print):
    kind = request.get('Type') or 'CombatDecision'
    decision = request['DecisionId']
    output_fn(f'\n=== HUMAN DEMONSTRATION | {kind} | #{decision} ===')
    if kind == 'CardSelection':
        options = request['Options']
        details = request.get('OptionDetails') or []
        lo = int(request['MinSelect'])
        hi = min(int(request['MaxSelect']), len(options))
        if lo > hi or lo < 0:
            raise ValueError('Invalid card-selection bounds')
        for i, option in enumerate(options):
            detail = details[i] if i < len(details) else option
            output_fn(f'  [{i}] {_describe_action(detail)}')
        output_fn(f'Select {lo}–{hi} distinct indices separated by commas (empty = none if permitted).')
        while True:
            raw = input_fn('Your card selection> ').strip()
            try:
                indices = [int(s.strip()) for s in raw.split(',')] if raw else []
            except ValueError:
                output_fn('Enter integers separated by commas.')
                continue
            if lo <= len(indices) <= hi and len(set(indices)) == len(indices) and all(0 <= i < len(options) for i in indices):
                return {'DecisionId': decision, 'SelectedIndices': indices}
            output_fn('Invalid selection or selection count. Try again.')

    actions = request.get('LegalActions')
    if not isinstance(actions, list) or not actions:
        raise ValueError(f'{kind}: no legal actions received')
    for i, action in enumerate(actions):
        output_fn(f'  [{i}] {_describe_action(action)}')
    while True:
        raw = input_fn(f'Choose action [0–{len(actions)-1}]> ').strip()
        try:
            idx = int(raw)
        except ValueError:
            output_fn('Enter a numbered choice.')
            continue
        if 0 <= idx < len(actions):
            return {'DecisionId': decision, 'ActionIndex': idx}
        output_fn('Out of range. Try again.')
