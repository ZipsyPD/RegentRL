# Parity Coverage Backlog

This document inventories the gameplay surfaces that still lack direct parity proof against the decompiled Slay the Spire 2 logic.

It complements [PARITY_GAPS.md](./PARITY_GAPS.md):

- `PARITY_GAPS.md` answers "why can we not yet claim exact parity?"
- this document answers "which card / relic / event surfaces still lack direct coverage?"

Absence from this document's covered lists is not proof of a bug. It means the repository does not yet have strong, targeted proof for that surface.

## Post-Agent Updates

The detailed backlog sections below were captured as the pre-pass baseline. After the latest local coverage passes, the stricter direct-reference audit including deprecated save placeholders reports:

| Surface | Total | Missing implementation references | Missing direct test references |
| --- | ---: | ---: | ---: |
| Cards | 577 | 0 | 0 |
| Encounters | 88 | 0 | 0 |
| Events | 68 | 0 | 0 |
| Modifiers | 17 | 0 | 0 |
| Monsters | 121 | 0 | 0 |
| Potions | 64 | 0 | 0 |
| Powers | 260 | 0 | 0 |
| Relics | 290 | 0 | 0 |

This table is a coverage gate, not a full behavior proof. It means every decompiled surface currently counted by `scripts/parity_reference_audit.py --direct-test-references --include-deprecated --code-implementation-references --show-missing` has a Python implementation mention and a direct test mention. Exact parity still depends on the deeper behavior and bridge validation tracked in [PARITY_GAPS.md](./PARITY_GAPS.md).

Latest local pass also added direct coverage for:

- Cards: `BALL_LIGHTNING`, `BARRAGE`, `BEAM_CELL`, `COLD_SNAP`, `COMPILE_DRIVER`

No new logic mismatch was found in this pass. The pass also made these Defect card factories accept `upgraded=True` directly, so upgraded parity tests can use the semantic factory names.

Latest local pass also added direct coverage for:

- Cards: `FIGHT_THROUGH`, `ICE_LANCE`, `REFRACT`

No new logic mismatch was found in this pass. The pass also made these card factories accept `upgraded=True` directly, so upgraded parity tests no longer need to route through `create_card`.

Latest local pass also added direct coverage for:

- Cards: `DEATHS_DOOR`, `NEUROSURGE`, `SENTRY_MODE`

This pass also exposed and fixed the following logic mismatches:

- `DeathsDoor`: reference-backed cards now expose the `Repeat` value through the effect field used by the Python implementation, so the repeat count is no longer an implicit fallback.
- `Neurosurge`: `NeurosurgePower` now maps into the effect field used by the Python implementation, so upgraded cards keep the original 3-power amount while only increasing energy.
- `SentryMode`: `SentryModePower` now maps into the effect field used by the Python implementation, so upgraded cards keep the original 1-power amount while only reducing cost.

The same pass added `scripts/audit_card_effect_vars.py`, which checks that card effects do not read `effect_vars` keys absent from the base or upgraded factory output.

Latest local pass also added direct coverage for:

- Cards: `PREP_TIME`

This pass also exposed and fixed the following logic mismatch:

- `PrepTime`: upgraded reference-backed cards now map `PrepTimePower+2` into the effect field actually used by the Python implementation, so `PrepTime+` grants 6 next-turn Vigor instead of 4.

Latest local pass also added direct coverage for:

- Cards: `AUTOMATION`, `KNOCKDOWN`, `ROLLING_BOULDER`

This pass also exposed and fixed the following logic mismatches:

- `Knockdown`: upgraded reference-backed cards now map `KnockdownPower+1` into the effect field actually used by the Python implementation, so `Knockdown+` applies multiplier 3 instead of 2.
- `RollingBoulder`: upgraded reference-backed cards now map `RollingBoulderPower+5` into the effect field actually used by the Python implementation, so `RollingBoulder+` starts at 10 damage instead of 5.

Latest local pass also added direct coverage for:

- Cards: `ANOINTED`

No new logic mismatch was found in this pass.

Latest local pass also added direct coverage for:

- Cards: `GANG_UP`

No new logic mismatch was found in this pass.

Latest local pass also added direct coverage for:

- Cards: `HIDDEN_GEM`, `HUDDLE_UP`, `IMPATIENCE`, `SCRAWL`

No new logic mismatch was found in this pass.

Latest local pass also added direct coverage for:

- Relics: `BLOOD_SOAKED_ROSE`, `ELECTRIC_SHRYMP`, `GNARLED_HAMMER`, `GOLDEN_PEARL`, `IRON_CLUB`, `LOOMING_FRUIT`, `MEAT_CLEAVER`, `NEOWS_TORMENT`, `NUTRITIOUS_OYSTER`, `PAELS_HORN`, `RINGING_TRIANGLE`, `SCREAMING_FLAGON`, `SLING_OF_COURAGE`, `TANXS_WHISTLE`, `VERY_HOT_COCOA`

This pass also exposed and fixed the following logic mismatch:

- `MeatCleaver`: rest sites now show `Cook` even when fewer than two cards can be removed, with the option disabled, matching the original `CookRestSiteOption` behavior.

Latest local pass also added direct coverage for:

- Cards: `CALTROPS`, `ENTRENCH`, `OUTMANEUVER`, `RELAX`, `WHISTLE`

Latest local pass also added direct coverage for:

