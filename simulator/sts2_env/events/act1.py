"""Act 1 (Act 0) specific events.

Events that only appear in Act 1 (act_index 0 or < 2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts2_env.cards.factory import create_card
from sts2_env.core.enums import CardId, CardRarity
from sts2_env.run.events import EventModel, EventOption, EventResult, register_event
from sts2_env.events.shared import _event_result_with_rewards, _roll_event_potion_id, _should_defer_event_rewards
from sts2_env.run.reward_objects import AddCardsReward, CardReward, PotionReward, RelicReward
from sts2_env.run.rewards import CARD_CREATION_SOURCE_OTHER

if TYPE_CHECKING:
    from sts2_env.run.run_state import RunState


_BRAIN_LEECH_RIP_HP_LOSS = 5
_BRAIN_LEECH_REWARD_COUNT = 1
_BRAIN_LEECH_RIP_CARD_OPTION_COUNT = 3
_BRAIN_LEECH_SHARE_CARD_CHOICE_COUNT = 1
_BRAIN_LEECH_SHARE_FROM_CARD_CHOICE_COUNT = 5
_ROOM_FULL_OF_CHEESE_SEARCH_HP_LOSS = 14
_ROOM_FULL_OF_CHEESE_GORGE_CARD_CHOICE_COUNT = 2
_ROOM_FULL_OF_CHEESE_GORGE_FROM_CARD_CHOICE_COUNT = 8
_THE_LEGENDS_WERE_TRUE_MIN_HP = 10
_THE_LEGENDS_WERE_TRUE_EXIT_HP_LOSS = 8
_TEA_MASTER_BONE_TEA_COST = 50
_TEA_MASTER_EMBER_TEA_COST = 150


# ── BrainLeech ────────────────────────────────────────────────────────

class BrainLeech(EventModel):
    """Share Knowledge: Pick 1 of 5 character cards to gain.
    Rip: Take 5 damage, gain a colorless card reward.
    """

    event_id = "BrainLeech"

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.current_act_index < 2

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        return [
            EventOption("share_knowledge", "Share Knowledge",
                         "Pick 1 of 5 character cards to gain"),
            EventOption("rip", "Rip", "Take 5 damage, gain a colorless card"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "rip":
            run_state.player.lose_hp(_BRAIN_LEECH_RIP_HP_LOSS)
            return EventResult(
                finished=True,
                description="Took 5 damage, gained a colorless card.",
                rewards={
                    "reward_objects": [
                        CardReward(
                            run_state.player.player_id,
                            option_count=_BRAIN_LEECH_RIP_CARD_OPTION_COUNT,
                            character_ids=(),
                            include_colorless=True,
                            generation_context=None,
                            roll_upgrade=False,
                            use_default_character_pool=False,
                        )
                        for _ in range(_BRAIN_LEECH_REWARD_COUNT)
                    ]
                },
            )
        return EventResult(
            finished=True,
            description="Gained a character card.",
            rewards={
                "reward_objects": [
                    CardReward(
                        run_state.player.player_id,
                        option_count=_BRAIN_LEECH_SHARE_FROM_CARD_CHOICE_COUNT,
                        cards_to_pick=_BRAIN_LEECH_SHARE_CARD_CHOICE_COUNT,
                        skippable=False,
                        generation_context=None,
                        roll_upgrade=False,
                    )
                ]
            },
        )


register_event(BrainLeech())


# ── RoomFullOfCheese ──────────────────────────────────────────────────

class RoomFullOfCheese(EventModel):
    """Gorge: Pick 2 of 8 common character cards.
    Search: Take 14 damage, gain Chosen Cheese relic.
    """

    event_id = "RoomFullOfCheese"

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.current_act_index < 2

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        return [
            EventOption("gorge", "Gorge",
                         "Pick 2 of 8 common cards"),
            EventOption("search", "Search",
                         "Take 14 damage, gain Chosen Cheese relic"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "gorge":
            return EventResult(
                finished=True,
                description="Picked 2 common character cards.",
                rewards={
                    "reward_objects": [
                        CardReward(
                            run_state.player.player_id,
                            option_count=_ROOM_FULL_OF_CHEESE_GORGE_FROM_CARD_CHOICE_COUNT,
                            cards_to_pick=_ROOM_FULL_OF_CHEESE_GORGE_CARD_CHOICE_COUNT,
                            skippable=False,
                            generation_context=None,
                            roll_upgrade=False,
                            card_creation_source=CARD_CREATION_SOURCE_OTHER,
                            allow_rarity_modifications=False,
                            card_pool_rarity_filter=CardRarity.COMMON,
                            use_uniform_noncombat_odds=True,
                        )
                    ]
                },
            )
        run_state.player.lose_hp(_ROOM_FULL_OF_CHEESE_SEARCH_HP_LOSS)
        if _should_defer_event_rewards(run_state):
            return _event_result_with_rewards(
                "Took 14 damage, gained Chosen Cheese relic.",
                [RelicReward(run_state.player.player_id, relic_id="CHOSEN_CHEESE")],
            )
        run_state.player.obtain_relic("CHOSEN_CHEESE")
        return EventResult(finished=True,
                           description="Took 14 damage, gained Chosen Cheese relic.")


register_event(RoomFullOfCheese())


# ── TheLegendsWereTrue ────────────────────────────────────────────────

class TheLegendsWereTrue(EventModel):
    """Nab the Map: Gain Spoils Map card.
    Slowly Find an Exit: Take 8 damage, gain a potion.
    """

    event_id = "TheLegendsWereTrue"

    def is_allowed(self, run_state: RunState) -> bool:
        return (
            run_state.current_act_index == 0
            and all(len(player.deck) > 0 for player in run_state.players)
            and all(player.current_hp >= _THE_LEGENDS_WERE_TRUE_MIN_HP for player in run_state.players)
        )

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        return [
            EventOption("nab_map", "Nab the Map", "Gain Spoils Map card"),
            EventOption("find_exit", "Slowly Find an Exit",
                         "Take 8 damage, gain a potion"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "nab_map":
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Gained Spoils Map card.",
                    [AddCardsReward(run_state.player.player_id, [create_card(CardId.SPOILS_MAP)])],
                )
            run_state.player.add_card_instance_to_deck(create_card(CardId.SPOILS_MAP))
            return EventResult(finished=True, description="Gained Spoils Map card.")
        run_state.player.lose_hp(_THE_LEGENDS_WERE_TRUE_EXIT_HP_LOSS)
        reward_objects = []
        potion_id = _roll_event_potion_id(run_state)
        if potion_id is not None:
            reward_objects.append(PotionReward(run_state.player.player_id, potion_id=potion_id))
        return EventResult(finished=True,
                           description="Took 8 damage, gained a potion.",
                           rewards={"reward_objects": reward_objects})


register_event(TheLegendsWereTrue())


# ── TeaMaster ────────────────────────────────────────────────────────

class TeaMaster(EventModel):
    """Bone Tea: Pay 50g, gain Bone Tea relic.
    Ember Tea: Pay 150g, gain Ember Tea relic.
    Tea of Discourtesy: Free, gain Tea of Discourtesy relic.
    """

    event_id = "TeaMaster"

    def is_allowed(self, run_state: RunState) -> bool:
        return (
            run_state.current_act_index < 2
            and all(player.gold >= _TEA_MASTER_EMBER_TEA_COST for player in run_state.players)
        )

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        gold = run_state.player.gold
        return [
            EventOption(
                "bone_tea",
                "Bone Tea (50g)" if gold >= _TEA_MASTER_BONE_TEA_COST else "Bone Tea",
                "Gain Bone Tea relic",
                enabled=gold >= _TEA_MASTER_BONE_TEA_COST,
            ),
            EventOption(
                "ember_tea",
                "Ember Tea (150g)" if gold >= _TEA_MASTER_EMBER_TEA_COST else "Ember Tea",
                "Gain Ember Tea relic",
                enabled=gold >= _TEA_MASTER_EMBER_TEA_COST,
            ),
            EventOption("discourtesy", "Tea of Discourtesy", "Free: gain Tea of Discourtesy relic"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "bone_tea":
            run_state.player.lose_gold(_TEA_MASTER_BONE_TEA_COST)
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Paid 50g, gained Bone Tea relic.",
                    [RelicReward(run_state.player.player_id, relic_id="BONE_TEA")],
                )
            run_state.player.obtain_relic("BONE_TEA")
            return EventResult(finished=True, description="Paid 50g, gained Bone Tea relic.")
        if option_id == "ember_tea":
            run_state.player.lose_gold(_TEA_MASTER_EMBER_TEA_COST)
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Paid 150g, gained Ember Tea relic.",
                    [RelicReward(run_state.player.player_id, relic_id="EMBER_TEA")],
                )
            run_state.player.obtain_relic("EMBER_TEA")
            return EventResult(finished=True, description="Paid 150g, gained Ember Tea relic.")
        if _should_defer_event_rewards(run_state):
            return _event_result_with_rewards(
                "Gained Tea of Discourtesy relic.",
                [RelicReward(run_state.player.player_id, relic_id="TEA_OF_DISCOURTESY")],
            )
        run_state.player.obtain_relic("TEA_OF_DISCOURTESY")
        return EventResult(finished=True, description="Gained Tea of Discourtesy relic.")


register_event(TeaMaster())
