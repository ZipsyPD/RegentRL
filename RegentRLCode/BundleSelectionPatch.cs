using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

using Godot;
using HarmonyLib;

using MegaCrit.Sts2.Core.Nodes.Cards;
using MegaCrit.Sts2.Core.Nodes.Screens.CardSelection;
using MegaCrit.Sts2.Core.Nodes.CommonUi;

namespace RegentRL.RegentRLCode;

[HarmonyPatch(typeof(NChooseABundleSelectionScreen))]
public static class BundleSelectionPatch
{
    private static readonly HashSet<ulong> Pending = new();
    private static long _decisionId;

    [HarmonyPostfix]
    [HarmonyPatch(nameof(NChooseABundleSelectionScreen.AfterOverlayOpened))]
    public static void OnOpened(NChooseABundleSelectionScreen __instance)
    {
        ulong id = __instance.GetInstanceId();

        if (!Pending.Add(id))
            return;

        _ = SelectBundleAsync(__instance);
    }

    [HarmonyPostfix]
    [HarmonyPatch(nameof(NChooseABundleSelectionScreen._ExitTree))]
    public static void OnClosed(NChooseABundleSelectionScreen __instance)
    {
        Pending.Remove(__instance.GetInstanceId());
    }

    private static async Task SelectBundleAsync(
        NChooseABundleSelectionScreen screen)
    {
        try
        {
            // Allow the UI to finish opening.
            await screen.ToSignal(
                screen.GetTree().CreateTimer(0.8),
                SceneTreeTimer.SignalName.Timeout
            );

            if (!IsActive(screen))
                return;

            var row = screen.GetNode<Control>("%BundleRow");

            var bundles = row.GetChildren()
                .OfType<NCardBundle>()
                .ToList();

            if (bundles.Count == 0)
            {
                MainFile.Logger.Info("BUNDLE: No bundles found");
                return;
            }

            long decisionId = ++_decisionId;

            var request = new
            {
                Type = "BundleDecision",
                DecisionId = decisionId,
                ProtocolVersion = 2,
                RunObservation = RunObservationExtractor.TryExtractLocal(),
                LegalActions = bundles.Select((bundle, index) => new
                {
                    Type = "ChooseBundle",
                    BundleIndex = index,
                    CardIds = bundle.Bundle
                        .Select(card => card.Id.ToString())
                        .ToArray()
                }).ToArray()
            };

            MainFile.Logger.Info(
                $"BUNDLE: Sending {bundles.Count} bundles to Python"
            );

            var response =
                await PythonAgentClient.RequestNeowDecisionAsync(request);

            if (response == null ||
                response.DecisionId != decisionId ||
                response.ActionIndex < 0 ||
                response.ActionIndex >= bundles.Count)
            {
                MainFile.Logger.Info("BUNDLE: Invalid Python response");
                return;
            }

            int selectedIndex = response.ActionIndex;
            var before = request.RunObservation;
            string[] chosenCards = bundles[selectedIndex].Bundle.Select(card => card.Id.Entry).ToArray();

            Callable.From(() =>
            {
                if (!IsActive(screen))
                    return;

                var selected = bundles[selectedIndex];

                if (!GodotObject.IsInstanceValid(selected) ||
                    !selected.IsInsideTree())
                    return;

                MainFile.Logger.Info(
                    $"BUNDLE: Selecting bundle {selectedIndex}"
                );

                // Triggers the game's original OnBundleClicked handler.
                selected.EmitSignal(
                    NCardBundle.SignalName.Clicked,
                    selected
                );

                // Wait for the preview to appear, then confirm.
                screen.GetTree().CreateTimer(0.7).Timeout += () =>
                {
                    if (!IsActive(screen))
                        return;

                    var confirm =
                        screen.GetNode<NConfirmButton>("%Confirm");

                    MainFile.Logger.Info("BUNDLE: Confirming selection");

                    var tree = screen.GetTree();
                    confirm.ForceClick();
                    NoncombatEffectVerifier.ConfirmDeckGain(tree,
                        "BundleDecision", decisionId, before, chosenCards);
                };
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"BUNDLE ERROR: {ex}");
        }
    }

    private static bool IsActive(NChooseABundleSelectionScreen screen)
    {
        return GodotObject.IsInstanceValid(screen)
            && screen.IsInsideTree()
            && screen.IsVisibleInTree();
    }
}