- Cards: `BURY`, `CALCIFY_CARD`, `DEFY`, `DEMESNE`, `DEVOUR_LIFE_CARD`, `LETHALITY_CARD`, `SCOURGE`, `SHARED_FATE`, `SQUEEZE`, `TIMES_UP`

This pass also exposed and fixed the following logic mismatch:

- OstyAttack cards: missing Osty now blocks only `HighFive`; other Osty attack cards remain playable and simply do nothing, matching the original card-specific `IsPlayable` behavior.

Latest local pass also added direct coverage for:

- Cards: `CELESTIAL_MIGHT`, `CRESCENT_SPEAR`, `DEVASTATE`, `GAMMA_BLAST`, `GLITTERSTREAM`, `HEGEMONY`, `KNOW_THY_PLACE`, `LUNAR_BLAST`, `NEUTRON_AEGIS`, `PROPHESIZE`, `THE_SEALED_THRONE`

This pass also exposed and fixed the following logic mismatch:

- `Glitterstream`: its `BlockNextTurn` amount now exists in the card factory and goes through the normal block modifier pipeline before applying.

Latest local pass also added direct coverage for:

- Cards: `CATASTROPHE`, `ETERNAL_ARMOR`, `JACKPOT`, `PREP_TIME`, `PROWESS`, `SALVO`

Latest local pass also added direct coverage for:

- Cards: `BOOT_SEQUENCE`, `BULK_UP`, `DOUBLE_ENERGY`, `FUSION`, `GLASSWORK`, `LEAP`, `METEOR_STRIKE`, `MODDED`, `QUADCAST`, `SHADOW_SHIELD`, `SKIM`, `SYNTHESIS`, `UPROAR`

This pass also exposed and fixed the following logic mismatch:

- `Quadcast`: it now triggers the front orb three times without removing it, then removes it on the fourth evoke, matching the original.

Latest local pass also added direct coverage for:

- Cards: `ADAPTIVE_STRIKE`, `HELIX_DRILL`, `MOMENTUM_STRIKE`, `TESLA_COIL`, `VOLTAIC`

This pass also exposed and fixed the following logic mismatches:

- `AdaptiveStrike`: after dealing damage, it now adds a 0-cost copy of itself to the discard pile.
- `HelixDrill`: hit count now follows energy spent by the owner this turn, excluding the card's own cost while it is in play.
- `MomentumStrike`: after dealing damage, it now sets its own cost to 0 for the rest of combat.
- `TeslaCoil`: after its attack, it now triggers only Lightning orb passives against the card target instead of triggering every orb passive.
- `Voltaic`: channel count now follows the owner's Lightning channel history for the combat rather than current orb count.

Latest local pass also added direct coverage for:

- Cards: `ABRASIVE`, `ASSASSINATE`, `BOUNCING_FLASK`, `DASH`, `FLECHETTES`, `FLICK_FLACK`, `LEADING_STRIKE`, `MIRAGE`, `PREDATOR`, `RICOCHET`, `SHADOWMELD`, `SUPPRESS`, `UNTOUCHABLE`

This pass also exposed and fixed the following logic mismatch:

- `Ricochet`: base and upgraded hit counts now match the original 4 / 5 hits instead of being one hit short.

Latest local pass also added direct coverage for:

- Cards: `PILLAGE`, `PYRE`, `STAMPEDE_CARD`, `STONE_ARMOR`, `TAUNT`, `TREMBLE`, `UNMOVABLE`, `UNRELENTING`

This pass also exposed and fixed the following logic mismatches:

- `Pillage`: continuation now uses the actual card returned by the draw command, so draw-time effects that move an Attack out of hand, such as `Hellraiser`, do not stop the draw loop early.
- `Unmovable`: block doubling now applies to the owner's own card / move block and no longer doubles another player's card block.

Latest local pass also added direct coverage for:

- Cards: `BARRICADE_CARD`, `BEACON_OF_HOPE`, `BLUDGEON`, `CORRUPTION_CARD`, `DEMON_FORM_CARD`, `DEMONIC_SHIELD`, `FISTICUFFS`, `FLAME_BARRIER_CARD`, `GOLD_AXE`

This pass also exposed and fixed the following logic mismatch:

- `DemonicShield`: block granted to an ally now fires after-block-gained hooks for that ally, so follow-up effects like `BeaconOfHope` run like the original.
- `Fisticuffs`: block gained from attack damage now goes through the normal block modifier pipeline, so Dexterity, Frail, and similar block modifiers apply like the original.
- Colorless block cards now fire the after-block-gained hook, so `BeaconOfHope` shares block from `Finesse` and `Fisticuffs` like the original.

Previous local pass also added direct coverage for:

- Relics: `EMOTION_CHIP`, `GAMBLING_CHIP`, `GIRYA`, `JUZU_BRACELET`, `KUNAI`, `PAPER_KRANE`, `SHOVEL`, `SHURIKEN`, `SNECKO_SKULL`

This pass also exposed and fixed the following logic mismatches:

- `JuzuBracelet`: unknown rooms now blacklist `Monster` outcomes when resolving `?` rooms.
- `SneckoSkull`: the relic now participates in the power-amount-given pipeline, so owner-applied Poison correctly gains `+1`.
- `Girya`: after 3 lifts, the rest site no longer keeps surfacing `Lift`.
- `EmotionChip`: now tracks previous-round unblocked HP loss and re-triggers all orb passives on the next player turn.
- `GamblingChip`: round-1 discard-and-draw now uses a real pending hand-choice flow.
- `PaperKrane`: Weak damage reduction now matches the original multiplier path without float-floor drift.

