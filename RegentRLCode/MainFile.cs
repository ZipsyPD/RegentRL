using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using System.Collections.Generic;

using Godot;
using HarmonyLib;

using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.GameActions;
using MegaCrit.Sts2.Core.Modding;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.MonsterMoves.Intents;

namespace RegentRL.RegentRLCode;

//You're recommended but not required to keep all your code in this package and all your assets in the RegentRL folder.
[ModInitializer(nameof(Initialize))]
public partial class MainFile : Node
{
    public const string ModId = "RegentRL"; //At the moment, this is used only for the Logger and harmony names.

    // Enable only when explicity testing autonomous combat actions
    private const bool AutoPlayTestEnabled = false;

    // Prevent the test from submitting more than one card per combat
    private static bool _autoPlayTestSubmitted;

    public static MegaCrit.Sts2.Core.Logging.Logger Logger { get; } = new(ModId, MegaCrit.Sts2.Core.Logging.LogType.Generic);

    // Retain the active combat state for extracting observations after actions finish
    private static CombatState? _currentCombatState;

    // Most recent combat snapshot; serves as the "before" state for a transition
    private static CombatObservation? _lastObservation;

    // Completed card actions waiting for a shared post-batch observation
    private static readonly List<PlayCardAction> _batchCardActions = new();

    // Indicates that the player ended their turn and we are waiting for the next turn
    private static bool _awaitingNextTurn;

    // MOst recently constructed structured transition
    private static CombatTransition? _lastTransition;

    // Tracks whether the CombatWon fired for this encounter.
    // Prevents CombatEnded from treating victories as defeats
    private static bool _combatWasWon;

    //------------------------------------------------------------
    // Mod Initialization
    //------------------------------------------------------------

    public static void Initialize()
    {
        var assembly = Assembly.GetExecutingAssembly();

        //If you want to use scripts defined in your mod for Godot scenes, uncomment the following line.
        //Godot.Bridge.ScriptManagerBridge.LookupScriptsInAssembly(assembly);
     
        Harmony harmony = new(ModId);
        harmony.PatchAll(assembly);

        Logger.Info("RegentRL initialized successfully!");

        CombatManager.Instance.CombatSetUp += OnCombatSetUp;
        CombatManager.Instance.CombatBegan += OnCombatBegan;
        CombatManager.Instance.TurnStarted += OnTurnStarted;

        // Combat termination subscriptions
        CombatManager.Instance.CombatWon += OnCombatWon;
        CombatManager.Instance.CombatEnded += OnCombatEnded;
    }

    //------------------------------------------------------------
    // Combat Event Handlers
    //------------------------------------------------------------

    private static void OnCombatSetUp(CombatState state)
    {
        Logger.Info(
                $"Combat setup: {state.Encounter?.Id.Entry}"
                );

        // Clear state from the previous combat to avoid mixing transitions
        // across different encounters
        _batchCardActions.Clear();
        _lastObservation = null;
        _currentCombatState = null;
        _awaitingNextTurn = false;
        _lastTransition = null;
        _combatWasWon = false;
        _autoPlayTestSubmitted = false;

        // Subscribe to this run's ActionExecutor, which processes GameActions
        // Remove the handler first to prevent duplicate subscribes
        RunManager.Instance.ActionExecutor.AfterActionExecuted -= OnActionExecuted;
        RunManager.Instance.ActionExecutor.AfterActionExecuted += OnActionExecuted;
        Logger.Info(
                $"Subscribed executor ID: " +
                $"{RuntimeHelpers.GetHashCode(RunManager.Instance.ActionExecutor)}"
                );
    }

    private static void OnCombatBegan(CombatState state)
    {
        Logger.Info(
                $"Combat began! Enemies: {state.Enemies.Count()}"
                );
    }

