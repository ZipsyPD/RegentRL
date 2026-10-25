using System;
using System.Threading.Tasks;

using Godot;
using HarmonyLib;

using MegaCrit.Sts2.Core.Nodes.GodotExtensions;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens.TreasureRoomRelic;
using MegaCrit.Sts2.Core.Runs;

namespace RegentRL.RegentRLCode;

[HarmonyPatch(typeof(NTreasureRoom), nameof(NTreasureRoom._Ready))]
public static class TreasureSelectionPatch
{
    private static NTreasureRoom? _room;
    private static int _generation;

    private static bool _opened;
    private static bool _picked;
    private static bool _proceeded;
    private static int _ticks;

    [HarmonyPostfix]
    public static void OnReady(NTreasureRoom __instance)
    {
        _room = __instance;
        int generation = ++_generation;

        _opened = false;
        _picked = false;
        _proceeded = false;
        _ticks = 0;

        MainFile.Logger.Info("TREASURE: Room initialized");

        // All Godot node interactions take place on its main thread.
        _ = PollAsync(__instance, generation);
    }

    private static bool IsCurrent(
        NTreasureRoom room,
        int generation)
    {
        return generation == _generation &&
               ReferenceEquals(_room, room) &&
               GodotObject.IsInstanceValid(room) &&
               room.IsInsideTree();
    }

    private static async Task PollAsync(
        NTreasureRoom room,
        int generation)
    {
        // Maximum approximately 60 seconds.
        // This avoids an unbounded automation loop.
        for (int i = 0; i < 300; i++)
        {
            await Task.Delay(200);

            Callable.From(() =>
            {
                if (!IsCurrent(room, generation) || _proceeded)
                    return;

                try
                {
                    Tick(room);
                }
                catch (Exception ex)
                {
                    MainFile.Logger.Info(
                        $"TREASURE ERROR: {ex}"
                    );

                    // Do not force Proceed after an exception.
                    _proceeded = true;
                }
            }).CallDeferred();

            if (generation != _generation)
                return;
        }

        MainFile.Logger.Info(
            "TREASURE: Polling timeout; manual intervention may be needed"
        );
    }

    private static void Tick(NTreasureRoom room)
    {
        _ticks++;

        // Phase 1: Open chest.
        if (!_opened)
        {
            var chest = room.GetNodeOrNull<NClickableControl>("Chest");

            if (chest == null ||
                !GodotObject.IsInstanceValid(chest))
            {
                MainFile.Logger.Info(
                    "TREASURE: Chest node not found"
                );
                return;
            }

            if (!chest.IsEnabled)
                return;

            _opened = true;

            MainFile.Logger.Info(
                "TREASURE: Opening native chest"
            );

            chest.ForceClick();
            return;
        }

        var collection =
            room.GetNodeOrNull<NTreasureRoomRelicCollection>(
                "%RelicCollection"
            );

        if (collection == null ||
            !GodotObject.IsInstanceValid(collection))
        {
            return;
        }

        // Phase 2: Collect the relic.
        if (!_picked)
        {
            var relics =
                RunManager.Instance
                    .TreasureRoomRelicSynchronizer
                    .CurrentRelics;

            var holder = collection.SingleplayerRelicHolder;

            if (collection.Visible &&
                relics != null &&
                relics.Count > 0 &&
                GodotObject.IsInstanceValid(holder) &&
                holder.Visible &&
                holder.IsEnabled &&
                holder.MouseFilter !=
                    Control.MouseFilterEnum.Ignore)
            {
                // The native relic picker also rejects clicks
                // during its initial 200 ms protection window.
                // Polling until enabled avoids premature clicks.
                MainFile.Logger.Info(
                    $"TREASURE: Claiming relic {relics[0].Id.Entry}"
                );

                _picked = true;
                holder.ForceClick();
                return;
            }

            // STS2 can also generate an empty chest.
            // Only bypass the relic-click phase if the
            // collection is visibly open but contains no relics.
            if (collection.Visible &&
                relics != null &&
                relics.Count == 0)
            {
                MainFile.Logger.Info(
                    "TREASURE: Empty chest"
                );

                _picked = true;
            }

            return;
        }

        // Phase 3: Wait for native relic awarding and Proceed.
        var proceed = room.ProceedButton;

        if (proceed == null ||
            !GodotObject.IsInstanceValid(proceed) ||
            !proceed.IsEnabled)
        {
            return;
        }

        // Skip and Proceed share a button. Only click Proceed
        // once the relic picking interface has closed.
        if (collection.Visible)
        {
            return;
        }

        _proceeded = true;

        MainFile.Logger.Info(
            "TREASURE: Clicking native Proceed"
        );

        proceed.ForceClick();
    }
}