The latest local pass also added direct coverage for:

- Relics: `CLOAK_CLASP`, `GHOST_SEED`, `INTIMIDATING_HELMET`, `IVORY_TILE`, `MEAT_ON_THE_BONE`, `POWER_CELL`, `RAINBOW_RING`, `RAZOR_TOOTH`

This pass also exposed and fixed the following logic mismatches:

- `GhostSeed`: starter `Strike` / `Defend` cards now actually gain `Ethereal` when combat starts.
- `RainbowRing`: it now only grants its `+1 Strength / +1 Dexterity` payoff once per turn.
- `RazorTooth`: played Attack / Skill cards now upgrade through the real combat upgrade path instead of calling a nonexistent card method.

This pass added direct coverage for:

- Cards: `ARMAMENTS`, `BURNING_PACT`, `HEADBUTT`, `TRUE_GRIT`, `WHIRLWIND`, `BACKSTAB`, `BLADE_DANCE`, `BURST`, `ESCAPE_PLAN`, `WRAITH_FORM`, `CHARGE_BATTERY`, `COOLHEADED`, `DUALCAST`, `LOOP_CARD`, `SUNDER`, `MASTER_OF_STRATEGY`, `MIND_BLAST`, `PANACHE_CARD`, `MIMIC`, `VOLLEY`, `GATHER_LIGHT`, `GLOW`, `MAKE_IT_SO`, `RADIATE`, `STARDUST`, `DRAIN_POWER`, `END_OF_DAYS`, `GLIMPSE_BEYOND`, `SEVERANCE`, `SOUL_STORM`, `BURN`, `VOID`, `REGRET`, `DEBT`, `FRANTIC_ESCAPE`, `NORMALITY`
- Events: `BrainLeech`, `RoomFullOfCheese`, `TeaMaster`, `Neow`, `WarHistorianRepy`, `DeprecatedEvent`, `DeprecatedAncientEvent`, `RelicTrader`, `SlipperyBridge`, `Symbiote`, `LostWisp`, `Reflections`, `TheLegendsWereTrue`, `SpiralingWhirlpool`, `StoneOfAllTime`, `TheFutureOfPotions`, `WaterloggedScriptorium`, `DrowningBeacon`, `GraveOfTheForgotten`, `HungryForMushrooms`, `InfestedAutomaton`, `SunkenStatue`, `TheArchitect`, `CrystalSphere`, `EndlessConveyor`, `FakeMerchant`, `WelcomeToWongos`, `FieldOfManSizedHoles`, `ColorfulPhilosophers`, `SunkenTreasury`, `TabletOfTruth`, `ThisOrThat`, `Wellspring`, `DollRoom`, `AbyssalBaths`, `Amalgamator`, `AromaOfChaos`, `ByrdonisNest`, `Orobas`, `SapphireSeed`, `SelfHelpBook`, `WoodCarvings`, `ZenWeaver`
- Relics: `AKABEKO`, `BAG_OF_MARBLES`, `BRONZE_SCALES`, `CHEMICAL_X`, `DATA_DISK`, `BAG_OF_PREPARATION`, `ORICHALCUM`, `MERCURY_HOURGLASS`, `GREMLIN_HORN`, `CRACKED_CORE`, `RING_OF_THE_DRAKE`, `INFUSED_CORE`, `PERMAFROST`, `RED_SKULL`, `FESTIVE_POPPER`, `VENERABLE_TEA_SET`, `HORN_CLEAT`, `KUSARIGAMA`, `LETTER_OPENER`, `NUNCHAKU`, `ORNAMENTAL_FAN`, `JOSS_PAPER`, `FROZEN_EGG`, `TOXIC_EGG`, `LIZARD_TAIL`, `MAW_BANK`, `SOZU`, `VELVET_CHOKER`, `BLOOD_VIAL`, `CENTENNIAL_PUZZLE`, `HAPPY_FLOWER`, `MEAL_TICKET`, `POTION_BELT`, `STRAWBERRY`, `VAJRA`, `GORGET`, `PARRYING_SHIELD`, `PANTOGRAPH`, `PAPER_PHROG`, `PETRIFIED_TOAD`, `RIPPLE_BASIN`, `SELF_FORMING_CLAY`, `TWISTED_FUNNEL`, `GOLD_PLATED_CABLES`, `ART_OF_WAR`, `CHARONS_ASHES`, `DEMON_TONGUE`, `MUMMIFIED_HAND`, `POCKETWATCH`, `TUNGSTEN_ROD`, `ARCANE_SCROLL`, `PRECARIOUS_SHEARS`, `BLACK_BLOOD`, `BOUND_PHYLACTERY`, `DIVINE_RIGHT`, `DIVINE_DESTINY`, `BONE_FLUTE`, `ODDLY_SMOOTH_STONE`, `STRIKE_DUMMY`, `BEATING_REMNANT`, `CAPTAINS_WHEEL`, `TOUGH_BANDAGES`, `THE_ABACUS`, `BOOMING_CONCH`, `EMPTY_CAGE`, `ALCHEMICAL_COFFER`, `HAND_DRILL`, `BELLOWS`, `BOWLER_HAT`, `ETERNAL_FEATHER`, `FUNERARY_MASK`, `GALACTIC_DUST`, `MINIATURE_CANNON`, `RED_MASK`, `BURNING_BLOOD`, `PHYLACTERY_UNBOUND`, `FENCING_MANUAL`, `PENDULUM`, `REGAL_PILLOW`, `TINY_MAILBOX`, `WAR_PAINT`, `BOOK_OF_FIVE_RINGS`, `CANDELABRA`, `PEN_NIB`, `LUCKY_FYSH`, `SPARKLING_ROUGE`, `TUNING_FORK`, `TINGSHA`, `VAMBRACE`, `SYMBIOTIC_VIRUS`, `BELT_BUCKLE`, `BRIMSTONE`, `BURNING_STICKS`, `GAME_PIECE`, `RUNIC_CAPACITOR`, `THE_BOOT`, `TOUCH_OF_OROBAS`, `UNCEASING_TOP`

