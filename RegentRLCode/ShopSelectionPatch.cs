
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Entities.Merchant;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens.Shops;

namespace RegentRL.RegentRLCode;

[HarmonyPatch(typeof(NMerchantRoom), nameof(NMerchantRoom._Ready))]
public static class ShopSelectionPatch
{
    private static NMerchantRoom? _room;
    private static bool _shopping;
    private static bool _busy;
    private static int _generation;
    private static long _decisionId;
    private static int _purchases;

    public static bool IsShopping => _shopping;

    [HarmonyPostfix]
    public static void Postfix(NMerchantRoom __instance)
    {
        _room = __instance;
        _shopping = true;
        _busy = false;
        _purchases = 0;
        int generation = ++_generation;

        MainFile.EnsureCardSelectorInstalled();
        MainFile.Logger.Info("SHOP: Merchant room detected");

        // Let Godot finish initializing the room.
        Callable.From(() =>
        {
            if (!IsCurrent(__instance, generation))
                return;

            MainFile.Logger.Info("SHOP: Opening inventory");
            __instance.OpenInventory();

            _ = WaitForInventoryAsync(__instance, generation);
        }).CallDeferred();
    }

    private static bool IsCurrent(
        NMerchantRoom room,
        int generation)
    {
        return generation == _generation &&
               ReferenceEquals(room, _room) &&
               GodotObject.IsInstanceValid(room) &&
               room.IsInsideTree();
    }

    private static List<NMerchantSlot> GetAffordableSlots(
        NMerchantRoom room)
    {
        bool hasPotionRoom =
            room.Inventory.Inventory?.Player.HasOpenPotionSlots ?? false;

        return room.Inventory.GetAllSlots()
            .Where(slot =>
                GodotObject.IsInstanceValid(slot) &&
                slot.IsInsideTree() &&
                slot.Visible &&
                slot.Entry != null &&
                slot.Entry.IsStocked &&
                slot.Entry.EnoughGold &&
                (!(slot.Entry is MerchantPotionEntry) ||
                 hasPotionRoom))
            .ToList();
    }

    private static async Task WaitForInventoryAsync(
        NMerchantRoom room,
        int generation)
    {
        for (int attempt = 0; attempt < 50; attempt++)
        {
            await Task.Delay(200);

            Callable.From(() =>
            {
                if (!IsCurrent(room, generation) || _busy)
                    return;

                if (!room.Inventory.IsOpen)
                    return;

                RequestShopDecision(room, generation);
            }).CallDeferred();
        }
    }

    private static void RequestShopDecision(
        NMerchantRoom room,
        int generation)
    {
        if (!IsCurrent(room, generation) ||
            !_shopping ||
            _busy ||
            !room.Inventory.IsOpen)
            return;

        _busy = true;

        var slots = GetAffordableSlots(room);
        long id = ++_decisionId;

        var actions = slots.Select((slot, index) => new
        {
            Type = slot.Entry switch
            {
                MerchantCardEntry => "BuyCard",
                MerchantRelicEntry => "BuyRelic",
                MerchantPotionEntry => "BuyPotion",
                MerchantCardRemovalEntry => "RemoveCard",
                _ => "BuyItem"
            },
            SlotIndex = index,
            Cost = slot.Entry.Cost,
            ItemType = slot.Entry.GetType().Name
        }).ToList();

        MainFile.Logger.Info(
            $"SHOP: Sending {slots.Count} affordable items to Python"
        );

        _ = GetDecisionAsync(room, slots, id, generation);
    }

