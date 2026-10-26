using System;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;
using System.Linq;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.GameActions;

namespace RegentRL.RegentRLCode;

// Opt-in, observation-only native-action logging. Does not drive game input.
// WARNING: records post-execution events, NOT BC-ready (observation, legal actions, label) samples.
public static class PassiveHumanRecorder
{
    public static bool Enabled => Environment.GetEnvironmentVariable("REGENTRL_PASSIVE_RECORD") == "1";
    private static readonly object Gate = new();
    private sealed record PendingChoice(object Request, int Index);
    private static readonly Dictionary<GameAction, PendingChoice> Choices = new();
    private static long _nextDecision;
    private static string TrainingPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "RegentRL", "human_verified_combat.jsonl");
    private static string FilePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "RegentRL", "passive_human_native_events.jsonl");

    public static void Append(object entry)
    {
        if (!Enabled) return;
        try
        {
            lock (Gate)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
                File.AppendAllText(FilePath, JsonSerializer.Serialize(entry) + "\n");
            }
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"PASSIVE RECORDER: {ex.Message}");
        }
    }

    public static void RecordTurn(CombatState state)
    {
        if (state.Players.Count == 0 || state.Players[0].PlayerCombatState == null) return;
        var obs = CombatObservationExtractor.Extract(state, state.Players[0]);
        Append(new { Kind = "TurnStarted", TimestampUtc = DateTime.UtcNow,
            Observation = obs, LegalActions = CombatLegalActionGenerator.Generate(obs) });
    }

    // Native action executor fires this immediately before executing the action.
    // We require a UNIQUE legal action match; ambiguous identical cards are skipped.
    public static void RecordBeforeAction(GameAction action)
    {
        if (!Enabled || (action is not PlayCardAction && action is not EndPlayerTurnAction)) return;
        try
        {
            var state = CombatManager.Instance.DebugOnlyGetState();
            if (state == null || state.Players.Count == 0 || state.Players[0].PlayerCombatState == null) return;
            var obs = CombatObservationExtractor.Extract(state, state.Players[0]);
            var legal = CombatLegalActionGenerator.Generate(obs);
            var matches = legal.Select((a, i) => new { a, i }).Where(x =>
                action is EndPlayerTurnAction ? x.a.Type == "EndTurn" :
                action is PlayCardAction card && x.a.Type == "PlayCard" &&
                    x.a.CardId == card.CardModelId.Entry &&
                    x.a.TargetId == card.TargetId).ToList();
            if (matches.Count != 1)
            {
                Append(new { Kind = "UnmatchedAction", TimestampUtc = DateTime.UtcNow,
                    Action = action.GetType().Name, CandidateMatches = matches.Count });
                return;
            }
            long id = System.Threading.Interlocked.Increment(ref _nextDecision);
            var request = new { Type = "CombatDecision", DecisionId = id,
                ProtocolVersion = 2, Observation = obs,
                RunObservation = RunObservationExtractor.TryExtractLocal(), LegalActions = legal };
            lock (Gate) Choices[action] = new PendingChoice(request, matches[0].i);
        }
        catch (Exception ex) { MainFile.Logger.Info($"PASSIVE before action: {ex.Message}"); }
    }

    public static void RecordNativeAction(GameAction action)
    {
        if (!Enabled) return;
        PendingChoice? choice;
        lock (Gate) { Choices.TryGetValue(action, out choice); Choices.Remove(action); }
        if (choice != null)
        {
            try
            {
                lock (Gate)
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(TrainingPath)!);
                    File.AppendAllText(TrainingPath, JsonSerializer.Serialize(new {
                        Executed = true, Source = "HumanNativeMouse",
                        FullRequest = choice.Request,
                        PolicyResponse = new { ActionIndex = choice.Index }
                    }) + "\n");
                }
            }
            catch (Exception ex) { MainFile.Logger.Info($"PASSIVE training write: {ex.Message}"); }
        }
        if (action is PlayCardAction card)
            Append(new { Kind = "PlayedCard", TimestampUtc = DateTime.UtcNow,
                CardId = card.CardModelId.Entry, TargetId = card.TargetId });
        else if (action is UsePotionAction)
            Append(new { Kind = "UsedPotion", TimestampUtc = DateTime.UtcNow });
        else if (action is EndPlayerTurnAction)
            Append(new { Kind = "EndedTurn", TimestampUtc = DateTime.UtcNow });
    }
}
