using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using HarmonyLib;
using MegaCrit.Sts2.Core.Runs;

namespace RegentRL.RegentRLCode;

// Native run lifecycle is independent of combat lifecycle.
// A lost TCP connection must never prevent gameplay or saves.
public static class RunLifecycleBridge
{
    private static readonly object Gate = new();
    private static string? _runId;
    private static bool _installed;

    public static string EnsureRunId()
    {
        lock (Gate)
            return _runId ??= Guid.NewGuid().ToString("N");
    }

    public static void Install()
    {
        if (_installed) return;
        _installed = true;
        RunManager.Instance.RunStarted += OnRunStarted;
        MainFile.Logger.Info("TRACE: Run lifecycle bridge installed");
    }

    private static void OnRunStarted(RunState state)
    {
        string id;
        lock (Gate) _runId = id = Guid.NewGuid().ToString("N");
        MainFile.Logger.Info($"TRACE: Native run started {id}");
        SendEvent(new { Type = "RunLifecycle", Event = "Started", RunId = id });
    }

    public static void OnRunEnded(bool isVictory, bool isAbandoned)
    {
        string id = EnsureRunId();
        string outcome = isAbandoned ? "Abandoned" : isVictory ? "Win" : "Loss";
        MainFile.Logger.Info($"TRACE: Native run ended {id}: {outcome}");
        SendEvent(new {
            Type = "RunLifecycle", Event = "Ended", RunId = id,
            Outcome = outcome, OutcomeVerified = true
        });
        lock (Gate) _runId = null;
    }

    // Abandoning from the main menu bypasses RunManager.OnEnded.
    // Only close a run whose ID we observed in this game process.
    public static void OnMainMenuAbandoned()
    {
        string? id;
        lock (Gate)
        {
            id = _runId;
            _runId = null;
        }

        if (id == null)
        {
            MainFile.Logger.Info(
                "TRACE: Main-menu abandon detected, but no active native RunId. " +
                "Skipping unverified trace closure (possibly loaded after restart).");
            return;
        }

        MainFile.Logger.Info($"TRACE: Native run ended {id}: Abandoned");
        SendEvent(new {
            Type = "RunLifecycle", Event = "Ended", RunId = id,
            Outcome = "Abandoned", OutcomeVerified = true
        });
    }

    // Called only after a matching native combat transition is observed.
    // Terminal acknowledges carry the combat outcome, not the whole run outcome.
    public static void SendVerifiedCombatAction(
        long decisionId, object afterObservation,
        bool terminal = false, string? combatOutcome = null)
    {
        string? id;
        lock (Gate) id = _runId;
        if (id == null) return;

        SendEvent(new {
            Type = "ActionExecution",
            Event = "Resolved",
            RunId = id,
            DecisionType = "CombatDecision",
            DecisionId = decisionId,
            Executed = true,
            NextObservation = afterObservation,
            Terminal = terminal,
            CombatOutcome = combatOutcome
        });
        MainFile.Logger.Info($"TRACE: Sent combat resolution for decision {decisionId}");
    }

    // Native evidence must be obtained from game state, not merely a successful click.
    public static void SendVerifiedNoncombatAction(string decisionType, long decisionId, RunObservation after)
    {
        string? id;
        lock (Gate) id = _runId;
        if (id == null) return;
        SendEvent(new {
            Type = "ActionExecution", Event = "Resolved", RunId = id,
            DecisionType = decisionType, DecisionId = decisionId,
            Executed = true, NextObservation = after
        });
        MainFile.Logger.Info($"TRACE: Sent verified {decisionType} decision {decisionId}");
    }

    private static void SendEvent(object payload)
    {
        string line = JsonSerializer.Serialize(payload);
        _ = Task.Run(async () =>
        {
            try
            {
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                using var client = new TcpClient();
                await client.ConnectAsync("127.0.0.1", 5050, timeout.Token);
                using var stream = client.GetStream();
                using var writer = new StreamWriter(stream, new UTF8Encoding(false), leaveOpen: true);
                await writer.WriteLineAsync(line);
                await writer.FlushAsync();
                // Read ACK to make transport failures observable.
                using var reader = new StreamReader(stream, Encoding.UTF8);
                string? reply = await reader.ReadLineAsync(timeout.Token);
                if (reply == null) throw new IOException("No lifecycle ACK");
            }
            catch (Exception ex)
            {
                MainFile.Logger.Info($"TRACE: Lifecycle event not delivered: {ex.Message}");
            }
        });
    }
}

[HarmonyPatch(typeof(RunManager), nameof(RunManager.OnEnded))]
public static class RunEndedLifecyclePatch
{
    [HarmonyPostfix]
    public static void Postfix(RunManager __instance, bool isVictory)
    {
        RunLifecycleBridge.OnRunEnded(isVictory, __instance.IsAbandoned);
    }
}
