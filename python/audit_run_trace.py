"""Audit RegentRL JSONL traces without treating observations as execution proof.
Usage: python python/audit_run_trace.py [path-to-run.jsonl]
If omitted, selects the most recently modified run trace.
"""
import argparse
import collections
import json
from pathlib import Path


def audit(path):
    records = []
    with path.open(encoding='utf-8') as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f'Invalid JSON line {line_number}: {exc}') from exc

    decisions = {}
    resolved = set()
    followups = set()
    endings = []
    starts = []
    errors = []
    run_ids = set()
    for r in records:
        kind = r.get('RecordType')
        rid = r.get('RunId')
        if rid:
            run_ids.add(rid)
        if kind == 'RunStarted':
            starts.append(r)
        elif kind == 'RunEnded':
            endings.append(r)
        elif kind == 'Decision':
            key = (rid, r.get('Sequence'))
            if key in decisions:
                errors.append(f'duplicate Decision sequence {key}')
            decisions[key] = r
        elif kind == 'ActionResolved':
            key = (rid, r.get('Sequence'))
            if key in resolved:
                errors.append(f'duplicate ActionResolved {key}')
            resolved.add(key)
            if r.get('Executed') is not True or r.get('NextObservation') is None:
                errors.append(f'invalid ActionResolved {key}')
            orig = decisions.get(key)
            if orig is not None and (orig.get('DecisionId') != r.get('DecisionId') or orig.get('DecisionType') != r.get('DecisionType')):
                errors.append(f'ActionResolved mismatch {key}')
        elif kind == 'ObservationFollowup':
            followups.add((rid, r.get('Sequence')))
            if r.get('ExecutionVerified') is not False:
                errors.append('observation follow-up marked verified')
    for key in resolved:
        if key not in decisions:
            errors.append(f'orphan ActionResolved {key}')
    for key in followups:
        if key not in decisions:
            errors.append(f'orphan ObservationFollowup {key}')
    if len(run_ids) > 1:
        errors.append(f'mixed RunIds: {sorted(run_ids)}')
    by_type = collections.defaultdict(lambda: [0, 0, 0])
    for key, d in decisions.items():
        counts = by_type[d.get('DecisionType', 'Unknown')]
        counts[0] += 1
        counts[1] += key in resolved
        counts[2] += key in followups

    print(f'FILE: {path}')
    print(f'RUN ID(S): {", ".join(sorted(run_ids)) or "none"}')
    print(f'NATIVE STARTS: {len(starts)} | NATIVE ENDS: {len(endings)}')
    for e in endings:
        print(f'OUTCOME: {e.get("Outcome")} (native verified: {e.get("OutcomeVerified")})')
    print('\nDECISION TYPE             TOTAL  RESOLVED  FOLLOW-UP  UNRESOLVED')
    for name, (total, nresolved, nfollowup) in sorted(by_type.items()):
        print(f'{name:25} {total:5} {nresolved:9} {nfollowup:10} {total - nresolved:11}')
    print('\nNote: FOLLOW-UP is observational evidence and may overlap with RESOLVED.')
    print('No native outcome or acknowledgment is ever inferred from a later request.')
    print('AUDIT:', 'PASS (structural checks)' if not errors else 'WARN')
    for error in errors:
        print(' -', error)
    return 0 if not errors else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', type=Path)
    args = parser.parse_args()
    path = args.path
    if path is None:
        trace_dir = Path(__file__).resolve().parent / 'run_traces'
        files = list(trace_dir.glob('run_*.jsonl'))
        if not files:
            parser.error(f'No traces in {trace_dir}')
        path = max(files, key=lambda p: p.stat().st_mtime)
    raise SystemExit(audit(path))


if __name__ == '__main__':
    main()
