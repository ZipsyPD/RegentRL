using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Nodes.Events;
using MegaCrit.Sts2.Core.Nodes.Rooms;

namespace RegentRL.RegentRLCode;

[HarmonyPatch(
    typeof(NEventOptionButton),
    nameof(NEventOptionButton.EnableButton)
)]
public static class NeowOptionPatch
{
    private static bool _decisionPending;
    private static NEventRoom? _lastRoom;
    private static long _nextDecisionId;
    private static bool _followUpRequested;
    private static bool _proceedAttempted;

    [HarmonyPostfix]
    public static void Postfix(NEventOptionButton __instance)
    {
        if (__instance.Event is not AncientEventModel)
            return;

        MainFile.EnsureCardSelectorInstalled();
        if (__instance.Option == null || __instance.Option.IsLocked)
            return;

        var room = NEventRoom.Instance;
        if (room == null)
            return;

        // Allow a fresh decision in each newly created room.
        if (!ReferenceEquals(room, _lastRoom))
        {
            _lastRoom = room;
            _decisionPending = false;
            _followUpRequested = false;
            _proceedAttempted = false;
        }

        // EnableButton can fire repeatedly.
        if (_decisionPending || _proceedAttempted)
            return;

        _decisionPending = true;
        _ = StartDecisionAsync(room);
    }