    private static void OnCombatWon(CombatRoom room)
    {
        Logger.Info("COMBAT WON EVENT");
        if (_currentCombatState != null && _currentCombatState.Players.Count > 0)
        {
            var player = _currentCombatState.Players[0];

            Logger.Info(
                    $"TERMINAL STATE TEST: " +
                    $"HP {player.Creature.CurrentHp}, " +
                    $"Enemies remaining {_currentCombatState.Enemies.Count(e => e.IsAlive)}, " +
                    $"Pending card actions {_batchCardActions.Count}"
                    );
            
            if (_lastObservation != null)
            {
                Logger.Info(
                        $"TERMINAL BASELINE: " +
                        $"Turn {_lastObservation.Turn}, " +
                        $"HP {_lastObservation.Player.Hp}, " +
                        $"Energy {_lastObservation.Player.Energy}, " +
                        $"Awaiting next turn: {_awaitingNextTurn}"
                        );
            }
        }

        // Set to win
        _combatWasWon = true;

        if (_currentCombatState != null && _lastObservation != null)
        {
            var observation = CombatObservationExtractor.Extract(
                    _currentCombatState,
                    _currentCombatState.Players[0]
                    );

            _lastTransition = new CombatTransition
            {
                Before = _lastObservation,
                After = observation,
                Terminal = true,
                Outcome = "Win",
                EndedTurn = _awaitingNextTurn,
                Actions = _batchCardActions.Select(card => new CombatActionObservation
                        {
                        Type = "PlayCard",
                        CardId = card.CardModelId.Entry,
                        TargetId = card.TargetId
                        }).ToList()
            };

            if (_awaitingNextTurn)
            {
                _lastTransition.Actions.Add(new CombatActionObservation
                        {
                        Type = "EndTurn"
                        });
            }

            Logger.Info(
                    $"TERMINAL TRANSITION CREATED: " +
                    $"Outcome {_lastTransition.Outcome}, " +
                    $"Actions {_lastTransition.Actions.Count}, " +
                    $"HP {_lastTransition.Before.Player.Hp} -> {_lastTransition.After.Player.Hp}"
                    );

            // The terminal transition already contains the completed card actions.
            // Do not carry them into any later transition
            _batchCardActions.Clear();
            _awaitingNextTurn = false;
        }
    }

    private static void OnCombatEnded(CombatRoom room)
    {
        Logger.Info("COMBAT ENDED EVENT");
        if (!_combatWasWon && _currentCombatState != null &&
                _currentCombatState.Players.Count > 0)
        {
            var player = _currentCombatState.Players[0];

            Logger.Info(
                    $"DEFEAT STATE TEST: " +
                    $"HP {player.Creature.CurrentHp}, " +
                    $"IsDead {player.Creature.IsDead}, " +
                    $"Pending card actions {_batchCardActions.Count}, " +
                    $"Awaiting next turn {_awaitingNextTurn}, " +
                    $"Has baseline {_lastObservation != null}"    
                    );

            if (player.Creature.IsDead && _lastObservation != null)
            {
                var observation = CombatObservationExtractor.Extract(
                        _currentCombatState,
                        player
                        );

                _lastTransition = new CombatTransition
                {
                    Before = _lastObservation,
                    After = observation,
                    Terminal = true,
                    Outcome = "Loss",
                    EndedTurn = _awaitingNextTurn,
                    Actions = _batchCardActions.Select(card => new CombatActionObservation
                            {
                            Type = "PlayCard",
                            CardId = card.CardModelId.Entry,
                            TargetId = card.TargetId
                            }).ToList()
                };

                if (_awaitingNextTurn)
                {
                    _lastTransition.Actions.Add(new CombatActionObservation
                            {
                            Type = "EndTurn"
                            });
                }

                Logger.Info(
                        $"TERMINAL TRANSITION CREATED: " +
                        $"Outcome {_lastTransition.Outcome}, " +
                        $"Actions {_lastTransition.Actions.Count}, " +
                        $"HP {_lastTransition.Before.Player.Hp} -> {_lastTransition.After.Player.Hp}"
                        );

                _batchCardActions.Clear();
                _awaitingNextTurn = false;
            }
        }
    }