This pass also exposed and fixed the following logic mismatches:

- `Escape Plan`: now draws first and only grants block if the drawn card is a Skill.
- `Dualcast`: now evokes the front orb twice with the correct first-without-dequeue / second-with-dequeue behavior.
- `Coolheaded`: now channels Frost before drawing.
- `Chemical X`: now feeds its X-value bonus into the engine's `energy_spent` path.
- `Gremlin Horn`: now actually triggers on enemy death and grants energy + draw.
- `SlipperyBridge.overcome`: now actually removes one random removable card.
- `Symbiote.kill_fire`: now uses a real pending card choice and transforms one selected card.
- `TheLegendsWereTrue.nab_map`: now actually adds `Spoils Map`; `find_exit` now returns a potion reward object.
- `TheFutureOfPotions`: now trades the selected potion and produces upgraded card rewards with rarity / type mapping.
- `WaterloggedScriptorium`: now handles sparse or empty enchant candidates without deadlocking the choice flow.
- `CrystalSphere.debt`: now actually adds `Debt` to the deck.
- `FieldOfManSizedHoles`: now has real gating, `resist` removal + `Normality`, and `enter` enchant choice flow.
- `WelcomeToWongos`: purchases now grant relics; `leave` now downgrades a random upgraded card.
- `DrowningBeacon.climb`: now actually grants `Fresnel Lens`.
- `GraveOfTheForgotten`: now actually adds `Decay` and applies the `Soul's Power` enchantment choice.
- `HungryForMushrooms`: `fragrant` no longer double-applies HP loss.
- `InfestedAutomaton`: now actually adds a random Power or a random 0-cost non-X card.
- `SunkenStatue.grab_sword`: now actually grants `Sword of Stone`.
- `TabletOfTruth`: `give_up` no longer heals, and `decipher` now performs the staged upgrades.
- `JossPaper`: now tracks exhausts per owner correctly and resolves ethereal-turn-end draw timing.
- `Kusarigama`, `ParryingShield`, and `Tingsha`: now use a valid random-enemy selector.
- `GoldPlatedCables`, `PaperPhrog`, and `PetrifiedToad`: now follow their intended uncommon-relic combat semantics.
- `CursedPearl`: deferred follow-up mode now queues only the curse while granting gold immediately.
- `MummifiedHand`: now applies temporary cost-0 without calling a nonexistent combat API.
- `HandDrill`: now detects real block breaks and applies Vulnerable correctly.
- `BeltBuckle`: now checks actual held potions from combat player state.
- `BurningSticks`: now uses a supported hand-clone path.
- `RunicCapacitor`: now falls back to orb-queue capacity when slot APIs are absent.
- `UnceasingTop`: no longer depends on missing `combat.in_play_phase`.
- `Reflections.touch`: now actually downgrades 2 upgraded cards and upgrades 4 other cards.
- `Reflections.shatter`: now duplicates the deck and adds `Bad Luck`.

Previously scoped blocker `NORMALITY` is now closed:

- `NORMALITY` is now enforced in `CombatState.can_play_card`, and has direct parity coverage in `tests/test_status_curse_card_effects_parity.py`.

## Current Remaining Backlog

These are the current exact remaining surfaces that still lack direct proof.

### Remaining Cards By Module

#### `sts2_env.cards.ironclad` (0)

All currently implemented Ironclad cards now have direct coverage.

#### `sts2_env.cards.silent` (0)

All currently implemented Silent cards now have direct coverage.

#### `sts2_env.cards.defect` (0)

All currently implemented Defect cards now have direct coverage.

#### `sts2_env.cards.colorless` (0)

All currently implemented Colorless cards now have direct coverage.

#### `sts2_env.cards.regent` (0)

All currently implemented Regent cards now have direct coverage.

#### `sts2_env.cards.necrobinder` (0)

All currently implemented Necrobinder cards now have direct coverage.

#### `sts2_env.cards.status` (0)

All currently implemented reference-backed status, curse, event, token, and quest cards now have direct coverage.

### Remaining Events By File

#### `sts2_env/events/act1.py` (0)

All currently implemented Act 1 events now have direct coverage.

#### `sts2_env/events/act2.py` (0)

All currently implemented Act 2 events now have direct coverage.

#### `sts2_env/events/act3.py` (0)

All currently implemented Act 3 events now have direct coverage.

#### `sts2_env/events/shared.py` (0)

All currently implemented shared events now have direct coverage.

### Remaining Relics (0)

All currently counted relic classes now have direct implementation and test references, including the deprecated save placeholder under the stricter audit.

## Baseline Snapshot

