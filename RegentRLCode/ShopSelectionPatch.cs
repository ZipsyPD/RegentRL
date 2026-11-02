
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
    private static bool _leaving;
    private static bool _leaveRequested;
    private static int _generation;
    private static long _decisionId;
    private static int _purchases;

    // A bool alone outlives the merchant scene, and used to block every later map.
    public static bool IsShopping
    {
        get
        {
            if (_shopping && (_room == null ||
                !GodotObject.IsInstanceValid(_room) ||
                !_room.IsInsideTree() ||
                !ReferenceEquals(_room, NMerchantRoom.Instance)))
            {
                ResetSession("merchant scene is no longer active");
            }
            return _shopping;
        }
    }

    public static void ResetSession(string reason)
    {
        if (_shopping || _busy || _leaving)
            MainFile.Logger.Info($"SHOP: Clearing automation state ({reason})");
        ++_generation; // Invalidate in-flight server requests and deferred callbacks.
        _room = null;
        _shopping = false;
        _busy = false;
        _leaving = false;
        _leaveRequested = false;
        _purchases = 0;
    }

    // Native merchant Proceed opens the map before the old room is removed.
    // If the user clicked Proceed manually after LeaveShop was requested, the
    // map must not stay blocked behind the stale shop guard.
    public static void OnMapOpened(bool fromTopBar)
    {
        if (!fromTopBar && _leaveRequested && _room != null &&
            GodotObject.IsInstanceValid(_room) &&
            ReferenceEquals(_room, NMerchantRoom.Instance) &&
            !_room.Inventory.IsOpen)
            ResetSession("merchant proceeded to map manually");
    }

    public static void OnMerchantExited(NMerchantRoom room)
    {
        if (ReferenceEquals(room, _room))
        {
            ResetSession("merchant room exited");
            MapSelectionPatch.TryResumeMap();
        }
    }

    public static void TryResumeLeave(NMerchantRoom room)
    {
        if (_leaveRequested && !_leaving && ReferenceEquals(room, _room))
            _ = LeaveAsync(room, _generation);
    }

    [HarmonyPostfix]
    public static void Postfix(NMerchantRoom __instance)
    {
        _room = __instance;
        _shopping = true;
        _busy = false;
        _leaving = false;
        _leaveRequested = false;
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
            var legalActions = slots.Select((slot, index) =>
            {
                var entry = slot.Entry;
                string kind = entry switch
                {
                    MerchantCardEntry => "BuyCard",
                    MerchantRelicEntry => "BuyRelic",
                    MerchantPotionEntry => "BuyPotion",
                    MerchantCardRemovalEntry => "RemoveCard",
                    _ => "BuyItem"
                };
                string itemId = entry switch
                {
                    MerchantCardEntry card => card.CreationResult?.Card.Id.ToString() ?? "",
                    MerchantRelicEntry relic => relic.Model?.Id.ToString() ?? "",
                    MerchantPotionEntry potion => potion.Model?.Id.ToString() ?? "",
                    _ => ""
                };
                string rarity = entry switch
                {
                    MerchantCardEntry card => card.CreationResult?.Card.Rarity.ToString() ?? "",
                    MerchantRelicEntry relic => relic.Model?.Rarity.ToString() ?? "",
                    MerchantPotionEntry potion => potion.Model?.Rarity.ToString() ?? "",
                    _ => ""
                };
                return new
                {
                    Type = kind,
                    SlotIndex = index,
                    Cost = entry.Cost,
                    ItemType = entry.GetType().Name,
                    ItemId = itemId,
                    Rarity = rarity
                };
            }).Cast<object>()
              .Concat(new object[]
              {
                  new { Type = "LeaveShop" }
              }).ToArray();

            foreach (var entryAction in legalActions)
                MainFile.Logger.Info($"SHOP: Candidate {System.Text.Json.JsonSerializer.Serialize(entryAction)}");

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

    // The native shop enables Proceed *after* InventoryClosed and any active
    // overlay/UI transition. A single 700 ms timeout stranded _shopping=true.
    private static async Task LeaveAsync(NMerchantRoom room, int generation)
    {
        if (!IsCurrent(room, generation) || _leaving)
            return;

        _leaveRequested = true;
        _leaving = true;
        _busy = true; // Do not launch new purchase decisions while leaving.
        bool clickedBack = false;

        // Allow pauses / overlays; native buttons become enabled asynchronously.
        // Every Godot node read and click happens on the main thread.
        for (int attempt = 0; attempt < 240; attempt++)
        {
            var result = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            Callable.From(() =>
            {
                try
                {
                    if (!IsCurrent(room, generation))
                    {
                        result.TrySetResult(true);
                        return;
                    }

                    if (room.Inventory.IsOpen)
                    {
                        // Retry Back periodically if another overlay intercepted it.
                        if (!clickedBack || attempt % 20 == 0)
                        {
                            var back = room.Inventory.GetNodeOrNull<NBackButton>("%BackButton");
                            if (back != null && GodotObject.IsInstanceValid(back))
                            {
                                MainFile.Logger.Info("SHOP: Closing native inventory");
                                back.ForceClick();
                                clickedBack = true;
                            }
                        }
                    }
                    else if (room.ProceedButton.IsEnabled)
                    {
                        MainFile.Logger.Info("SHOP: Proceed enabled; clicking native Proceed");
                        // The native click synchronously opens the map; release our
                        // map-navigation guard *before* invoking that click.
                        ResetSession("native shop Proceed ready");
                        room.ProceedButton.ForceClick();
                        result.TrySetResult(true);
                        return;
                    }

                    if (attempt > 0 && attempt % 20 == 0)
                        MainFile.Logger.Info(
                            $"SHOP: Waiting for UI to close (inventoryOpen={room.Inventory.IsOpen}, " +
                            $"proceedEnabled={room.ProceedButton.IsEnabled})");

                    result.TrySetResult(false);
                }
                catch (Exception ex)
                {
                    MainFile.Logger.Info($"SHOP: Leave retry error: {ex}");
                    result.TrySetResult(false);
                }
            }).CallDeferred();

            if (await result.Task)
                return;

            await Task.Delay(250);
        }

        // Do not falsely mark the room exited: the native UI may still be open.
        // OnActiveScreenUpdated re-arms the leave attempt after a pause/menu closes.
        Callable.From(() =>
        {
            if (IsCurrent(room, generation))
            {
                _leaving = false;
                MainFile.Logger.Info("SHOP: Exit still blocked; will retry on UI update");
            }
        }).CallDeferred();
    }
}

[HarmonyPatch(typeof(NMerchantRoom), nameof(NMerchantRoom._ExitTree))]
public static class ShopRoomExitPatch
{
    [HarmonyPostfix]
    public static void Postfix(NMerchantRoom __instance)
    {
        ShopSelectionPatch.OnMerchantExited(__instance);
    }
}

// Native room updates this whenever a pause/menu/overlay becomes active or closes.
[HarmonyPatch(typeof(NMerchantRoom), "OnActiveScreenUpdated")]
public static class ShopScreenActivationPatch
{
    [HarmonyPostfix]
    public static void Postfix(NMerchantRoom __instance)
    {
        ShopSelectionPatch.TryResumeLeave(__instance);
    }
}