    private static void OnTurnStarted(CombatState state)
    {
        // Only observe the player's turn. 
        if (state.CurrentSide != CombatSide.Player)
        {
            return;
        }

        if (state.Players.Count == 0)
        {
            Logger.Info("No players found!");
            return;
        }

        _currentCombatState = state;

        // RegentRL currently supports single-player
        Player player = state.Players[0];

        // Player state: HP, block, and active powers
        var creature = player.Creature;

        foreach (var power in creature.Powers)
        {
            Logger.Info(
                    $"Regent Power: {power.Id.Entry}, Amount: {power.Amount}"
                    );
        }

        Logger.Info(
                $"Regent HP: {creature.CurrentHp}/{creature.MaxHp}"
                );

        Logger.Info(
                $"Regent Block: {creature.Block}"
                );

        // Enemy state: HP, block, powers, and visible intents
        foreach (var enemy in state.Enemies)
        {
            Logger.Info(
                    $"Enemy: {enemy.Name} " +
                    $"(ID: {enemy.CombatId}) " +
                    $"HP: {enemy.CurrentHp}/{enemy.MaxHp} " +
                    $"Block: {enemy.Block}"
                    );

            foreach (var power in enemy.Powers)
            {
                Logger.Info(
                        $" Enemy Power: {power.Id.Entry}, Amount: {power.Amount}"
                        );
            }

            if (enemy.Monster != null)
            {
                foreach (var intent in enemy.Monster.NextMove.Intents)
                {
                    Logger.Info(
                            $" Intent Type: {intent.IntentType}"
                            );

                    if (intent is AttackIntent attack)
                    {
                        int damage = attack.GetSingleDamage(
                                state.Players.Select(p => p.Creature),
                                enemy
                                );

                        Logger.Info(
                                $" Attack Intent: {damage} x {attack.Repeats}"
                                );
                    }
                }
            }
        }

        // Validate the player's combat state
        // before extracting observations
        PlayerCombatState? combat = player.PlayerCombatState;

        if (combat == null)
        {
            Logger.Info("Player combat state unavailable!");
            return;
        }

        // Convert STS2's combat state into RegentRL structured observation
        var observation = CombatObservationExtractor.Extract(state, player);

        // If an end turn action was observed, compare the previous player
        // decision state with the next turn's state after enemy-turn processing
        // This captures the combined effects of enemy actions and delayed effects.
        if (_awaitingNextTurn && _lastObservation != null)
        {
            Logger.Info(
                    $"END TURN TRANSITION: " +
                    $"Turn {_lastObservation.Turn} -> {observation.Turn}, " +
                    $"HP {_lastObservation.Player.Hp} -> {observation.Player.Hp}, " +
                    $"Energy {_lastObservation.Player.Energy} -> {observation.Player.Energy}, " +
                    $"Stars {_lastObservation.Player.Stars} -> {observation.Player.Stars}"
                    );
        }

        _awaitingNextTurn = false;
        // The new snapshot becomes the baseline for subsequent card transitions
        _lastObservation = observation;

        Logger.Info(
                $"Observation: Turn {observation.Turn}, " +
                $"HP {observation.Player.Hp}/{observation.Player.MaxHp}, " +
                $"Energy {observation.Player.Energy}/{observation.Player.MaxEnergy}, " +
                $"Stars {observation.Player.Stars}"
                );

        foreach (var power in observation.Player.Powers)
        {
            Logger.Info(
                    $"Observed Regent Power: {power.Id}, Amount: {power.Amount}"
                    );
        }

        // Verify extracted enemy information against the raw game state
        foreach (var enemy in observation.Enemies)
        {
            Logger.Info(
                    $"Observed Enemy: {enemy.Name}, " +
                    $"ID: {enemy.CombatId}, " +
                    $"HP: {enemy.Hp}/{enemy.MaxHp}, " +
                    $"Block: {enemy.Block}"
                    );

            foreach (var power in enemy.Powers)
            {
                Logger.Info(
                        $"Observed Power: {power.Id}, Amount: {power.Amount}"
                        );
            }

            foreach (var intent in enemy.Intents)
            {
                Logger.Info($"Observed Intent: {intent.Type}");

                if (intent.DamagePerHit.HasValue && intent.Hits.HasValue)
                {
                    Logger.Info(
                            $" Observed Attack Intent: " +
                            $"{intent.DamagePerHit.Value} x {intent.Hits.Value}"
                            );
                }
            }
        }

        // Hand state: Card metadata, resource costs, and legal targets
        for (int i = 0; i < combat.Hand.Cards.Count; i++)
        {
            var card = combat.Hand.Cards[i];

            Logger.Info(
                    $"Hand[{i}]: {card.Id.Entry}, " +
                    $"Upgrade: {card.CurrentUpgradeLevel}, " +
                    $"Star Cost: {card.CurrentStarCost}, " +
                    $"Target Type: {card.TargetType}, " +
                    $"Playable: {card.CanPlay()}, " +
                    $"No-target legal: {card.CanPlayTargeting(null)}, " +
                    $"Energy Cost: {card.EnergyCost.GetAmountToSpend()}"
                    );

            if (card.CanPlay())
            {
                foreach (var enemy in state.Enemies)
                {
                    Logger.Info(
                            $" Target {enemy.CombatId} ({enemy.Name}): " +
                            $"{card.CanPlayTargeting(enemy)}"
                            );
                }
            }
        }

        // Verify cards extracted into RegentRl's observation
        Logger.Info($"Observed hand count: {observation.Hand.Count}");
        foreach (var card in observation.Hand)
        {
            Logger.Info(
                    $"Observed Hand[{card.HandIndex}]: {card.Id}, " +
                    $"Upgrade: {card.UpgradeLevel}, " +
                    $"Star Cost: {card.StarCost}, " +
                    $"Target Type: {card.TargetType}, " +
                    $"Playable: {card.Playable}, " +
                    $"No-target legal: {card.NoTargetLegal}, " +
                    $"Energy Cost: {card.EnergyCost}"
                    );

            foreach (var targetId in card.LegalEnemyTargets)
            {
                Logger.Info($" Observed Legal Target: {targetId}");
            }
        }

        if (AutoPlayTestEnabled && !_autoPlayTestSubmitted)
        {
            var defend = combat.Hand.Cards.FirstOrDefault(card =>
                    card.Id.Entry == "DEFEND_REGENT" &&
                    card.CanPlay() &&
                    card.CanPlayTargeting(null)
                    );

            if (defend != null)
            {
                _autoPlayTestSubmitted = true;

                Logger.Info("AUTO-PLAY TEST: Submitting DEFEND_REFENT");

                RunManager.Instance.ActionQueueSynchronizer.RequestEnqueue(
                        new PlayCardAction(defend, null)
                        );
            }
        }
    }