    private static async Task StartDecisionAsync(NEventRoom room)
    {
        try
        {
            // Allow the remaining buttons to finish appearing.
            await Task.Delay(300);

            // Collect scene nodes on Godot's main thread.
            Callable.From(() => CollectAndRequest(room)).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"NEOW START ERROR: {ex}");
            _decisionPending = false;
        }
    }

    private static void CollectAndRequest(NEventRoom room)
    {
        try
        {
            if (!GodotObject.IsInstanceValid(room) ||
                !room.IsInsideTree())
            {
                _decisionPending = false;
                return;
            }

            var buttons = new List<NEventOptionButton>();
            CollectButtons(room, buttons);

            var legal = buttons
                .Where(b =>
                    GodotObject.IsInstanceValid(b) &&
                    b.IsInsideTree() &&
                    b.IsEnabled &&
                    b.Visible &&
                    b.Event is AncientEventModel &&
                    b.Option != null &&
                    !b.Option.IsLocked)
                .ToList();

            if (_proceedAttempted)
            {
                MainFile.Logger.Info(
                    "NEOW: Proceed already attempted; ignoring further options"
                );
                return;
            }

            if (legal.Count == 0)
            {
                MainFile.Logger.Info("NEOW: No ready options");
                _decisionPending = false;
                return;
            }

            long decisionId = ++_nextDecisionId;

            MainFile.Logger.Info(
                $"NEOW: Sending {legal.Count} choices to Python"
            );

            _ = RequestChoiceAsync(room, legal, decisionId);
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"NEOW COLLECT ERROR: {ex}");
            _decisionPending = false;
        }
    }

    private static void CollectButtons(
        Node root,
        List<NEventOptionButton> results)
    {
        foreach (Node child in root.GetChildren())
        {
            if (child is NEventOptionButton button)
                results.Add(button);

            CollectButtons(child, results);
        }
    }

    private static async Task RequestChoiceAsync(
        NEventRoom room,
        List<NEventOptionButton> buttons,
        long decisionId)
    {
        try
        {
            var request = new
            {
                Type = "NeowDecision",
                DecisionId = decisionId,
                ProtocolVersion = 2,
                RunObservation = RunObservationExtractor.TryExtractLocal(),
                LegalActions = buttons.Select((b, i) => new
                {
                    Type = "ChooseOption",
                    OptionIndex = i,
                    Name = b.Option.Title.GetFormattedText()
                }).ToArray()
            };

            var response =
                await PythonAgentClient.RequestNeowDecisionAsync(request);

            if (response == null ||
                response.DecisionId != decisionId ||
                response.ActionIndex < 0 ||
                response.ActionIndex >= buttons.Count)
            {
                MainFile.Logger.Info("NEOW: Invalid Python response");
                _decisionPending = false;
                return;
            }

            int index = response.ActionIndex;
            var before = request.RunObservation;

            // All Godot scene interactions happen on the main thread.
            Callable.From(() =>
            {
                try
                {
                    if (!GodotObject.IsInstanceValid(room) ||
                        !room.IsInsideTree())
                        return;

                    var selected = buttons[index];

                    if (!GodotObject.IsInstanceValid(selected) ||
                        !selected.IsInsideTree() ||
                        !selected.IsEnabled ||
                        selected.Option.IsLocked)
                        return;

                    MainFile.Logger.Info(
                        $"NEOW: Executing {selected.Option.Title.GetFormattedText()}"
                    );
                    string optionName = selected.Option.Title.GetFormattedText();
                    bool isProceed = optionName.Trim()
                        .Equals("Proceed", StringComparison.OrdinalIgnoreCase);

                    if (isProceed)
                    {
                        _proceedAttempted = true;

                        MainFile.Logger.Info(
                            "NEOW: Proceed attempted; stopping Neow automation"
                        );
                    }
                    else
                    {
                        _followUpRequested = false;
                    }

                    var tree = room.GetTree();
                    selected.ForceClick();
                    // For direct relic-granting choices, a changed relic inventory
                    // is native evidence. Nested choices stay proposal-only.
                    if (!isProceed && before != null)
                        NoncombatEffectVerifier.ConfirmRelic(tree,
                            decisionId, string.Join("|", before.Relics));

                    if (!isProceed)
                    {
                        // The game may present another set of options, such as Proceed.
                        // Wait for this click to update the event before accepting another decision.
                        _ = ResetAfterChoiceAsync(room, selected);
                    }
                }
                catch (Exception ex)
                {
                    MainFile.Logger.Info($"NEOW CLICK ERROR: {ex}");
                }
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"NEOW PYTHON ERROR: {ex}");
            _decisionPending = false;
        }
    }

    
    private static async Task ResetAfterChoiceAsync(
        NEventRoom room,
        NEventOptionButton previousChoice)
    {
        // Wait for nested choices (upgrades, card rewards, etc.)
        // to finish and for the next Neow button to appear.
        for (int attempt = 0; attempt < 40; attempt++)
        {
            await Task.Delay(250);

            // Task.Delay may resume off the Godot main thread.
            // Schedule scene-tree inspection back on the main thread.
            Callable.From(() =>
            {
                if (!GodotObject.IsInstanceValid(room) ||
                    !room.IsInsideTree() ||
                    !ReferenceEquals(room, _lastRoom))
                    return;

                if (!_decisionPending || _proceedAttempted)
                    return;

                bool oldChoiceActive =
                    GodotObject.IsInstanceValid(previousChoice) &&
                    previousChoice.IsInsideTree() &&
                    previousChoice.IsEnabled &&
                    previousChoice.Visible;

                if (oldChoiceActive)
                    return;

                var buttons = new List<NEventOptionButton>();
                CollectButtons(room, buttons);

                bool hasNewChoice = buttons.Any(b =>
                    GodotObject.IsInstanceValid(b) &&
                    b.IsInsideTree() &&
                    b.IsEnabled &&
                    b.Visible &&
                    b.Event is AncientEventModel &&
                    b.Option != null &&
                    !b.Option.IsLocked);

                if (!hasNewChoice)
                    return;

                // Existing pending flag remains true while sending.
                // This extra flag prevents repeated polling requests.
                if (_followUpRequested)
                    return;

                _followUpRequested = true;

                MainFile.Logger.Info(
                    "NEOW: Follow-up options detected"
                );

                CollectAndRequest(room);
            }).CallDeferred();
        }
    }
}


