"""Character definitions for all five playable STS2 characters.

Each CharacterConfig captures the starting stats, starting relic,
starting deck composition, card-pool membership, and any character-
specific mechanic (orb slots, Stars, Osty companion).

Data sourced from the decompiled C# character and card-pool models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from sts2_env.core.card_pools import (
    COLORLESS_CARD_POOL,
    DEFECT_CARD_POOL,
    IRONCLAD_CARD_POOL,
    NECROBINDER_CARD_POOL,
    REGENT_CARD_POOL,
    SILENT_CARD_POOL,
)
from sts2_env.core.enums import CardId
from sts2_env.relics.base import RelicId

if TYPE_CHECKING:
    from sts2_env.cards.base import CardInstance


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CharacterConfig:
    """Immutable description of a playable character."""

    character_id: str
    starting_hp: int
    starting_gold: int
    max_energy: int
    starting_relic: RelicId
    starting_deck: tuple[tuple[CardId, int], ...]
    """(CardId, count) pairs that make up the starting deck."""
    card_pool: tuple[CardId, ...]
    """Every CardId in this character's class card pool."""
    # Character-specific mechanic flags
    base_orb_slots: int = 0
    uses_stars: bool = False
    has_osty: bool = False

    @property
    def starting_deck_size(self) -> int:
        return sum(count for _, count in self.starting_deck)


# ---------------------------------------------------------------------------
# Card pools are imported from sts2_env.core.card_pools in reference order.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Character configurations
# ---------------------------------------------------------------------------

IRONCLAD = CharacterConfig(
    character_id="Ironclad",
    starting_hp=80,
    starting_gold=99,
    max_energy=3,
    starting_relic=RelicId.BURNING_BLOOD,
    starting_deck=(
        (CardId.STRIKE_IRONCLAD, 5),
        (CardId.DEFEND_IRONCLAD, 4),
        (CardId.BASH, 1),
    ),
    card_pool=IRONCLAD_CARD_POOL,
)

SILENT = CharacterConfig(
    character_id="Silent",
    starting_hp=70,
    starting_gold=99,
    max_energy=3,
    starting_relic=RelicId.RING_OF_THE_SNAKE,
    starting_deck=(
        (CardId.STRIKE_SILENT, 5),
        (CardId.DEFEND_SILENT, 5),
        (CardId.NEUTRALIZE, 1),
        (CardId.SURVIVOR, 1),
    ),
    card_pool=SILENT_CARD_POOL,
)

DEFECT = CharacterConfig(
    character_id="Defect",
    starting_hp=75,
    starting_gold=99,
    max_energy=3,
    starting_relic=RelicId.CRACKED_CORE,
    starting_deck=(
        (CardId.STRIKE_DEFECT, 4),
        (CardId.DEFEND_DEFECT, 4),
        (CardId.ZAP, 1),
        (CardId.DUALCAST, 1),
    ),
    card_pool=DEFECT_CARD_POOL,
    base_orb_slots=3,
)

REGENT = CharacterConfig(
    character_id="Regent",
    starting_hp=75,
    starting_gold=99,
    max_energy=3,
    starting_relic=RelicId.DIVINE_RIGHT,
    starting_deck=(
        (CardId.STRIKE_REGENT, 4),
        (CardId.DEFEND_REGENT, 4),
        (CardId.FALLING_STAR, 1),
        (CardId.VENERATE, 1),
    ),
    card_pool=REGENT_CARD_POOL,
    uses_stars=True,
)

NECROBINDER = CharacterConfig(
    character_id="Necrobinder",
    starting_hp=66,
    starting_gold=99,
    max_energy=3,
    starting_relic=RelicId.BOUND_PHYLACTERY,
    starting_deck=(
        (CardId.STRIKE_NECROBINDER, 4),
        (CardId.DEFEND_NECROBINDER, 4),
        (CardId.BODYGUARD, 1),
        (CardId.UNLEASH, 1),
    ),
    card_pool=NECROBINDER_CARD_POOL,
    has_osty=True,
)


ALL_CHARACTERS: Sequence[CharacterConfig] = (
    IRONCLAD,
    SILENT,
    DEFECT,
    REGENT,
    NECROBINDER,
)

_BY_ID: dict[str, CharacterConfig] = {
    cfg.character_id.lower(): cfg for cfg in ALL_CHARACTERS
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_character(character_id: str) -> CharacterConfig:
    """Look up a character config by name (case-insensitive).

    >>> get_character("Ironclad").starting_hp
    80
    """
    key = character_id.lower()
    cfg = _BY_ID.get(key)
    if cfg is None:
        valid = ", ".join(sorted(_BY_ID))
        raise ValueError(
            f"Unknown character {character_id!r}. "
            f"Valid ids: {valid}"
        )
    return cfg


def create_starting_deck(character_id: str) -> list[CardInstance]:
    """Create the starting deck for the given character.

    Delegates to the per-character ``create_<char>_starter_deck``
    factory so that each card instance gets correct stats, keywords,
    and a unique ``instance_id``.

    >>> len(create_starting_deck("Ironclad"))
    10
    """
    key = character_id.lower()
    factory = _STARTER_DECK_FACTORIES.get(key)
    if factory is None:
        valid = ", ".join(sorted(_STARTER_DECK_FACTORIES))
        raise ValueError(
            f"Unknown character {character_id!r}. "
            f"Valid ids: {valid}"
        )
    return factory()


# ---------------------------------------------------------------------------
# Starter-deck factory registry
#
# Each character module already defines a create_<char>_starter_deck()
# that builds the exact cards with the right factories.  We import
# lazily so this module can be imported without pulling in every card
# effect function at import time.
# ---------------------------------------------------------------------------

def _make_ironclad_deck() -> list[CardInstance]:
    from sts2_env.cards.ironclad import (
        create_ironclad_starter_deck,
    )
    return create_ironclad_starter_deck()


def _make_silent_deck() -> list[CardInstance]:
    from sts2_env.cards.silent import (
        create_silent_starter_deck,
    )
    return create_silent_starter_deck()


def _make_defect_deck() -> list[CardInstance]:
    from sts2_env.cards.defect import (
        create_defect_starter_deck,
    )
    return create_defect_starter_deck()


def _make_regent_deck() -> list[CardInstance]:
    from sts2_env.cards.regent import (
        create_regent_starter_deck,
    )
    return create_regent_starter_deck()


def _make_necrobinder_deck() -> list[CardInstance]:
    from sts2_env.cards.necrobinder import (
        create_necrobinder_starter_deck,
    )
    return create_necrobinder_starter_deck()


_STARTER_DECK_FACTORIES: dict[str, object] = {
    "ironclad": _make_ironclad_deck,
    "silent": _make_silent_deck,
    "defect": _make_defect_deck,
    "regent": _make_regent_deck,
    "necrobinder": _make_necrobinder_deck,
}