    // Temporary decision policy.
    // Eventually will ask the Python RL agent what to do. 

    // Called after each GameAction executes.
    // TRacks played cards and detecs when the player requests to end 
    // their turn
    private static void OnActionExecuted(GameAction action)
    {
        Logger.Info(
                $"Action finished: {action.GetType().Name}, " +
                $"Executor running: {RunManager.Instance.ActionExecutor.IsRunning}, " +
                $"Queue Empty: {RunManager.Instance.ActionQueueSet.IsEmpty}"
                );
        
        // Makrs the player ready to end their turn.
        // The actual enemy turn happens later so wait for the next
        // Turn Started event. 
        if (action is EndPlayerTurnAction)
        {
            _awaitingNextTurn = true;
            Logger.Info("END TURN ACTION FINISHED");
        }

        if (action is PlayCardAction cardAction)
        {
            // Preserve every completed card action instead of overwriting the last one.
            // Rapidly played cards may execute in the same action batch. 
            _batchCardActions.Add(cardAction);

            Logger.Info(
                    $"PLAYED CARD: {cardAction.CardModelId.Entry}, " +
                    $"Target ID: {cardAction.TargetId?.ToString() ?? "None"}, " +
                    $"Player ID: {cardAction.Player.NetId}"
                    );
        }

        if (action is PlayCardAction)
        {
            // Delay extracting the next observation while other actions are queued.
            // This avoids duplicate observations for the multi-card batches being tested
            // Queue emptiness alone is not full synchronization though
            if (!RunManager.Instance.ActionQueueSet.IsEmpty)
            {
                Logger.Info("More queued actions; waiting for batch completion.");
                return;
            }

            // Capture the combat identity before starting asynchronous work.
            var combatId = CombatManager.Instance.CurrentCombatId;
            _ = LogAfterExecutorFinishes(combatId);
        }
    }

