using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;

using HarmonyLib;

using MegaCrit.Sts2.Core.CardSelection;
using MegaCrit.Sts2.Core.Commands;

namespace RegentRL.RegentRLCode;

public sealed class CardSelectionContext
{
    public string Purpose { get; init; } = "Unknown";
    public string Source { get; init; } = "Unknown";
}

[HarmonyPatch]
public static class CardSelectionPurposePatch
{
    // AsyncLocal follows the logical async execution flow.
    // This avoids one global Purpose variable being
    // overwritten by an unrelated selection.
    private static readonly AsyncLocal<CardSelectionContext?>
        CurrentContext = new();

    public static CardSelectionContext Current =>
        CurrentContext.Value ?? new CardSelectionContext();

    [HarmonyTargetMethods]
    public static IEnumerable<MethodBase> TargetMethods()
    {
        string[] names =
        {
            "FromDeckForUpgrade",
            "FromDeckForRemoval",
            "FromDeckForTransformation",
            "FromDeckForEnchantment",
            "FromHandForDiscard",
            "FromHandForUpgrade",
            "FromDeckGeneric",
            "FromHand",
            "FromCombatPile",
            "FromSimpleGrid",
            "FromSimpleGridForRewards",
            "FromChooseACardScreen"
        };

        return typeof(CardSelectCmd)
            .GetMethods(BindingFlags.Public | BindingFlags.Static)
            .Where(method => names.Contains(method.Name))
            .Cast<MethodBase>();
    }

    [HarmonyPrefix]
    public static void Prefix(
        MethodBase __originalMethod,
        out CardSelectionContext? __state,
        object[] __args)
    {
        __state = CurrentContext.Value;

        // An outer, more specific selection context wins.
        // For example, FromDeckForRemoval calls FromDeckGeneric.
        if (__state != null)
            return;

        string name = __originalMethod.Name;

        string purpose = name switch
        {
            "FromDeckForUpgrade" => "Upgrade",
            "FromHandForUpgrade" => "Upgrade",
            "FromDeckForRemoval" => "Remove",
            "FromDeckForTransformation" => "Transform",
            "FromDeckForEnchantment" => "Enchant",
            "FromHandForDiscard" => "Discard",
            "FromChooseACardScreen" => "ChooseCard",
            _ => "Generic"
        };

        var prefs = __args.OfType<CardSelectorPrefs>().FirstOrDefault();

        if (prefs.Prompt != null &&
            prefs.Prompt.LocTable == "card_selection")
        {
            purpose = prefs.Prompt.LocEntryKey switch
            {
                "TO_TRANSFORM" => "Transform",
                "TO_EXHAUST" => "Exhaust",
                "TO_REMOVE" => "Remove",
                "TO_DISCARD" => "Discard",
                "TO_UPGRADE" => "Upgrade",
                "TO_ENCHANT" => "Enchant",
                _ => purpose
            };
        }

        string source = name switch
        {
            "FromDeckForUpgrade" or
            "FromDeckForRemoval" or
            "FromDeckForTransformation" or
            "FromDeckForEnchantment" or
            "FromDeckGeneric" => "Deck",

            "FromHandForDiscard" or
            "FromHandForUpgrade" or
            "FromHand" => "Hand",

            "FromCombatPile" => "CombatPile",
            "FromSimpleGridForRewards" => "CardReward",
            "FromChooseACardScreen" => "ChooseCardScreen",
            _ => "Generic"
        };

        CurrentContext.Value = new CardSelectionContext
        {
            Purpose = purpose,
            Source = source
        };
    }

    [HarmonyPostfix]
    public static void Postfix(
        CardSelectionContext? __state)
    {
        // Restore the caller's context. Async method
        // continuations retain their captured context.
        CurrentContext.Value = __state;
    }
}