- Snapshot date: 2026-03-17
- Reference implementation: `decompiled/`
- Test snapshot used for this inventory:
  - [tests/test_combat_parity.py](../tests/test_combat_parity.py)
  - [tests/test_card_choice_parity.py](../tests/test_card_choice_parity.py)
  - [tests/test_silent_choice_parity.py](../tests/test_silent_choice_parity.py)
  - [tests/test_defect_choice_parity.py](../tests/test_defect_choice_parity.py)
  - [tests/test_colorless_parity.py](../tests/test_colorless_parity.py)
  - [tests/test_regent_parity.py](../tests/test_regent_parity.py)
  - [tests/test_necrobinder_parity.py](../tests/test_necrobinder_parity.py)
  - [tests/test_parity_helpers.py](../tests/test_parity_helpers.py)
  - [tests/test_events_shared_state_changes_parity.py](../tests/test_events_shared_state_changes_parity.py)
  - [tests/test_events_act2_state_changes_parity.py](../tests/test_events_act2_state_changes_parity.py)
  - [tests/test_relic_reward_and_card_reward_hooks_parity.py](../tests/test_relic_reward_and_card_reward_hooks_parity.py)
  - [tests/test_relic_rest_site_hooks_parity.py](../tests/test_relic_rest_site_hooks_parity.py)
  - [tests/test_shop_relic_hooks.py](../tests/test_shop_relic_hooks.py)
  - [tests/test_relic_shop_event_combat_reward_hooks_parity.py](../tests/test_relic_shop_event_combat_reward_hooks_parity.py)
  - [tests/test_combat_potion_action_space_parity.py](../tests/test_combat_potion_action_space_parity.py)
  - [tests/test_bridge_state_adapter.py](../tests/test_bridge_state_adapter.py)
- Verification status for the parity-focused suites above:
  - `uv run pytest -q ...`
  - Result: `270 passed in 0.29s`

## Counting Rules

### Cards

- Card totals come from the lazy registry returned by `sts2_env.cards.factory._factory_registry()`.
- This is stricter and broader than counting handwritten `make_*` functions because it also includes reference-backed cards exposed through the factory.
- A card is counted as "explicitly parity-covered" only if it appears in a targeted parity suite or in a decompiled-backed test docstring.

### Relics

- A relic is counted as "directly test-touched" if a test references it via:
  - `obtain_relic("...")`
  - `create_relic_by_name("...")`
  - `relics=[...]` when constructing combat state
- This is intentionally conservative. Indirect behavior might still be exercised elsewhere, but it is not counted unless the relic is named directly by a focused test.

### Events

- An event is counted as "directly covered" only if a focused event test instantiates it or drives it through `RunManager`.
- Generic run-flow tests are not counted unless the event itself is named.

## Summary

| Surface | Total | Directly Covered | Gap | Coverage |
| --- | ---: | ---: | ---: | ---: |
| Cards | 578 | 83 | 495 | 14.4% |
| Relics | 289 | 73 | 216 | 25.3% |
| Events | 68 | 12 | 56 | 17.6% |

## What This Means

The repository has meaningful parity depth in several targeted areas:

- combat turn flow and hook semantics
- card choice flows
- Regent and Necrobinder spot checks
- potion action decoding
- reward / shop / rest-site relic plumbing

But the proof surface is still sparse relative to the total implementation surface:

- Ironclad has no explicit card-by-card parity suite yet
- Silent and Defect still only have a small targeted subset covered
- Status / curse / event / quest cards are mostly uncovered
- most relics still lack direct named tests
- most events still lack focused tests

## Baseline Explicit Card Coverage

The original baseline directly parity-backed card set was:

```text
ACROBATICS, AFTERLIFE, ALCHEMIZE, BEACON_OF_HOPE, BEAT_DOWN, BEGONE, BIG_BANG, BLACK_HOLE,
BODYGUARD, BONE_SHARDS, BORROWED_TIME, BULWARK, CAPTURE_SPIRIT, CHARGE, CLASH,
CLEANSE, COMPACT, CONQUEROR, CONVERGENCE, COUNTDOWN_CARD, CRASH_LANDING,
DAGGER_THROW, DANSE_MACABRE, DEATH_MARCH, DECISIONS_DECISIONS, DIRGE,
DISCOVERY, DREDGE, EIDOLON, ENTHRALLED, FISTICUFFS, FLAK_CANNON, FURNACE, GLIMMER,
GOLD_AXE, GRAND_FINALE, GRAVE_WARDEN, GUARDS, HAND_OF_GREED, HAND_TRICK, HEIRLOOM_HAMMER,
HIDDEN_CACHE, HIDDEN_DAGGERS, HIGH_FIVE, HOLOGRAM, KNOCKOUT_BLOW, LARGESSE,
LEGION_OF_BONE, MANIFEST_AUTHORITY, NECRO_MASTERY_CARD, NIGHTMARE, ORBIT,
PALE_BLUE_DOT, PHOTON_CUT, PREPARED, PROTECTOR, PULL_AGGRO, PURITY, QUASAR,
RATTLE, REANIMATE, REFINE_BLADE, RESONANCE, SACRIFICE, SCAVENGE, SEANCE,
SECRET_TECHNIQUE, SECRET_WEAPON, SEEKING_EDGE, SOLAR_STRIKE, SPOILS_OF_BATTLE,
SPUR, SUMMON_FORTH, SURVIVOR, THE_HUNT, THE_SMITH, THINKING_AHEAD, TRANSFIGURE,
UNDEATH, VOID_FORM, WHITE_NOISE, WISH, WROUGHT_IN_WAR
```

Notes:

- `NIGHTMARE` is covered through `NightmarePower` snapshot behavior.
- `COUNTDOWN_CARD` and `NECRO_MASTERY_CARD` are the registered card ids behind the user-facing names `Countdown` and `NecroMastery`.

