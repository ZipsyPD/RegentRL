
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Nodes.Cards.Holders;
using MegaCrit.Sts2.Core.Nodes.Screens.CardSelection;

namespace RegentRL.RegentRLCode;

[HarmonyPatch(typeof(NCardRewardSelectionScreen))]
public static class CardRewardSelectionPatch
{
    private static readonly HashSet<ulong> Pending = new();
    private static long _decisionId;

    [HarmonyPostfix]
    [HarmonyPatch(nameof(NCardRewardSelectionScreen.AfterOverlayOpened))]
    public static void OnOpened(NCardRewardSelectionScreen __instance)
    {
        ulong id = __instance.GetInstanceId();

        if (!Pending.Add(id))
            return;

        _ = ChooseCardAsync(__instance);
    }

    [HarmonyPostfix]
    [HarmonyPatch(nameof(NCardRewardSelectionScreen._ExitTree))]
    public static void OnClosed(NCardRewardSelectionScreen __instance)
    {
        Pending.Remove(__instance.GetInstanceId());
    }

    private static async Task ChooseCardAsync(
        NCardRewardSelectionScreen screen)
    {
        try
        {
            // Wait until the game's initial click lock expires.
            await screen.ToSignal(
                screen.GetTree().CreateTimer(0.8),
                SceneTreeTimer.SignalName.Timeout
            );

            if (!GodotObject.IsInstanceValid(screen) ||
                !screen.IsInsideTree() ||
                !screen.IsVisibleInTree())
                return;

            var row = screen.GetNode<Control>("UI/CardRow");

            var cards = row.GetChildren()
                .OfType<NCardHolder>()
                .ToList();

            if (cards.Count == 0)
            {
                MainFile.Logger.Info("CARD REWARD: No cards found");
                return;
            }

            long decisionId = ++_decisionId;

            var request = new
            {
                Type = "CardRewardDecision",
                DecisionId = decisionId,
                LegalActions = cards.Select((card, i) => new
                {
                    Type = "ChooseCard",
                    CardIndex = i,
                    CardId = card.CardModel.Id.ToString()
                }).ToArray()
            };

            MainFile.Logger.Info(
                $"CARD REWARD: Sending {cards.Count} cards to Python"
            );

            var response =
                await PythonAgentClient.RequestNeowDecisionAsync(request);

            if (response == null ||
                response.DecisionId != decisionId ||
                response.ActionIndex < 0 ||
                response.ActionIndex >= cards.Count)
            {
                MainFile.Logger.Info("CARD REWARD: Invalid response");
                return;
            }

            int index = response.ActionIndex;

            // Scene interaction must happen on the Godot main thread.
            Callable.From(() =>
            {
                if (!GodotObject.IsInstanceValid(screen) ||
                    !screen.IsInsideTree() ||
                    !screen.IsVisibleInTree())
                    return;

                var selected = cards[index];

                if (!GodotObject.IsInstanceValid(selected) ||
                    !selected.IsInsideTree())
                    return;

                MainFile.Logger.Info(
                    $"CARD REWARD: Selecting index {index}"
                );

                selected.EmitSignal(
                    NCardHolder.SignalName.Pressed,
                    selected
                );
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"CARD REWARD ERROR: {ex}");
        }
    }
}

