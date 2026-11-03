"""Powers that react to damage events (taking or dealing damage).

Covers: ThornsPower, FlameBarrierPower, CurlUpPower, SelfFormingClayPower,
ReflectPower, GalvanicPower, InterceptPower.

All logic verified against decompiled C# source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts2_env.core.enums import (
    CardId,
    CombatSide,
    PowerId,
    PowerType,
    PowerStackType,
    ValueProp,
)
from sts2_env.powers.base import PowerInstance

if TYPE_CHECKING:
    from sts2_env.core.creature import Creature
    from sts2_env.core.combat import CombatState


def _gain_unpowered_block(owner: Creature, amount: int, combat: CombatState) -> int:
    before = owner.block
    owner.gain_block(amount, unpowered=True)
    gained = owner.block - before
    if gained > 0:
        from sts2_env.core.hooks import fire_after_block_gained

        fire_after_block_gained(owner, gained, combat)
    return gained


# ---------------------------------------------------------------------------
# ThornsPower
# ---------------------------------------------------------------------------
class ThornsPower(PowerInstance):
    """Whenever you are hit by a powered attack, deal Amount damage back
    to the attacker (unpowered, skip-hurt-anim).

    C# ref: ThornsPower.cs
    - BeforeDamageReceived: if target == owner and dealer exists and
      powered attack, deal Amount damage to dealer.
    StackType.Counter.
    """

    power_type = PowerType.BUFF
    stack_type = PowerStackType.COUNTER

    def __init__(self, amount: int):
        super().__init__(PowerId.THORNS, amount)

    def before_damage_received(
        self,
        owner: Creature,
        target: Creature,
        dealer: Creature | None,
        damage: int,
        props: ValueProp,
        combat: CombatState,
    ) -> None:
        from sts2_env.cards.colorless import is_omnislice

        card_source = getattr(combat, "active_card_source", None)
        if target is owner and dealer is not None and (props.is_powered_attack() or is_omnislice(card_source)):
            combat.deal_damage(
                dealer=owner,
                target=dealer,
                amount=self.amount,
                props=ValueProp.UNPOWERED | ValueProp.SKIP_HURT_ANIM,
            )


# ---------------------------------------------------------------------------
# FlameBarrierPower
# ---------------------------------------------------------------------------
class FlameBarrierPower(PowerInstance):
    """Whenever you are hit by a powered attack, deal Amount damage back
    to the attacker (unpowered). Removed at end of the opposing side's turn.

    C# ref: FlameBarrierPower.cs
    - AfterDamageReceived: if target == owner and dealer exists and
      powered attack, deal Amount damage to dealer.
    - AfterTurnEnd: remove when the OPPOSITE side's turn ends
      (i.e., when enemy turn ends if you applied it on player turn).
    StackType.Counter.
    """

    power_type = PowerType.BUFF
    stack_type = PowerStackType.COUNTER

    def __init__(self, amount: int):
        super().__init__(PowerId.FLAME_BARRIER, amount)

    def after_damage_received(
        self,
        owner: Creature,
        target: Creature,
        dealer: Creature | None,
        damage: int,
        props: ValueProp,
        combat: CombatState,
    ) -> None:
        if target is owner and dealer is not None and props.is_powered_attack():
            combat.deal_damage(
                dealer=owner,
                target=dealer,
                amount=self.amount,
                props=ValueProp.UNPOWERED,
            )

    def after_turn_end(
        self, owner: Creature, side: CombatSide, combat: CombatState
    ) -> None:
        # Remove when the turn of the side OPPOSITE to owner ends.
        # C#: if (base.Owner.Side != side) -> remove.
        if owner.side != side:
            owner.powers.pop(self.power_id, None)


# ---------------------------------------------------------------------------
# CurlUpPower
# ---------------------------------------------------------------------------
class CurlUpPower(PowerInstance):
    """The first time you are hit by a powered attack (from a card), gain
    Amount Block and remove this power.

    C# ref: CurlUpPower.cs
    - AfterDamageReceived: if target == owner and powered attack from a card,
      mark the card source. After that card finishes playing, gain block
      and remove self.
    StackType.Counter. Single-use (removed after triggering).

    """

    power_type = PowerType.BUFF
    stack_type = PowerStackType.COUNTER
    should_scale_in_multiplayer = True

    def __init__(self, amount: int):
        super().__init__(PowerId.CURL_UP, amount)
        self._triggered_card: object | None = None

    def after_damage_received(
        self,
        owner: Creature,
        target: Creature,
        dealer: Creature | None,
        damage: int,
        props: ValueProp,
        combat: CombatState,
    ) -> None:
        if (
            target is owner
            and self._triggered_card is None
            and props.is_powered_attack()
            and dealer is not None
        ):
            self._triggered_card = getattr(combat, "active_card_source", None)

    def after_card_played(self, owner: Creature, card: object, combat: CombatState) -> None:
        if card is self._triggered_card:
            self._triggered_card = None
            _gain_unpowered_block(owner, self.amount, combat)
            owner.powers.pop(self.power_id, None)


# ---------------------------------------------------------------------------
# SelfFormingClayPower
# ---------------------------------------------------------------------------
class SelfFormingClayPower(PowerInstance):
    """When your block is fully broken, gain Amount Block and remove this power.

    C# ref: SelfFormingClayPower.cs
    - AfterBlockCleared: if creature == owner, gain block and remove self.
    StackType.Counter. Single-use.

    NOTE: The C# hook is AfterBlockCleared, which fires when block drops
    to 0. In the simulator, we check after damage if block was broken.
    """

    power_type = PowerType.BUFF
    stack_type = PowerStackType.COUNTER

    def __init__(self, amount: int):
        super().__init__(PowerId.SELF_FORMING_CLAY, amount)

    def after_block_cleared(self, owner: Creature, creature: Creature, combat: CombatState) -> None:
        if creature is owner:
            _gain_unpowered_block(owner, self.amount, combat)
            combat._remove_power(owner, self.power_id)

# ---------------------------------------------------------------------------
# ReflectPower
# ---------------------------------------------------------------------------
class ReflectPower(PowerInstance):
    """Whenever you are hit by a powered attack and block some damage, deal
    the blocked amount back to the attacker. Decrements at start of your turn.

    C# ref: ReflectPower.cs
    - AfterDamageReceived: if target == owner, result.BlockedDamage > 0,
      powered attack, and dealer exists, deal BlockedDamage to dealer.
    - AfterSideTurnStart: decrement on owner's side.
    StackType.Counter.

    """

    power_type = PowerType.BUFF
    stack_type = PowerStackType.COUNTER

    def __init__(self, amount: int):
        super().__init__(PowerId.REFLECT, amount)

    def after_damage_received(
        self,
        owner: Creature,
        target: Creature,
        dealer: Creature | None,
        damage: int,
        props: ValueProp,
        combat: CombatState,
    ) -> None:
        result = getattr(combat, "_active_damage_result", None)
        blocked_amount = getattr(result, "blocked", 0)
        if target is owner and blocked_amount > 0 and dealer is not None and props.is_powered_attack():
            combat.deal_damage(
                dealer=owner,
                target=dealer,
                amount=blocked_amount,
                props=ValueProp.UNPOWERED,
            )

    def after_side_turn_start(
        self, owner: Creature, side: CombatSide, combat: CombatState
    ) -> None:
        if side == owner.side:
            self.amount -= 1
            if self.amount <= 0:
                owner.powers.pop(self.power_id, None)


# ---------------------------------------------------------------------------
# GalvanicPower
# ---------------------------------------------------------------------------
class GalvanicPower(PowerInstance):
    """Power cards are afflicted with "Galvanized" -- when played, they deal
    Amount damage to the player who played them.

    C# ref: GalvanicPower.cs
    - BeforeCombatStart: afflict all Power cards with Galvanized.
    - AfterCardEnteredCombat: afflict new Power cards.
    - AfterCardPlayed: if card has Galvanized, deal Amount damage to card
      owner (unpowered, as a MOVE).
    StackType.Counter.

    Galvanized is tracked on the card's combat vars.
    """

    power_type = PowerType.BUFF
    stack_type = PowerStackType.COUNTER
    _MARKER = "_galvanized"

    def __init__(self, amount: int):
        super().__init__(PowerId.GALVANIC, amount)

    def _afflict_card(self, card: object) -> None:
        from sts2_env.core.enums import CardType

        if getattr(card, "card_type", None) != CardType.POWER:
            return
        combat_vars = getattr(card, "combat_vars", None)
        if combat_vars is None or combat_vars.get(self._MARKER):
            return
        afflict = getattr(card, "afflict", None)
        if callable(afflict) and not afflict("galvanized", stackable=True):
            return
        combat_vars[self._MARKER] = 1

    def before_combat_start(self, owner: Creature, combat: CombatState) -> None:
        for state in combat.combat_player_states:
            for pile in state.all_piles:
                for card in pile:
                    self._afflict_card(card)

    def after_card_entered_combat(self, owner: Creature, card: object, combat: CombatState) -> None:
        self._afflict_card(card)

    def after_card_played(
        self, owner: Creature, card: object, combat: CombatState
    ) -> None:
        if getattr(card, "combat_vars", {}).get(self._MARKER):
            card_owner_creature = getattr(card, "owner", None)
            if card_owner_creature is not None:
                combat.deal_damage(
                    dealer=None,
                    target=card_owner_creature,
                    amount=self.amount,
                    props=ValueProp.UNPOWERED | ValueProp.MOVE,
                )


# ---------------------------------------------------------------------------
# InterceptPower
# ---------------------------------------------------------------------------
class InterceptPower(PowerInstance):
    """Takes increased damage from powered attacks proportional to the number
    of creatures being covered (+1 multiplier per covered creature).
    Removed at end of enemy turn.

    C# ref: InterceptPower.cs
    - ModifyDamageMultiplicative: (coveredCreatures.Count + 1) multiplier
      for powered attacks targeting owner.
    - AfterTurnEnd: remove at end of ENEMY side turn.
    StackType.Single.

    Simplified: The covered-creature list is tracked as a simple count
    stored in amount. The multiplier is (amount) since amount = count + 1
    from how CoveredPower sets it up.
    """

    power_type = PowerType.BUFF
    stack_type = PowerStackType.SINGLE

    def __init__(self, amount: int = 1):
        super().__init__(PowerId.INTERCEPT, amount)
        self._covered_creatures: list[Creature] = []

    def add_covered_creature(self, creature: Creature) -> None:
        """Called by CoveredPower when a creature is covered."""
        if creature not in self._covered_creatures:
            self._covered_creatures.append(creature)

    def remove_covered_creature(self, creature: Creature) -> None:
        """Called when a previously covered creature is no longer covered."""
        if creature in self._covered_creatures:
            self._covered_creatures.remove(creature)

    def modify_damage_multiplicative(
        self,
        owner: Creature,
        dealer: Creature | None,
        target: Creature,
        props: ValueProp,
    ) -> float:
        if target is owner and props.is_powered_attack():
            return float(len(self._covered_creatures) + 1)
        return 1.0

    def after_turn_end(
        self, owner: Creature, side: CombatSide, combat: CombatState
    ) -> None:
        if side == CombatSide.ENEMY:
            owner.powers.pop(self.power_id, None)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
from sts2_env.core.creature import register_power_class  # noqa: E402

_ALL_POWERS: dict[PowerId, type[PowerInstance]] = {
    PowerId.THORNS: ThornsPower,
    PowerId.FLAME_BARRIER: FlameBarrierPower,
    PowerId.CURL_UP: CurlUpPower,
    PowerId.SELF_FORMING_CLAY: SelfFormingClayPower,
    PowerId.REFLECT: ReflectPower,
    PowerId.GALVANIC: GalvanicPower,
    PowerId.INTERCEPT: InterceptPower,
}

for _pid, _cls in _ALL_POWERS.items():
    register_power_class(_pid, _cls)