    private static async Task LogAfterExecutorFinishes(CombatId? combatId)
    {
        // Wait for the action executor to finish its current processing.
        // This is asynchronous and does not necessarily mean even combat
        // lifecycle event or delayed effect has completed.
        await RunManager.Instance.ActionExecutor.FinishedExecutingActions();

        // The callback may resume after its original combat has ended
        // Never allow it to observe or modify a different combat
        if (!CombatManager.Instance.IsCurrentLiveCombat(combatId))
        {
            Logger.Info("Skipping stale post-action callback.");
            return;
        }

        Logger.Info(
                $"Executor finished! " + 
                $"Running: {RunManager.Instance.ActionExecutor.IsRunning}, " +
                $"Queue Empty: {RunManager.Instance.ActionQueueSet.IsEmpty}"
                );

        // Avoid extracting an ordinary player decision state after combat ends
        // or when the game is no longer in the player's phase
        if (!CombatManager.Instance.IsInProgress)
            return;

        var state = _currentCombatState;
        if (state == null || state.CurrentSide != CombatSide.Player)
            return;

        var observation = CombatObservationExtractor.Extract(
                state,
                state.Players[0]
                );

        if (_lastObservation != null && _batchCardActions.Count > 0)
        {
            // Construct a structured transition from the previous observation,
            // all completed cards in this batch, and the resulting observation
            // For now, this is a batch and not one decision though. 
            _lastTransition = new CombatTransition
            {
                Before = _lastObservation,
                After = observation,
                EndedTurn = false,
                Actions = _batchCardActions.Select(card => new CombatActionObservation
                        {
                        Type = "PlayCard",
                        CardId = card.CardModelId.Entry,
                        TargetId = card.TargetId
                        }).ToList()
            };

            Logger.Info(
                    $"STRUCTURED TRANSITION CREATED: " +
                    $"{_lastTransition.Actions.Count} actions, " +
                    $"Turn {_lastTransition.Before.Turn} -> {_lastTransition.After.Turn}"
                    );
            string actions = string.Join(", ",
                    _batchCardActions.Select(card =>
                        $"{card.CardModelId.Entry} -> Target {card.TargetId?.ToString() ?? "None"}"
                        )
                    );

            Logger.Info(
                    $"BATCH TRANSITION: Actions [{actions}], " +
                    $"Energy {_lastObservation.Player.Energy} -> {observation.Player.Energy}, " +
                    $"Hand {_lastObservation.Hand.Count} -> {observation.Hand.Count}"
                    );
        }

        // Clear before collection actions for next transition. 
        _batchCardActions.Clear();

        if (_lastObservation != null)
        {
            Logger.Info(
                    $"TRANSITION: " +
                    $"Before Energy {_lastObservation.Player.Energy}, " +
                    $"After Energy {observation.Player.Energy}, " +
                    $"Before Hand {_lastObservation.Hand.Count}, " +
                    $"After Hand {observation.Hand.Count}"
                    );
        }

        _lastObservation = observation;

        Logger.Info(
                $"POST-ACTION OBSERVATION: " +
                $"Turn {observation.Turn}, " +
                $"Energy {observation.Player.Energy}, " +
                $"Stars {observation.Player.Stars}, " +
                $"Hand count {observation.Hand.Count}"
                );

        foreach (var enemy in observation.Enemies)
        {
            Logger.Info(
                    $"POST-ACTION ENEMY: ID {enemy.CombatId}, HP {enemy.Hp}"
                    );
        }
    }
}