## Baseline Card Coverage Backlog By Module

Module-level counts in this baseline were derived from `sts2_env.cards.factory._factory_registry()`.

### `sts2_env.cards.ironclad`

- Baseline covered: `0 / 87`
- Baseline missing direct parity proof: `87 / 87`

```text
AGGRESSION_CARD, ANGER, ARMAMENTS, ASHEN_STRIKE, BARRICADE_CARD, BASH,
BATTLE_TRANCE, BLOODLETTING, BLOOD_WALL, BLUDGEON, BODY_SLAM, BRAND, BREAK,
BREAKTHROUGH, BULLY, BURNING_PACT, CASCADE, CINDER, COLOSSUS_CARD,
CONFLAGRATION, CORRUPTION_CARD, CRIMSON_MANTLE, CRUELTY_CARD,
DARK_EMBRACE_CARD, DEFEND_IRONCLAD, DEMONIC_SHIELD, DEMON_FORM_CARD,
DISMANTLE, DOMINATE, DRUM_OF_BATTLE_CARD, EVIL_EYE, EXPECT_A_FIGHT, FEED,
FEEL_NO_PAIN_CARD, FIEND_FIRE, FIGHT_ME, FLAME_BARRIER_CARD,
FORGOTTEN_RITUAL, GRAPPLE, HAVOC, HEADBUTT, HELLRAISER_CARD, HEMOKINESIS,
HOWL_FROM_BEYOND, IMPERVIOUS, INFERNAL_BLADE, INFERNO_CARD, INFLAME,
IRON_WAVE, JUGGERNAUT_CARD, JUGGLING_CARD, MANGLE, MOLTEN_FIST, OFFERING,
ONE_TWO_PUNCH_CARD, PACTS_END, PERFECTED_STRIKE, PILLAGE, POMMEL_STRIKE,
PRIMAL_FORCE, PYRE, RAGE_CARD, RAMPAGE, RUPTURE_CARD, SECOND_WIND,
SETUP_STRIKE_CARD, SHRUG_IT_OFF, SPITE, STAMPEDE_CARD, STOKE, STOMP,
STONE_ARMOR, STRIKE_IRONCLAD, SWORD_BOOMERANG, TANK_CARD, TAUNT,
TEAR_ASUNDER, THRASH, THUNDERCLAP, TREMBLE, TRUE_GRIT, TWIN_STRIKE,
UNMOVABLE, UNRELENTING, UPPERCUT, VICIOUS_CARD, WHIRLWIND
```

### `sts2_env.cards.silent`

- Baseline covered: `9 / 88`
- Baseline missing direct parity proof: `79 / 88`

```text
ABRASIVE, ACCELERANT, ACCURACY_CARD, ADRENALINE, AFTERIMAGE_CARD,
ANTICIPATE, ASSASSINATE, BACKFLIP, BACKSTAB, BLADE_DANCE, BLADE_OF_INK,
BLUR_CARD, BOUNCING_FLASK, BUBBLE_BUBBLE, BULLET_TIME, BURST,
CALCULATED_GAMBLE, CLOAK_AND_DAGGER, CORROSIVE_WAVE, DAGGER_SPRAY, DASH,
DEADLY_POISON, DEFEND_SILENT, DEFLECT, DODGE_AND_ROLL, ECHOING_SLASH,
ENVENOM_CARD, ESCAPE_PLAN, EXPERTISE, EXPOSE, FAN_OF_KNIVES_CARD,
FINISHER, FLANKING, FLECHETTES, FLICK_FLACK, FOLLOW_THROUGH, FOOTWORK,
HAZE, INFINITE_BLADES_CARD, KNIFE_TRAP, LEADING_STRIKE, LEG_SWEEP,
MALAISE, MASTER_PLANNER, MEMENTO_MORI, MIRAGE, MURDER, NEUTRALIZE,
NOXIOUS_FUMES_CARD, OUTBREAK_CARD, PHANTOM_BLADES_CARD, PIERCING_WAIL,
PINPOINT, POISONED_STAB, POUNCE, PRECISE_CUT, PREDATOR, REFLEX, RICOCHET,
SERPENT_FORM_CARD, SHADOWMELD, SHADOW_STEP, SKEWER, SLICE, SNAKEBITE,
SNEAKY_CARD, SPEEDSTER_CARD, STORM_OF_STEEL, STRANGLE, STRIKE_SILENT,
SUCKER_PUNCH, SUPPRESS, TACTICIAN, TOOLS_OF_THE_TRADE, TRACKING,
UNTOUCHABLE, UP_MY_SLEEVE, WELL_LAID_PLANS, WRAITH_FORM
```

### `sts2_env.cards.defect`

- Baseline covered: `5 / 88`
- Baseline missing direct parity proof: `83 / 88`