    private static async Task GetDecisionAsync(
        NMerchantRoom room,
        List<NMerchantSlot> slots,
        long decisionId,
        int generation)
    {
        try
        {
            var legalActions = slots.Select((slot, index) => new
            {
                Type = slot.Entry switch
                {
                    MerchantCardEntry => "BuyCard",
                    MerchantRelicEntry => "BuyRelic",
                    MerchantPotionEntry => "BuyPotion",
                    MerchantCardRemovalEntry => "RemoveCard",
                    _ => "BuyItem"
                },
                SlotIndex = index,
                Cost = slot.Entry.Cost,
                ItemType = slot.Entry.GetType().Name
            }).Cast<object>()
              .Concat(new object[]
              {
                  new { Type = "LeaveShop" }
              }).ToArray();

            var request = new
            {
                Type = "ShopDecision",
                DecisionId = decisionId,
                ProtocolVersion = 2,
                RunObservation = RunObservationExtractor.TryExtractLocal(),
                Gold = room.Inventory.Inventory?.Player.Gold ?? 0,
                LegalActions = legalActions
            };

            var response =
                await PythonAgentClient.RequestNeowDecisionAsync(request);

            Callable.From(() =>
            {
                if (!IsCurrent(room, generation) ||
                    !_shopping ||
                    !room.Inventory.IsOpen)
                    return;

                if (response == null ||
                    response.DecisionId != decisionId ||
                    response.ActionIndex < 0 ||
                    response.ActionIndex >= legalActions.Length)
                {
                    MainFile.Logger.Info(
                        "SHOP: Invalid Python response; leaving"
                    );
                    _ = LeaveAsync(room, generation);
                    return;
                }

                int index = response.ActionIndex;

                if (index == slots.Count)
                {
                    MainFile.Logger.Info("SHOP: Python chose LeaveShop");
                    _ = LeaveAsync(room, generation);
                    return;
                }

                var selected = slots[index];

                if (!GodotObject.IsInstanceValid(selected) ||
                    !selected.IsInsideTree() ||
                    !selected.Entry.IsStocked ||
                    !selected.Entry.EnoughGold)
                {
                    MainFile.Logger.Info("SHOP: Selected item is stale");
                    _busy = false;
                    RequestShopDecision(room, generation);
                    return;
                }

                MainFile.Logger.Info(
                    $"SHOP: Purchasing {selected.Entry.GetType().Name} " +
                    $"for {selected.Entry.Cost} gold"
                );

                _ = PurchaseAsync(
                    room,
                    selected,
                    generation
                );
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"SHOP DECISION ERROR: {ex}");

            Callable.From(() =>
            {
                if (IsCurrent(room, generation))
                    _ = LeaveAsync(room, generation);
            }).CallDeferred();
        }
    }

    private static async Task PurchaseAsync(
        NMerchantRoom room,
        NMerchantSlot slot,
        int generation)
    {
        try
        {
            // Native STS2 transaction: checks stock/cost,
            // charges gold, applies the item and fires
            // PurchaseCompleted when successful.
            bool success =
                await slot.Entry.OnTryPurchaseWrapper(
                    room.Inventory.Inventory
                );

            MainFile.Logger.Info(
                $"SHOP: Purchase result = {success}"
            );

            await Task.Delay(500);

            Callable.From(() =>
            {
                if (!IsCurrent(room, generation) || !_shopping)
                    return;

                if (success)
                    _purchases++;

                // Initial integration test: buy at most one
                // item, then leave. Later we can remove
                // this limit for repeated RL decisions.
                if (!success)
                {
                    MainFile.Logger.Info(
                            "SHOP: Purchas failed; leaving shop"
                            );
                    _ = LeaveAsync(room, generation);
                    return;
                }

                _busy = false;
                RequestShopDecision(room, generation);
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"SHOP PURCHASE ERROR: {ex}");

            Callable.From(() =>
            {
                if (IsCurrent(room, generation))
                    _ = LeaveAsync(room, generation);
            }).CallDeferred();
        }
    }

    private static async Task LeaveAsync(
        NMerchantRoom room,
        int generation)
    {
        if (!IsCurrent(room, generation))
            return;

        if (room.Inventory.IsOpen)
        {
            var back = room.Inventory
                .GetNodeOrNull<NBackButton>("%BackButton");

            if (back == null ||
                !GodotObject.IsInstanceValid(back))
            {
                MainFile.Logger.Info(
                    "SHOP: Cannot find native Back button"
                );
                return;
            }

            MainFile.Logger.Info("SHOP: Closing inventory");
            back.ForceClick();
        }

        // Wait for native shop UI to finish closing.
        await Task.Delay(700);

        Callable.From(() =>
        {
            if (!IsCurrent(room, generation))
                return;

            if (room.Inventory.IsOpen ||
                !room.ProceedButton.IsEnabled)
            {
                MainFile.Logger.Info(
                    "SHOP: Proceed not ready; leaving room unchanged"
                );
                return;
            }

            MainFile.Logger.Info("SHOP: Clicking native Proceed");

            // Release map ownership just before native Proceed.
            _shopping = false;
            room.ProceedButton.ForceClick();
        }).CallDeferred();
    }
}

