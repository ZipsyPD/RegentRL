"""October 2026 cards. Unimplemented effects fail explicitly rather than pretending to work.

Source definitions: decompiled/MegaCrit.Sts2.Core.Models.Cards/*.cs.
New cards are not added to reward pools until their effects are verified.
"""
from sts2_env.core.enums import CardId, PowerId, ValueProp
from sts2_env.cards.base import CardInstance
from sts2_env.cards.reference_static_metadata import reference_metadata_by_card_id, reference_dynamic_vars_by_card_id, upgraded_reference_metadata_by_card_id, upgraded_reference_dynamic_vars_by_card_id
from sts2_env.cards.registry import register_effect
from sts2_env.core.damage import calculate_damage, apply_damage, calculate_block
from sts2_env.core.hooks import fire_after_block_gained

CARD_NAMES = {'ABUNDANCE': 'Abundance', 'BLADE_SYMPHONY': 'BladeSymphony', 'BLAZE': 'Blaze', 'CACOPHONY': 'Cacophony', 'CONCOCT': 'Concoct', 'CONSTELLATION': 'Constellation', 'DOWSING': 'Dowsing', 'FADE': 'Fade', 'HIBERNATE': 'Hibernate', 'IMITATION_LEARNING': 'ImitationLearning', 'MIDNIGHT': 'Midnight', 'NOT_YET': 'NotYet', 'ONE_FOR_ALL': 'OneForAll', 'OUTRAGE': 'Outrage', 'PLOT': 'Plot', 'SIDESTEP': 'Sidestep', 'SOULBOUND': 'Soulbound', 'THE_BALL': 'TheBall', 'TUTOR': 'Tutor', 'UNDERWORLD': 'Underworld', 'WITHER': 'Wither'}

for _symbol in CARD_NAMES:
    _cid = getattr(CardId, _symbol)
    def _factory(upgraded=False, *, _id=_cid):
        metadata = (upgraded_reference_metadata_by_card_id() if upgraded else reference_metadata_by_card_id())[_id]
        vars_ = dict((upgraded_reference_dynamic_vars_by_card_id() if upgraded else reference_dynamic_vars_by_card_id()).get(_id, {}))
        return CardInstance(card_id=_id, cost=metadata.cost, card_type=metadata.card_type,
            target_type=metadata.target_type, rarity=metadata.rarity, upgraded=upgraded and metadata.cost >= 0 and _id not in {CardId.DOWSING, CardId.WITHER},
            keywords=metadata.keywords, tags=metadata.tags, base_damage=vars_.get("damage"),
            base_block=vars_.get("block"), effect_vars=vars_, star_cost=metadata.star_cost,
            has_energy_cost_x=metadata.has_energy_cost_x, has_star_cost_x=metadata.has_star_cost_x,
            can_be_generated_in_combat=False, can_be_generated_by_modifiers=False)
    _factory.__name__ = f"make_{_symbol.lower()}"
    globals()[_factory.__name__] = _factory


def _owner(card, combat):
    return getattr(card, "owner", None) or combat.primary_player

def _power(card, combat, target, power, key, default):
    combat.apply_power_to(target, power, card.effect_vars.get(key, default))

@register_effect(CardId.BLAZE)
def blaze(card, combat, target):
    _power(card, combat, target or _owner(card, combat), PowerId.STRENGTH, "strength", 7 if card.upgraded else 5)

@register_effect(CardId.SIDESTEP)
def sidestep(card, combat, target):
    _power(card, combat, _owner(card, combat), PowerId.ENERGY_NEXT_TURN, "energy", 2 if card.upgraded else 1)

@register_effect(CardId.PLOT)
def plot(card, combat, target):
    _power(card, combat, _owner(card, combat), PowerId.DRAW_CARDS_NEXT_TURN, "cards", 3 if card.upgraded else 2)

@register_effect(CardId.OUTRAGE)
def outrage(card, combat, target):
    if target is None:
        raise ValueError("Outrage requires an enemy target")
    owner = _owner(card, combat)
    amount = calculate_damage(card.base_damage, owner, target, ValueProp.MOVE, combat)
    apply_damage(target, amount, ValueProp.MOVE, combat, owner)
    # Its additional copies go to *other players* in multiplayer; solo has no recipients.

