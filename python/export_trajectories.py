"""Export strictly native-resolved RegentRL decision transitions to JSONL.

Never infer execution from later decisions or observational follow-ups.
Run Win/Loss/Abandoned are separate from combat terminal outcomes.
Usage: python python/export_trajectories.py [trace.jsonl] [--out file.jsonl]
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def read_jsonl(path):
    with path.open(encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f'{path}:{lineno}: {exc}') from exc


def export_trace(path, out):
    decisions, resolved = {}, {}
    starts, ends, errors = [], [], []
    run_ids = set()
    for rec in read_jsonl(path):
        kind, rid = rec.get('RecordType'), rec.get('RunId')
        if rid: run_ids.add(rid)
        if kind == 'Decision':
            key = (rid, rec.get('Sequence'))
            if key in decisions: errors.append(f'duplicate decision {key}')
            decisions[key] = rec
        elif kind == 'ActionResolved':
            key = (rid, rec.get('Sequence'))
            if key in resolved: errors.append(f'duplicate resolution {key}')
            resolved[key] = rec
        elif kind == 'RunStarted': starts.append(rec)
        elif kind == 'RunEnded': ends.append(rec)
    if len(run_ids) != 1: errors.append(f'expected one run ID; got {run_ids}')
    if len(starts) != 1: errors.append(f'expected one native start; got {len(starts)}')
    if len(ends) > 1: errors.append(f'multiple native ends ({len(ends)})')
    if errors: raise ValueError('; '.join(errors))
    outcome = ends[0].get('Outcome') if ends and ends[0].get('OutcomeVerified') is True else None
    if outcome not in (None, 'Win', 'Loss', 'Abandoned'):
        raise ValueError(f'bad verified run outcome: {outcome}')
    counts = Counter()
    output = []
    for key, decision in sorted(decisions.items(), key=lambda kv: kv[0][1]):
        ack = resolved.get(key)
        if ack is None:
            counts['unverified'] += 1
            continue
        if (ack.get('Executed') is not True or ack.get('NextObservation') is None or
            ack.get('DecisionId') != decision.get('DecisionId') or
            ack.get('DecisionType') != decision.get('DecisionType')):
            raise ValueError(f'invalid acknowledgment: {key}')
        req = decision.get('Request') or {}
        action = decision.get('ChosenAction')
        output.append({
            'SchemaVersion': 1,
            'RunId': decision['RunId'],
            'Sequence': decision['Sequence'],
            'DecisionType': decision['DecisionType'],
            'DecisionId': decision['DecisionId'],
            'Observation': {'RunObservation': req.get('RunObservation'),
                            'CombatObservation': req.get('Observation')},
            'FullRequest': req,  # preserve phase-specific features without guessing keys
            'LegalActions': req.get('LegalActions'),
            'ChosenAction': action,
            'PolicyResponse': decision.get('Response'),
            'NextObservation': ack['NextObservation'],
            'CombatTerminal': bool(ack.get('Terminal', False)),
            'CombatOutcome': ack.get('CombatOutcome'),
            'Executed': True,
            'RunOutcome': outcome,
            'Reward': None,  # intentionally missing until reward design
            'Done': bool(ack.get('Terminal', False)),  # combat boundary only; not run termination!
            'DoneScope': 'Combat' if ack.get('Terminal') else None,
        })
        counts['verified'] += 1
        counts[f'verified_{decision["DecisionType"]}'] += 1
    # Do not label RunOutcome as a per-action terminal reward.
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8', newline='\n') as f:
        for r in output:
            f.write(json.dumps(r, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'Input: {path}\nOutput: {out}\nVerified transitions: {counts["verified"]}')
    print(f'Excluded unverified decisions: {counts["unverified"]}')
    print(f'Native verified run outcome: {outcome or "not available"}')
    for kind, count in sorted(counts.items()):
        if kind.startswith('verified_'): print(f'  {kind[9:]}: {count}')
    print('Reward remains null. Combat Done does NOT mean run Done.')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', nargs='?', type=Path)
    parser.add_argument('--out', type=Path)
    a = parser.parse_args()
    if a.trace is None:
        traces = list((Path(__file__).parent / 'run_traces').glob('run_*.jsonl'))
        if not traces: parser.error('No run traces found')
        a.trace = max(traces, key=lambda p: p.stat().st_mtime)
    out = a.out or Path(__file__).parent / 'trajectories' / f'{a.trace.stem}_verified.jsonl'
    export_trace(a.trace, out)


if __name__ == '__main__': main()
