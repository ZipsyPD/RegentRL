"""Run-level October card mechanics grounded in the bundled C# reference."""
from __future__ import annotations

from sts2_env.core.enums import CardId, MapPointType


def before_map_room_entered(player, point_type: MapPointType | None) -> int:
    """Advance Dowsing only for unknown map points while still in the deck.

    Mirrors Dowsing.BeforeRoomEntered's quest counter/transform behavior for
    the single-player deck. Returns the number transformed into Abundance.
    The C# multiplayer room-count guard is not modeled here.
    """
    if point_type != MapPointType.UNKNOWN:
        return 0
    from sts2_env.cards.factory import create_card
    changed = 0
    for index, card in enumerate(player.deck):
        if card.card_id != CardId.DOWSING:
            continue
        remaining = max(0, int(card.effect_vars.get('rooms', 5)) - 1)
        card.effect_vars['rooms'] = remaining
        if remaining == 0:
            replacement = create_card(CardId.ABUNDANCE)
            replacement.instance_id = card.instance_id
            player.deck[index] = replacement
            changed += 1
    return changed