@register_effect(CardId.CONSTELLATION)
def constellation(card, combat, target):
    owner = target or _owner(card, combat)
    combat._draw_cards(card.effect_vars.get("cards", 0))
    combat.gain_energy(owner, card.effect_vars.get("energy", 0))
    before = owner.block
    block = calculate_block(card.base_block or card.effect_vars.get("block", 0), owner, ValueProp.MOVE, combat, card_source=card)
    owner.gain_block(block)
    if owner.block > before:
        fire_after_block_gained(owner, owner.block-before, combat, ValueProp.MOVE, combat.active_card_play_token)

@register_effect(CardId.NOT_YET)
def not_yet(card, combat, target):
    """Restore HP to the owner; exhaust is handled by the card-play engine."""
    _owner(card, combat).heal(card.effect_vars.get("heal", 0))

@register_effect(CardId.THE_BALL)
def the_ball(card, combat, target):
    """Single-player card-play damage accumulation (card retains its instance)."""
    if target is None:
        raise ValueError("The Ball requires an enemy target")
    owner = _owner(card, combat)
    amount = calculate_damage(card.base_damage, owner, target, ValueProp.MOVE, combat)
    apply_damage(target, amount, ValueProp.MOVE, combat, owner)
    increase = card.effect_vars.get("increase", 10)
    card.base_damage = (card.base_damage or 0) + increase
    card.effect_vars["damage"] = card.base_damage

from sts2_env.cards.registry import register_turn_end_in_hand_hook

@register_turn_end_in_hand_hook(CardId.WITHER)
def wither_turn_end(card, combat, cards_in_hand_at_turn_end):
    from sts2_env.cards.status import _deal_self_damage
    _deal_self_damage(card, combat, card.effect_vars.get("damage", 3))


@register_effect(CardId.MIDNIGHT)
def midnight(card, combat, target):
    """Source: Midnight.OnPlay. Its cost reduction on exhaust is a separate hook."""
    if target is None:
        raise ValueError("Midnight requires an enemy target")
    owner = _owner(card, combat)
    amount = calculate_damage(card.base_damage, owner, target, ValueProp.MOVE, combat)
    apply_damage(target, amount, ValueProp.MOVE, combat, owner)


@register_effect(CardId.TUTOR)
def tutor(card, combat, target):
    """Source: Tutor.OnPlay; player selects one card from the draw pile."""
    if target is not None and target is not _owner(card, combat):
        raise NotImplementedError("Tutor ally-targeted selection needs multiplayer support")
    candidates = list(combat.draw_pile)
    if not candidates:
        return
    combat.request_card_choice(
        prompt="Choose a card from your draw pile",
        cards=candidates,
        source_pile="draw",
        resolver=combat.move_card_to_hand,
    )


@register_effect(CardId.ABUNDANCE)
def abundance(card, combat, target):
    """Choose one of three distinct random, upgraded Powers; add it free to hand.

    Mirrors Abundance.OnPlay in the October decompilation. The combat choice
    mechanism keeps the decision observable to an RL agent.
    """
    from sts2_env.cards.factory import create_distinct_character_cards
    from sts2_env.core.enums import CardType

    owner = _owner(card, combat)
    state = combat.combat_player_state_for(owner)
    if state is None:
        raise RuntimeError("Abundance requires an active combat player state")
    choices = create_distinct_character_cards(
        state.character_id, combat.combat_card_generation_rng, 3,
        card_type=CardType.POWER, generation_context="combat",
        is_multiplayer=combat.is_multiplayer,
    )
    for choice in choices:
        combat.upgrade_card(choice)
    if not choices:
        return

    def accept(chosen):
        if chosen is None:
            return
        chosen.set_temporary_free_this_turn()
        combat.add_generated_card_to_creature_hand(owner, chosen)

    combat.request_card_choice(
        prompt="Choose an upgraded Power to add to your hand for free",
        cards=choices, source_pile="generated", resolver=accept,
        owner=owner,
    )
