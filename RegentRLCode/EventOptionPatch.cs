using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Nodes.Events;
using MegaCrit.Sts2.Core.Nodes.Rooms;

namespace RegentRL.RegentRLCode;

// Handles ordinary events, including events that trigger combat.
// Neow remains handled separately by NeowOptionPatch.
[HarmonyPatch(
    typeof(NEventOptionButton),
    nameof(NEventOptionButton.EnableButton))]
public static class EventOptionPatch
{
    private static bool _decisionPending;
    private static NEventRoom? _lastRoom;
    private static long _nextDecisionId;
    private static bool _followUpRequested;
    private static bool _proceedAttempted;
    private static int _generation;

    // Don't make event decisions while another interface
    // or an active combat controls the game.
    private static bool IsBusy() =>
        CombatManager.Instance.IsInProgress ||
        (NOverlayStack.Instance?.ScreenCount ?? 0) > 0 ||
        (NMapScreen.Instance?.IsOpen ?? false);

    [HarmonyPostfix]
    public static void Postfix(NEventOptionButton __instance)
    {
        if (__instance.Event is AncientEventModel ||
            __instance.Option == null ||
            __instance.Option.IsLocked)
            return;

        var room = NEventRoom.Instance;

        if (room == null)
            return;

        MainFile.EnsureCardSelectorInstalled();

        if (!ReferenceEquals(room, _lastRoom))
        {
            _lastRoom = room;
            _decisionPending = false;
            _followUpRequested = false;
            _proceedAttempted = false;
            ++_generation;
        }

        if (_decisionPending || _proceedAttempted || IsBusy())
            return;

        _decisionPending = true;
        _ = StartDecisionAsync(room, _generation);
    }

