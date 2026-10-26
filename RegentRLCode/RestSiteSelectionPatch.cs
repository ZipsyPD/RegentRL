
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Nodes.RestSite;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;

namespace RegentRL.RegentRLCode;

// Automates native rest-site options and the Proceed button.
// Smith's deck selection is handled by RegentRLCardSelector.
[HarmonyPatch(typeof(NRestSiteRoom), nameof(NRestSiteRoom._Ready))]
public static class RestSiteSelectionPatch
{
    private static NRestSiteRoom? _lastRoom;
    private static bool _decisionPending;
    private static bool _optionClicked;
    private static bool _proceedClicked;
    private static long _nextDecisionId;
    private static int _generation;

    [HarmonyPostfix]
    public static void Postfix(NRestSiteRoom __instance)
    {
        if (ReferenceEquals(__instance, _lastRoom))
            return;

        _lastRoom = __instance;
        _decisionPending = false;
        _optionClicked = false;
        _proceedClicked = false;
        ++_generation;

        MainFile.EnsureCardSelectorInstalled();

        MainFile.Logger.Info("REST: Room initialized");

        _ = WaitForOptionsAsync(__instance, _generation);
    }

    private static bool IsCurrent(
        NRestSiteRoom room,
        int generation)
    {
        return generation == _generation &&
               ReferenceEquals(room, _lastRoom) &&
               GodotObject.IsInstanceValid(room) &&
               room.IsInsideTree();
    }

    private static bool OverlayActive()
    {
        return (NOverlayStack.Instance?.ScreenCount ?? 0) > 0;
    }

    private static void FindButtons(
        Node root,
        List<NRestSiteButton> results)
    {
        foreach (Node child in root.GetChildren())
        {
            if (child is NRestSiteButton button)
                results.Add(button);

            FindButtons(child, results);
        }
    }

    private static List<NRestSiteButton> GetLegalButtons(
        NRestSiteRoom room)
    {
        var buttons = new List<NRestSiteButton>();
        FindButtons(room, buttons);

        return buttons
            .Where(b =>
                GodotObject.IsInstanceValid(b) &&
                b.IsInsideTree() &&
                b.IsVisibleInTree() &&
                b.IsEnabled &&
                b.Option.IsEnabled)
            .ToList();
    }

    private static async Task WaitForOptionsAsync(
        NRestSiteRoom room,
        int generation)
    {
        // The native rest-site UI animates into view.
        // Wait for actual usable buttons instead of assuming
        // that they exist immediately after _Ready().
        for (int attempt = 0; attempt < 100; attempt++)
        {
            await Task.Delay(200);

            Callable.From(() =>
            {
                if (!IsCurrent(room, generation) ||
                    _decisionPending ||
                    _optionClicked ||
                    OverlayActive())
                    return;

                var buttons = GetLegalButtons(room);

                if (buttons.Count == 0)
                    return;

                _decisionPending = true;

                MainFile.Logger.Info(
                    $"REST: Sending {buttons.Count} options to Python"
                );

                _ = RequestDecisionAsync(
                    room,
                    buttons,
                    ++_nextDecisionId,
                    generation
                );
            }).CallDeferred();
        }
    }

    private static async Task RequestDecisionAsync(
        NRestSiteRoom room,
        List<NRestSiteButton> buttons,
        long decisionId,
        int generation)
    {
        try
        {
            var request = new
            {
                Type = "RestSiteDecision",
                DecisionId = decisionId,
                ProtocolVersion = 2,
                RunObservation = RunObservationExtractor.TryExtractLocal(),
                LegalActions = buttons.Select((b, i) => new
                {
                    Type = "ChooseRestOption",
                    OptionIndex = i,
                    OptionId = b.Option.OptionId,
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
                    "REST: Invalid Python response"
                );
                _decisionPending = false;
                return;
            }

            int index = response.ActionIndex;

            Callable.From(() =>
            {
                if (!IsCurrent(room, generation) ||
                    OverlayActive() ||
                    _optionClicked)
                    return;

                var selected = buttons[index];

                if (!GodotObject.IsInstanceValid(selected) ||
                    !selected.IsInsideTree() ||
                    !selected.IsEnabled ||
                    !selected.Option.IsEnabled ||
                    !GetLegalButtons(room).Contains(selected))
                {
                    MainFile.Logger.Info(
                        "REST: Selected option is stale"
                    );
                    _decisionPending = false;
                    return;
                }

                MainFile.Logger.Info(
                    $"REST: Selecting {selected.Option.OptionId}"
                );

                _optionClicked = true;
                selected.ForceClick();

                // The game executes the selected option.
                // For SMITH, that includes opening the native
                // deck-upgrade selection screen.
                _ = WaitForProceedAsync(room, generation);
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"REST ERROR: {ex}");

            if (generation == _generation)
                _decisionPending = false;
        }
    }

    private static async Task WaitForProceedAsync(
        NRestSiteRoom room,
        int generation)
    {
        // Wait for native selection, card upgrades, and VFX.
        for (int attempt = 0; attempt < 300; attempt++)
        {
            await Task.Delay(200);

            Callable.From(() =>
            {
                if (!IsCurrent(room, generation) ||
                    _proceedClicked ||
                    OverlayActive())
                    return;

                var proceed = room.ProceedButton;

                if (!GodotObject.IsInstanceValid(proceed) ||
                    !proceed.IsInsideTree() ||
                    !proceed.IsEnabled ||
                    !proceed.IsVisibleInTree())
                    return;

                _proceedClicked = true;

                MainFile.Logger.Info(
                    "REST: Clicking native Proceed"
                );

                proceed.ForceClick();
            }).CallDeferred();
        }

        if (generation == _generation && !_proceedClicked)
        {
            MainFile.Logger.Info(
                "REST: Proceed was not reached within 60 seconds"
            );
        }
    }
}

