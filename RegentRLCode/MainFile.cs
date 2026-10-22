using System.IO;
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

    // Enables execution of decisions received from Python.
    // Keep false until single-action safeguards are done
    private const bool PythonControlEnabled = true;

    // Number of cards automatically submitted in this combat.
    // Temporarily limited to two for testing sequential decisions.
    private static int _autoPlayTestCount;

    // Prevent agent from submitting another action
    // while previous one is being processed
    // this prevent batch processing
    private static bool _agentActionPending;

    // Prevent multiple post-action observation tasks from running concurrently.
    private static bool _observationTaskPending;

    // The action submitted by our agent, retain until execution completes.
    private static CombatLegalAction? _pendingAgentAction;

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

    // Next python decision
    private static long _nextDecisionId = 0;

    // Stop outdated decision
    private static long _latestDecisionId = 0;

    private static bool _pythonRequestPending = false;

    // Limit Python to one submitted action during initial testing
    private static int _pythonActionsSubmitted = 0;

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
        CombatExperienceBuffer.Clear();
        _autoPlayTestCount = 0;
        _agentActionPending = false;
        _pendingAgentAction = null;
        _observationTaskPending = false;
        // Python invalidation reset
        _latestDecisionId = -1;
        _pythonRequestPending = false;
        _pythonActionsSubmitted = 0;

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

            // Match a single completed card against the agent's
            // Submitted decision to preserve the original hand index
            int? agentHandIndex = null;
            bool isAgentAction = false;

            if (_batchCardActions.Count == 1 &&
                    _pendingAgentAction?.Type == "PlayCard" &&
                    _batchCardActions[0].CardModelId.Entry == _pendingAgentAction.CardId &&
                    _batchCardActions[0].TargetId == _pendingAgentAction.TargetId)
            {
                agentHandIndex = _pendingAgentAction.HandIndex;
                isAgentAction = true;
            }

            _lastTransition = new CombatTransition
            {
                Before = _lastObservation,
                After = observation,
                Terminal = true,
                Outcome = "Win",
                EndedTurn = _awaitingNextTurn,
                IsAgentAction = isAgentAction,
                Actions = _batchCardActions.Select(card => new CombatActionObservation
                        {
                        Type = "PlayCard",
                        CardId = card.CardModelId.Entry,
                        TargetId = card.TargetId,
                        HandIndex = agentHandIndex
                        }).ToList()
            };

            CombatExperienceBuffer.Add(_lastTransition);

            Logger.Info(
                    $"TERMINAL EXPERIENCE COLLECTED: Win, " +
                    $"Total {CombatExperienceBuffer.Count}"
                    );

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
                    IsAgentAction = _awaitingNextTurn &&
                        _pendingAgentAction?.Type == "EndTurn" &&
                        _batchCardActions.Count == 0,
                    EndedTurn = _awaitingNextTurn,
                    Actions = _batchCardActions.Select(card => new CombatActionObservation
                            {
                            Type = "PlayCard",
                            CardId = card.CardModelId.Entry,
                            TargetId = card.TargetId
                            }).ToList()
                };
                CombatExperienceBuffer.Add(_lastTransition);

                Logger.Info(
                        $"TERMINAL EXPERIENCE COLLECTED: Loss, " +
                        $"Total {CombatExperienceBuffer.Count}"
                        );

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

        // Persist collected transitions when combat finishes
        // This runs after both victories and defeats.
        if (CombatExperienceBuffer.Count > 0)
        {
            string directory = Path.Combine(
                    OS.GetUserDataDir(),
                    "RegentRL",
                    "experiences"
                    );

            Directory.CreateDirectory(directory);

            string filename = $"combat_{System.Guid.NewGuid():N}.json";
            string path = Path.Combine(directory, filename);

            CombatExperienceBuffer.SaveToFile(path);

            Logger.Info(
                    $"EXPERIENCE SAVED: {CombatExperienceBuffer.Count} " +
                    $"transitions to {path}"  
                    );
        }

        // Combat has ended, so no agent action should remain pending
        //  This also handles EndTurn decisions that resulted in defeat
        _pendingAgentAction = null;
        _agentActionPending = false;
        // Invalidate any python response still in flight
        _latestDecisionId = -1;
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

            _lastTransition = new CombatTransition
            {
                Before = _lastObservation,
                After = observation,
                EndedTurn = true,
                Terminal = false,
                IsAgentAction = _pendingAgentAction?.Type == "EndTurn",
                Actions = new List<CombatActionObservation>
                {
                    new CombatActionObservation
                    {
                        Type = "EndTurn"
                    }
                }
            };

            CombatExperienceBuffer.Add(_lastTransition);

            Logger.Info(
                    $"EXPERIENCE COLLECTED: " +
                    $"Total {CombatExperienceBuffer.Count}"
                    );

            Logger.Info(
                    $"STRUCTURED END TURN TRANSITION CREATED: " +
                    $"Turn {_lastTransition.Before.Turn} -> {_lastTransition.After.Turn}, " +
                    $"Actions {_lastTransition.Actions.Count}"
                    );
        }

        _awaitingNextTurn = false;
        // The previous EndTurn decision has reached the next
        // player-turn observation, so the agent can act again.
        if (_pendingAgentAction?.Type == "EndTurn")
        {
            _pendingAgentAction = null;
            _agentActionPending = false;
        }
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

        // Generate the actions available to the RL agent.
        var legalActions = CombatLegalActionGenerator.Generate(observation);

        RequestPythonDecision(observation);

        Logger.Info($"LEGAL ACTIONS: {legalActions.Count}");

        foreach (var action in legalActions)
        {
            Logger.Info(
                    $"LEGAL ACTION: Type {action.Type}, " +
                    $"HandIndex {action.HandIndex?.ToString() ?? "None"}, " +
                    $"Card {action.CardId}, " +
                    $"Target {action.TargetId?.ToString() ?? "None"}"    
                    );
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

        // Request the first agent decision after observing the turn.
        RequestAgentAction(state, player);
    }

    // Temporary decision policy.
    // Eventually will ask the Python RL agent what to do. 
    private static void RequestAgentAction(
            CombatState state,
            Player player
            )
    {
        if (!AutoPlayTestEnabled || _agentActionPending || _autoPlayTestCount >= 2)
            return;

        var combat = player.PlayerCombatState;
        if (combat == null)
            return;

        var observation = CombatObservationExtractor.Extract(state, player);
        var legalActions = CombatLegalActionGenerator.Generate(observation);

        // Choose the first available card action,
        // regardless of ID
        var selectedAction = legalActions.FirstOrDefault(action => 
                action.Type == "PlayCard"
                );

        if (selectedAction == null)
            return;

        // Mark the agent as busy before submitting the action.
        _agentActionPending = true;
        _pendingAgentAction = selectedAction;

        bool submitted = CombatActionDispatcher.TryExecute(
                state,
                player,
                selectedAction
                );

        if (!submitted)
        {
            _agentActionPending = false;
            _pendingAgentAction = null;
            Logger.Info("AGENT TEST: Action submission rejected.");
            return;
        }

        _autoPlayTestCount++;

        Logger.Info(
                $"AGENT TEST: Submitted {selectedAction.CardId}, " +
                $"HandIndex {selectedAction.HandIndex}, " +
                $"Target {selectedAction.TargetId}"
                );
    }

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
            if (_observationTaskPending)
            {
                Logger.Info("Post-action observation already scheduled.");
                return;
            }

            _observationTaskPending = true;

            var combatId = CombatManager.Instance.CurrentCombatId;
            _ = LogAfterExecutorFinishes(combatId);
        }
    }

    private static async Task LogAfterExecutorFinishes(CombatId? combatId)
    {
        // Wait for the action executor to finish its current processing.
        // This is asynchronous and does not necessarily mean even combat
        // lifecycle event or delayed effect has completed.
        try
        {
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
                // Detect when a pending agent decision produced
                // more than one recorded card action.
                if (_pendingAgentAction?.Type == "PlayCard" && 
                        _batchCardActions.Count != 1)
                {
                    Logger.Info(
                            $"WARNING: Agent submitted one card, but " +
                            $"{_batchCardActions.Count} card actions were collected!"
                            );
                }
                // Only associate an agent-selected hand index with a
                // single matching completed card action.
                int? agentHandIndex = null;
                bool isAgentAction = false;

                if (_batchCardActions.Count == 1 &&
                        _pendingAgentAction?.Type == "PlayCard" &&
                        _batchCardActions[0].CardModelId.Entry == _pendingAgentAction.CardId &&
                        _batchCardActions[0].TargetId == _pendingAgentAction.TargetId)
                {
                    agentHandIndex = _pendingAgentAction.HandIndex;
                    isAgentAction = true;
                }
                // Construct a structured transition from the previous observation,
                // all completed cards in this batch, and the resulting observation
                // For now, this is a batch and not one decision though. 
                _lastTransition = new CombatTransition
                {
                    Before = _lastObservation,
                    After = observation,
                    EndedTurn = false,
                    IsAgentAction = isAgentAction,
                    Actions = _batchCardActions.Select(card => new CombatActionObservation
                            {
                            Type = "PlayCard",
                            CardId = card.CardModelId.Entry,
                            TargetId = card.TargetId,
                            HandIndex = agentHandIndex
                            }).ToList()
                };

                CombatExperienceBuffer.Add(_lastTransition);

                Logger.Info(
                        $"EXPERIENCE COLLECTED: " +
                        $"Total {CombatExperienceBuffer.Count}"
                        );

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
            _pendingAgentAction = null;
            // The submitted action has finished and its result has been observed.
            _agentActionPending = false;

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

            // Request the next decision only after observing the 
            // completed action's results.
            if (AutoPlayTestEnabled)
            {
                RequestAgentAction(state, state.Players[0]);
            }

            // Send the updated combat state to Python after a card finishes.
            if (CombatManager.Instance.IsInProgress &&
                    state.CurrentSide == CombatSide.Player)
            {
                RequestPythonDecision(observation);
            }
        }
        finally
        {
            _observationTaskPending = false;
        } 
    }

    // Entry point for sending a decision request to Python
    private static void RequestPythonDecision(CombatObservation observation)
    {
        if (_pythonRequestPending)
        {
            Logger.Info("PYTHON: Request already pending; skipping.");
            return;
        }

        var legalActions = CombatLegalActionGenerator.Generate(observation);

        _pythonRequestPending = true;

        var decisionRequest = new CombatDecisionRequest
        {
            DecisionId = ++_nextDecisionId,
            Observation = observation,
            LegalActions = legalActions
        };

        _latestDecisionId = decisionRequest.DecisionId;

        Logger.Info(
                $"PYTHON REQUEST: DecisionId={decisionRequest.DecisionId}, " +
                $"LegalActions={legalActions.Count}"
                );
        
        _ = TestPythonConnectionAsync(decisionRequest);
    }

    private static async System.Threading.Tasks.Task TestPythonConnectionAsync(
            CombatDecisionRequest request)
    {
        try
        {
            var response = await PythonAgentClient.RequestActionAsync(request);

            if (response == null)
            {
                Logger.Info("PYTHON TEST: No response received.");
                Callable.From(() =>
                        {
                            if (request.DecisionId == _latestDecisionId)
                            {
                                _pythonRequestPending = false;
                            }
                        }).CallDeferred();
                return;
            }

            if (response.DecisionId != request.DecisionId)
            {
                Logger.Info(
                        $"PYTHON TEST: Decision ID mismatch. " +
                        $"Expected {request.DecisionId}, received {response.DecisionId}");
                Callable.From(() =>
                        {
                            if (request.DecisionId == _latestDecisionId)
                            {
                                _pythonRequestPending = false;
                            }
                        }).CallDeferred();
                return;
            }
            
            if (response.ActionIndex < 0 || 
                    response.ActionIndex >= request.LegalActions.Count)
            {
                Logger.Info(
                        $"PYTHON TEST: Invalid action index {response.ActionIndex}");
                Callable.From(() =>
                        {
                            if (request.DecisionId == _latestDecisionId)
                            {
                                _pythonRequestPending = false;
                            }
                        }).CallDeferred();
                return;
            }

            var selectedAction = request.LegalActions[response.ActionIndex];

            Logger.Info(
                    $"PYTHON RESPONSE: DecisionId={response.DecisionId}, " +
                    $"ActionIndex={response.ActionIndex}, " +
                    $"Type={selectedAction.Type}, Card={selectedAction.CardId}"
                    );

            Callable.From(() =>
                    {
                        try
                        {
                            if (response.DecisionId != _latestDecisionId)
                            {
                                Logger.Info(
                                        $"PYTHON STALE RESPONSE: DecisionId={response.DecisionId}, " +
                                        $"Latest={_latestDecisionId}"
                                        );
                                return;
                            }
                            Logger.Info(
                                    $"PYTHON MAIN THREAD TEST: " +
                                    $"DecisionId={response.DecisionId}, " +
                                    $"ActionIndex={response.ActionIndex}, " +
                                    $"Card={selectedAction.CardId}"
                                    );
                            if (!PythonControlEnabled)
                                return;

                            // Initial safety limit: only one Python action per combat.
                            if (_pythonActionsSubmitted >= 50 || _agentActionPending)
                                return;

                            // Never execute against an ended or inactive combat
                            if (!CombatManager.Instance.IsInProgress ||
                                    _currentCombatState == null ||
                                    _currentCombatState.CurrentSide != CombatSide.Player ||
                                    _currentCombatState.Players.Count == 0)
                            {
                                Logger.Info("PYTHON: Combat is no longer actionable.");
                                return;
                            }

                            // Recheck the legal action against the current state
                            var state = _currentCombatState;
                            var player = state.Players[0];

                            var currentObservation = 
                                CombatObservationExtractor.Extract(state, player);

                            var currentActions =
                                CombatLegalActionGenerator.Generate(currentObservation);

                            // The legal-action list must still match the request.
                            // This is a preliminary stale-state check.
                            if (System.Text.Json.JsonSerializer.Serialize(currentObservation) !=
                                    System.Text.Json.JsonSerializer.Serialize(request.Observation) ||
                                    System.Text.Json.JsonSerializer.Serialize(currentActions) !=
                                    System.Text.Json.JsonSerializer.Serialize(request.LegalActions))
                            {
                                Logger.Info("PYTHON: Combat state changed; rejecting stale action.");
                                return;
                            }

                            // Claim the action before submitting it.
                            _agentActionPending = true;
                            _pendingAgentAction = selectedAction;

                            bool submitted;

                            try
                            {
                                submitted = CombatActionDispatcher.TryExecute(
                                        state,
                                        player,
                                        selectedAction
                                        );
                            }
                            catch (Exception ex)
                            {
                                _agentActionPending = false;
                                _pendingAgentAction = null;
                                Logger.Info($"PYTHON DISPATCH ERROR: {ex.Message}");
                                return;
                            }

                            if (!submitted)
                            {
                                _agentActionPending = false;
                                _pendingAgentAction = null;
                                Logger.Info("PYTHON: Action submission rejected.");
                                return;
                            }

                            _pythonActionsSubmitted++;

                            Logger.Info(
                                    $"PYTHON ACTION SUBMITTED: " +
                                    $"DecisionId={response.DecisionId}, " +
                                    $"Type={selectedAction.Type}, " +
                                    $"Card={selectedAction.CardId}"
                                    );
                        }
                        finally
                        {
                            _pythonRequestPending = false;
                        }
                    }).CallDeferred();
        }
        catch (Exception ex)
        {
            Logger.Info($"PYTHON TEST ERROR: {ex.Message}");

            Callable.From(() =>
                    {
                        if (request.DecisionId == _latestDecisionId)
                        {
                            _pythonRequestPending = false;
                        }
                    }).CallDeferred();
        }
    }
}
