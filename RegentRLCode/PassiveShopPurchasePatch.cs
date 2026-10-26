using System;
using System.Collections.Generic;
using HarmonyLib;
using MegaCrit.Sts2.Core.Entities.Merchant;

namespace RegentRL.RegentRLCode;

// Snapshot identity before purchase: entries can clear Model/CreationResult on success.
[HarmonyPatch]
public static class PassiveShopPurchasePatch
{
    private sealed record Snapshot(string? Id, string? Name, string Kind, int Cost);
    private static readonly Dictionary<MerchantEntry, Snapshot> Pending = new();

    [HarmonyPrefix]
    [HarmonyPatch(typeof(MerchantEntry), nameof(MerchantEntry.OnTryPurchaseWrapper))]
    public static void OnPurchaseAttempt(MerchantEntry __instance)
    {
        if (!PassiveHumanRecorder.Enabled) return;
        Pending[__instance] = new Snapshot(
            ShopItemInfo.Id(__instance), ShopItemInfo.Name(__instance),
            __instance.GetType().Name, __instance.Cost);
    }

    [HarmonyPrefix]
    [HarmonyPatch(typeof(MerchantEntry), nameof(MerchantEntry.InvokePurchaseCompleted))]
    public static void OnCompleted(MerchantEntry __instance)
    {
        if (!PassiveHumanRecorder.Enabled) return;
        if (!Pending.Remove(__instance, out var info)) return;
        PassiveHumanRecorder.Append(new {
            Kind = "PurchasedShopItem", TimestampUtc = DateTime.UtcNow,
            ItemType = info.Kind, ItemId = info.Id,
            ItemName = info.Name, Cost = info.Cost
        });
    }
}
