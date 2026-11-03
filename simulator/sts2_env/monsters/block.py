"""Monster block helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts2_env.core.damage import calculate_block
from sts2_env.core.enums import ValueProp

if TYPE_CHECKING:
    from sts2_env.core.combat import CombatState
    from sts2_env.core.creature import Creature


def gain_move_block(creature: Creature, amount: int, combat: CombatState) -> None:
    if combat.is_over:
        return
    block = calculate_block(amount, creature, ValueProp.MOVE, combat)
    before = creature.block
    creature.gain_block(block)
    gained = creature.block - before
    if gained > 0:
        from sts2_env.core.hooks import fire_after_block_gained

        fire_after_block_gained(creature, gained, combat, ValueProp.MOVE, None)