```text
ADAPTIVE_STRIKE, ALL_FOR_ONE, BALL_LIGHTNING, BARRAGE, BEAM_CELL,
BIASED_COGNITION_CARD, BOOST_AWAY, BOOT_SEQUENCE, BUFFER_CARD, BULK_UP,
CAPACITOR, CHAOS, CHARGE_BATTERY, CHILL, CLAW, COLD_SNAP, COMPILE_DRIVER,
CONSUMING_SHADOW, COOLANT, COOLHEADED, CREATIVE_AI_CARD, DARKNESS_CARD,
DEFEND_DEFECT, DEFRAGMENT, DOUBLE_ENERGY, DUALCAST, ECHO_FORM_CARD,
ENERGY_SURGE, FERAL, FIGHT_THROUGH, FOCUSED_STRIKE_CARD, FTL, FUSION,
GENETIC_ALGORITHM, GLACIER, GLASSWORK, GO_FOR_THE_EYES, GUNK_UP, HAILSTORM,
HELIX_DRILL, HOTFIX, HYPERBEAM, ICE_LANCE, IGNITION, ITERATION_CARD, LEAP,
LIGHTNING_ROD, LOOP_CARD, MACHINE_LEARNING_CARD, METEOR_STRIKE, MODDED,
MOMENTUM_STRIKE, MULTI_CAST, NULL_CARD, OVERCLOCK, QUADCAST, RAINBOW,
REBOOT, REFRACT, ROCKET_PUNCH, SCRAPE, SHADOW_SHIELD, SHATTER, SIGNAL_BOOST,
SKIM, SMOKESTACK, SPINNER_CARD, STORM_CARD, STRIKE_DEFECT, SUBROUTINE,
SUNDER, SUPERCRITICAL, SWEEPING_BEAM, SYNCHRONIZE, SYNTHESIS, TEMPEST,
TESLA_COIL, THUNDER_CARD, TRASH_TO_TREASURE, TURBO, UPROAR, VOLTAIC, ZAP
```

### `sts2_env.cards.colorless`

- Baseline covered: `11 / 64`
- Baseline missing direct parity proof: `53 / 64`

```text
ANOINTED, AUTOMATION, BELIEVE_IN_YOU, BOLAS, CALAMITY_CARD,
CATASTROPHE, COORDINATE_CARD, DARK_SHACKLES, DRAMATIC_ENTRANCE, ENTROPY,
EQUILIBRIUM, ETERNAL_ARMOR, FASTEN, FINESSE, FLASH_OF_STEEL,
GANG_UP, HIDDEN_GEM, HUDDLE_UP, IMPATIENCE, INTERCEPT_CARD,
JACKPOT, JACK_OF_ALL_TRADES, KNOCKDOWN, LIFT, MASTER_OF_STRATEGY,
MAYHEM_CARD, MIMIC, MIND_BLAST, NOSTALGIA_CARD, OMNISLICE, PANACHE_CARD,
PANIC_BUTTON, PREP_TIME, PRODUCTION, PROLONG, PROWESS, RALLY, REND,
RESTLESSNESS, ROLLING_BOULDER, SALVO, SCRAWL, SEEKER_STRIKE, SHOCKWAVE,
SPLASH, STRATAGEM, TAG_TEAM, THE_BOMB_CARD, THE_GAMBIT, THRUMMING_HATCHET,
ULTIMATE_DEFEND, ULTIMATE_STRIKE, VOLLEY
```

### `sts2_env.cards.regent`

- Baseline covered: `30 / 88`
- Baseline missing direct parity proof: `58 / 88`

```text
ALIGNMENT, ARSENAL, ASTRAL_PULSE, BEAT_INTO_SHAPE, BOMBARDMENT, BUNDLE_OF_JOY,
CELESTIAL_MIGHT, CHILD_OF_THE_STARS, CLOAK_OF_STARS, COLLISION_COURSE, COMET,
COSMIC_INDIFFERENCE, CRESCENT_SPEAR, CRUSH_UNDER, DEFEND_REGENT, DEVASTATE,
DYING_STAR, FALLING_STAR, FOREGONE_CONCLUSION, GAMMA_BLAST, GATHER_LIGHT,
GENESIS, GLITTERSTREAM, GLOW, GUIDING_STAR, HAMMER_TIME, HEAVENLY_DRILL,
HEGEMONY, I_AM_INVINCIBLE, KINGLY_KICK, KINGLY_PUNCH, KNOW_THY_PLACE,
LUNAR_BLAST, MAKE_IT_SO, METEOR_SHOWER, MONARCHS_GAZE_CARD, MONOLOGUE_CARD,
NEUTRON_AEGIS, PARRY_CARD, PARTICLE_WALL, PATTER, PILLAR_OF_CREATION,
PROPHESIZE, RADIATE, REFLECT_CARD, ROYALTIES_CARD, ROYAL_GAMBLE, SEVEN_STARS,
SHINING_STRIKE, SPECTRUM_SHIFT, STARDUST, STRIKE_REGENT, SUPERMASSIVE,
SWORD_SAGE, TERRAFORMING, THE_SEALED_THRONE, TYRANNY_CARD, VENERATE
```

### `sts2_env.cards.necrobinder`

- Baseline covered: `28 / 88`
- Baseline missing direct parity proof: `60 / 88`

```text
BANSHEES_CRY, BLIGHT_STRIKE, BURY, CALCIFY_CARD, CALL_OF_THE_VOID,
DEATHBRINGER, DEBILITATE_CARD, DEFEND_NECROBINDER, DEFILE, DEFY,
DELAY, DEMESNE, DEVOUR_LIFE_CARD, DRAIN_POWER, END_OF_DAYS,
ENFEEBLING_TOUCH, ERADICATE, FEAR, FETCH, FLATTEN, FORBIDDEN_GRIMOIRE,
FRIENDSHIP, GLIMPSE_BEYOND, GRAVEBLAST, HANG, HAUNT, INVOKE, LETHALITY_CARD,
MELANCHOLY, MISERY, NEGATIVE_PULSE, NO_ESCAPE, OBLIVION,
PAGESTORM, PARSE, POKE, PULL_FROM_BELOW, PUTREFY, REAP, REAPER_FORM, REAVE,
RIGHT_HAND_HAND, SCOURGE, SCULPTING_STRIKE, SEVERANCE,
SHARED_FATE, SHROUD, SIC_EM, SLEIGHT_OF_FLESH, SNAP, SOUL_STORM, SOW,
SPIRIT_OF_ASH, SQUEEZE, STRIKE_NECROBINDER, THE_SCYTHE, TIMES_UP, UNLEASH,
VEILPIERCER, WISP
```