    private static async Task StartDecisionAsync(
        NEventRoom room,
        int generation)
    {
        try
        {
            await Task.Delay(300);

            Callable.From(() =>
            {
                if (IsCurrent(room, generation) && !IsBusy())
                {
                    CollectAndRequest(room, generation);
                }
                else if (IsCurrent(room, generation))
                {
                    _decisionPending = false;
                }
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"EVENT START ERROR: {ex}");

            if (generation == _generation)
                _decisionPending = false;
        }
    }

    private static bool IsCurrent(
        NEventRoom room,
        int generation)
    {
        return generation == _generation &&
               ReferenceEquals(room, _lastRoom) &&
               GodotObject.IsInstanceValid(room) &&
               room.IsInsideTree();
    }

    private static List<NEventOptionButton> GetLegalButtons(
        NEventRoom room)
    {
        var buttons = new List<NEventOptionButton>();

        CollectButtons(room, buttons);

        return buttons
            .Where(b =>
                GodotObject.IsInstanceValid(b) &&
                b.IsInsideTree() &&
                b.IsEnabled &&
                b.Visible &&
                b.Event is not AncientEventModel &&
                b.Option != null &&
                !b.Option.IsLocked)
            .ToList();
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

    private static void CollectAndRequest(
        NEventRoom room,
        int generation)
    {
        try
        {
            if (!IsCurrent(room, generation) ||
                _proceedAttempted ||
                IsBusy())
                return;

            var legal = GetLegalButtons(room);

            if (legal.Count == 0)
            {
                MainFile.Logger.Info("EVENT: No ready options");
                _decisionPending = false;
                return;
            }

            long decisionId = ++_nextDecisionId;

            MainFile.Logger.Info(
                $"EVENT: Sending {legal.Count} choices to Python"
            );

            _ = RequestChoiceAsync(
                room,
                legal,
                decisionId,
                generation
            );
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info(
                $"EVENT COLLECT ERROR: {ex}"
            );

            if (generation == _generation)
                _decisionPending = false;
        }
    }

    private static async Task RequestChoiceAsync(
        NEventRoom room,
        List<NEventOptionButton> buttons,
        long decisionId,
        int generation)
    {
        try
        {
            // Reuse the existing Python option-choice protocol.
            var request = new
            {
                Type = "NeowDecision",
                DecisionId = decisionId,

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
                MainFile.Logger.Info(
                    "EVENT: Invalid Python response"
                );

                if (generation == _generation)
                    _decisionPending = false;

                return;
            }

            int index = response.ActionIndex;

            // All Godot scene interactions happen on the main thread.
            Callable.From(() =>
            {
                try
                {
                    if (!IsCurrent(room, generation) ||
                        _proceedAttempted ||
                        IsBusy())
                        return;

                    var selected = buttons[index];

                    if (!GodotObject.IsInstanceValid(selected) ||
                        !selected.IsInsideTree() ||
                        !selected.IsEnabled ||
                        !selected.Visible ||
                        selected.Option == null ||
                        selected.Option.IsLocked ||
                        !GetLegalButtons(room).Contains(selected))
                    {
                        MainFile.Logger.Info(
                            "EVENT: Selected option is stale"
                        );

                        _decisionPending = false;
                        return;
                    }

                    // Snapshot available options before clicking.
                    var previousButtons =
                        new HashSet<NEventOptionButton>(
                            GetLegalButtons(room)
                        );

                    bool isProceed = selected.Option.IsProceed;

                    MainFile.Logger.Info(
                        $"EVENT: Executing " +
                        selected.Option.Title.GetFormattedText()
                    );

                    if (isProceed)
                    {
                        _proceedAttempted = true;

                        MainFile.Logger.Info(
                            "EVENT: Proceed attempted; " +
                            "stopping event automation"
                        );
                    }
                    else
                    {
                        _followUpRequested = false;
                    }

                    // Let the game execute the native event option.
                    selected.ForceClick();

                    if (!isProceed)
                    {
                        // This now waits through combat if necessary.
                        _ = WaitForNextOptionsAsync(
                            room,
                            previousButtons,
                            generation
                        );
                    }
                }
                catch (Exception ex)
                {
                    MainFile.Logger.Info(
                        $"EVENT CLICK ERROR: {ex}"
                    );

                    if (generation == _generation)
                        _decisionPending = false;
                }
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info(
                $"EVENT PYTHON ERROR: {ex}"
            );

            if (generation == _generation)
                _decisionPending = false;
        }
    }

    private static async Task WaitForNextOptionsAsync(
        NEventRoom room,
        HashSet<NEventOptionButton> previousButtons,
        int generation)
    {
        // Poll through event-triggered combat and intervening overlays.
        // Godot objects are inspected on the main thread.
        bool sawCombat = false;
        bool completed = false;
        int elapsedTicks = 0;

        // Maximum wait: 5 minutes (1500 * 200ms).
        while (!completed && elapsedTicks++ < 1500)
        {
            await Task.Delay(200);

            Callable.From(() =>
            {
                if (completed ||
                    generation != _generation ||
                    !ReferenceEquals(room, _lastRoom) ||
                    !_decisionPending ||
                    _proceedAttempted)
                {
                    completed = true;
                    return;
                }

                // Events that do not resume after combat may remove
                // their original event room entirely.
                if (!GodotObject.IsInstanceValid(room) ||
                    !room.IsInsideTree())
                {
                    MainFile.Logger.Info(
                        "EVENT: Original room exited"
                    );

                    completed = true;
                    _decisionPending = false;
                    return;
                }

                // Case 1: The event has entered combat.
                // Our existing combat controller handles everything.
                bool inCombat = CombatManager.Instance.IsInProgress;

                if (inCombat)
                {
                    if (!sawCombat)
                    {
                        MainFile.Logger.Info(
                            "EVENT: Combat started; deferring decisions"
                        );
                    }

                    sawCombat = true;
                    return;
                }

                // Case 2: A reward or card-selection overlay is active.
                // Let its existing specialized controller handle it.
                if (IsBusy())
                    return;

                // Case 3: The event is ready to accept another choice.
                var currentButtons = GetLegalButtons(room);

                if (currentButtons.Count == 0)
                    return;

                // Following combat, buttons may be reused.
                // Otherwise, wait for a different set of buttons.
                if (!sawCombat &&
                    previousButtons.SetEquals(currentButtons))
                    return;

                if (_followUpRequested)
                {
                    completed = true;
                    return;
                }

                _followUpRequested = true;
                completed = true;

                if (sawCombat)
                {
                    MainFile.Logger.Info(
                        $"EVENT: Combat finished; resuming with " +
                        $"{currentButtons.Count} choices"
                    );
                }
                else
                {
                    MainFile.Logger.Info(
                        $"EVENT: Options changed; " +
                        $"{currentButtons.Count} choices available"
                    );
                }

                CollectAndRequest(room, generation);
            }).CallDeferred();
        }

        if (!completed && generation == _generation)
        {
            MainFile.Logger.Info(
                "EVENT: Follow-up wait timed out (5 minutes)"
            );

            // Reset on the Godot main thread.
            Callable.From(() =>
            {
                if (generation == _generation &&
                    ReferenceEquals(room, _lastRoom) &&
                    !_proceedAttempted)
                {
                    _decisionPending = false;
                }
            }).CallDeferred();
        }
    }
}

