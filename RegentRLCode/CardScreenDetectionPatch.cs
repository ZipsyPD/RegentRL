using HarmonyLib;
using MegaCrit.Sts2.Core.Nodes.Screens.CardSelection;

namespace RegentRL.RegentRLCode;

[HarmonyPatch]
public static class CardScreenDetectionPatch
{
    [HarmonyPatch(typeof(NDeckCardSelectScreen), nameof(NDeckCardSelectScreen._Ready))]
    [HarmonyPostfix]
    public static void OnDeckSelectionReady()
    {
        MainFile.Logger.Info(
            "REGENTRL CARD SCREEN: Deck card selection opened"
        );
    }

    [HarmonyPatch(typeof(NSimpleCardSelectScreen), nameof(NSimpleCardSelectScreen._Ready))]
    [HarmonyPostfix]
    public static void OnSimpleSelectionReady()
    {
        MainFile.Logger.Info(
            "REGENTRL CARD SCREEN: Simple card selection opened"
        );
    }
}