### `sts2_env.cards.status`

- Baseline covered: `3 / 75`
- Baseline missing direct parity proof: `72 / 75`

```text
APOTHEOSIS, APPARITION, ASCENDERS_BANE, BAD_LUCK, BECKON, BRIGHTEST_FLAME,
BURN, BYRDONIS_EGG, BYRD_SWOOP, CALTROPS, CLUMSY, CURSE_OF_THE_BELL, DAZED,
DEBRIS, DEBT, DECAY, DISINTEGRATION, DISTRACTION, DOUBT, DUAL_WIELD,
ENLIGHTENMENT, ENTRENCH, EXTERMINATE, FEEDING_FRENZY_CARD, FOLLY,
FRANTIC_ESCAPE, FUEL, GIANT_ROCK, GREED, GUILTY, HELLO_WORLD_CARD,
INFECTION, INJURY, LANTERN_KEY, LUMINESCE, MAD_SCIENCE, MAUL, METAMORPHOSIS,
MIND_ROT, MINION_DIVE_BOMB, MINION_SACRIFICE, MINION_STRIKE, NEOWS_FURY,
NORMALITY, OUTMANEUVER, PAIN, PARASITE, PECK, POOR_SLEEP, REBOUND, REGRET,
RELAX, RIP_AND_TEAR, SHAME, SHIV, SLIMED, SLOTH_STATUS, SOOT, SOUL,
SOVEREIGN_BLADE, SPOILS_MAP, SPORE_MIND, SQUASH, STACK, SWEEPING_GAZE,
TORIC_TOUGHNESS, TOXIC, VOID, WASTE_AWAY, WHISTLE, WOUND, WRITHE
```

## Baseline Direct Event Coverage

The original baseline focused event tests covered only the following event models:

```text
BattlewornDummy, Bugslayer, JungleMazeAdventure, LuminousChoir, MorphicGrove,
PotionCourier, RanwidTheElder, RoundTeaParty, TrashHeap, Trial, UnrestSite,
WhisperingHollow
```

## Baseline Event Coverage Backlog By File

### `sts2_env/events/act1.py`

- Baseline covered: `0 / 4`
- Baseline missing direct proof: `4 / 4`

```text
BrainLeech, RoomFullOfCheese, TheLegendsWereTrue, TeaMaster
```

### `sts2_env/events/act2.py`

- Baseline covered: `6 / 19`
- Baseline missing direct proof: `13 / 19`

```text
CrystalSphere, DollRoom, EndlessConveyor, FakeMerchant, FieldOfManSizedHoles,
RelicTrader, SlipperyBridge, SpiralingWhirlpool, StoneOfAllTime, Symbiote,
TheFutureOfPotions, WaterloggedScriptorium, WelcomeToWongos
```

### `sts2_env/events/act3.py`

- Baseline covered: `0 / 5`
- Baseline missing direct proof: `5 / 5`

```text
TheArchitect, WarHistorianRepy, Neow, DeprecatedEvent, DeprecatedAncientEvent
```

### `sts2_env/events/shared.py`

- Baseline covered: `6 / 40`
- Baseline missing direct proof: `34 / 40`

```text
AbyssalBaths, Amalgamator, AromaOfChaos, ByrdonisNest, ColorfulPhilosophers,
ColossalFlower, Darv, DenseVegetation, DoorsOfLightAndDark, DrowningBeacon,
GraveOfTheForgotten, HungryForMushrooms, InfestedAutomaton, LostWisp,
Nonupeipe, Orobas, Pael, PunchOff, Reflections, SapphireSeed, SelfHelpBook,
SpiritGrafter, SunkenStatue, SunkenTreasury, TabletOfTruth, Tanx, Tezcatara,
TheLanternKey, ThisOrThat, TinkerTime, Vakuu, Wellspring, WoodCarvings,
ZenWeaver
```

## Current Direct Relic Coverage

`scripts/parity_reference_audit.py --direct-test-references --include-deprecated --code-implementation-references --show-missing` currently reports all 290 counted relic classes with implementation and direct-test references.

The older uncovered-relic buckets have been removed from this live backlog because they became stale after the focused relic parity suites were added. Relic exactness should still be judged by the behavior-specific tests and by the remaining exact-parity blockers in [PARITY_GAPS.md](./PARITY_GAPS.md), not by direct name coverage alone.

## Recommended Order For Closing The Remaining Risk

1. Keep using the direct-reference audit as the coverage gate before claiming a surface has no named gaps.
2. Expand behavior-specific tests when a decompiled hook has nontrivial timing, owner-scope, RNG, reward, shop, or bridge semantics.
3. After the Python-side proof surface stays green, re-run bridge replay and live smoke testing.

## Interpretation Guardrails

- This backlog is about missing proof, not necessarily missing implementation.
- A surface can be correctly implemented and still appear here.
- Exact parity should only be claimed once the proof surface is broad enough that remaining untested behavior is clearly unreachable or mechanically trivial.
