"""Algorithm-neutral agent and verified-trajectory ingestion."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import json
import random
from typing import Any, Iterator

@dataclass(frozen=True)
class Decision:
    run_id: str
    sequence: int
    phase: str
    observation: dict[str, Any]
    legal_actions: list[dict[str, Any]]
    chosen_index: int | None
    run_outcome: str | None

class Agent(ABC):
    @abstractmethod
    def act(self, observation: dict[str, Any], legal_actions: list[dict[str, Any]]) -> int:
        """Choose an index into the supplied (already legal) action list."""

    def learn(self, transitions: list[dict[str, Any]]) -> None:
        """Optional offline training; algorithms may override."""

class FirstLegalAgent(Agent):
    def act(self, observation, legal_actions):
        if not legal_actions:
            raise ValueError('No legal actions')
        return 0

class RandomAgent(Agent):
    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def act(self, observation, legal_actions):
        if not legal_actions:
            raise ValueError('No legal actions')
        return self.rng.randrange(len(legal_actions))

def action_index(record: dict[str, Any]) -> int | None:
    """Recover the chosen index only if we can match it unambiguously."""
    actions = record.get('LegalActions')
    response = record.get('PolicyResponse') or {}
    if not isinstance(actions, list) or not actions:
        return None
    idx = response.get('ActionIndex')
    if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(actions):
        return idx
    chosen = record.get('ChosenAction')
    matches = [i for i, action in enumerate(actions) if action == chosen]
    return matches[0] if len(matches) == 1 else None

def load_verified(path: Path) -> Iterator[Decision]:
    """Read exporter output; reject non-native-resolved records."""
    with path.open(encoding='utf-8') as handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get('Executed') is not True or record.get('NextObservation') is None:
                raise ValueError(f'{path}:{lineno}: unverified transition')
            legal = record.get('LegalActions')
            if not isinstance(legal, list):
                # CardSelection and some special phases use separate option formats;
                # don't fabricate legal actions for them.
                continue
            yield Decision(
                run_id=record['RunId'], sequence=record['Sequence'],
                phase=record['DecisionType'], observation=record['Observation'],
                legal_actions=legal, chosen_index=action_index(record),
                run_outcome=record.get('RunOutcome'),
            )
