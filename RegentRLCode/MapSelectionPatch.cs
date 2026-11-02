using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

using Godot;
using HarmonyLib;

using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Rooms;

namespace RegentRL.RegentRLCode;

[HarmonyPatch]
public static class MapSelectionPatch
{
    private static bool _decisionPending;
    private static long _decisionId;
    private static int _generation;

    public static void ResetForRun(string reason)
    {
        ++_generation;
        _decisionPending = false;
        MainFile.Logger.Info($"MAP: Cleared pending navigation ({reason})");
    }

    // Called when a merchant room has finished exiting and a map is visible.
    public static void TryResumeMap()
    {
        var screen = NMapScreen.Instance;
        if (screen != null && GodotObject.IsInstanceValid(screen) &&
            screen.IsInsideTree() && screen.IsVisibleInTree())
            TryStart(screen);
    }

    [HarmonyPatch(typeof(NMapScreen), nameof(NMapScreen.Open))]
    [HarmonyPostfix]
    public static void OnMapOpened(NMapScreen __instance, bool isOpenedFromTopBar)
    {
        MainFile.Logger.Info("MAP: Open hook fired");
        ShopSelectionPatch.OnMapOpened(isOpenedFromTopBar);
        TryStart(__instance);
    }

    [HarmonyPatch(typeof(NMapScreen), nameof(NMapScreen.SetTravelEnabled))]
    [HarmonyPostfix]
    public static void OnTravelEnabled(NMapScreen __instance)
    {
        MainFile.Logger.Info("MAP: SetTravelEnabled hook fired");
        TryStart(__instance);
    }

    [HarmonyPatch(typeof(NMapScreen), nameof(NMapScreen.Close))]
    [HarmonyPostfix]
    public static void OnMapClosed()
    {
        MainFile.Logger.Info("MAP: Close hook fired");
        ++_generation;
        _decisionPending = false;
    }

    private static void TryStart(NMapScreen screen)
    {
        MainFile.Logger.Info(
            $"MAP: TryStart called; pending={_decisionPending}"
        );

        // Don't navigate away while shopping.
        if (ShopSelectionPatch.IsShopping)
        {
            MainFile.Logger.Info(
                "MAP: Shopping in progress; deferring map decision"
            );
            return;
        }

        if (_decisionPending)
            return;

        _decisionPending = true;
        _ = StartDecisionAsync(screen, _generation);
    }

    private static async Task StartDecisionAsync(NMapScreen screen, int generation)
    {
        // Opening animations, pause overlays, and shop exits may take longer
        // than the previous one-shot 400 ms readiness test. Retry while the
        // same map remains open; never click a disabled/unreachable room.
        for (int attempt = 0; attempt < 40; attempt++)
        {
            await Task.Delay(250);
            var result = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);

            Callable.From(() =>
            {
                try
                {
                    if (generation != _generation)
                    {
                        result.TrySetResult(true);
                        return;
                    }

                    bool valid = GodotObject.IsInstanceValid(screen);
                    bool inTree = valid && screen.IsInsideTree();
                    if (!inTree || !screen.IsOpen)
                    {
                        _decisionPending = false;
                        result.TrySetResult(true);
                        return;
                    }

                    bool ready = screen.IsVisibleInTree() &&
                                 screen.IsTravelEnabled &&
                                 !screen.IsTraveling &&
                                 !ShopSelectionPatch.IsShopping;
                    if (!ready)
                    {
                        if (attempt % 8 == 0)
                            MainFile.Logger.Info(
                                $"MAP: Waiting for readiness (visible={screen.IsVisibleInTree()}, " +
                                $"travelEnabled={screen.IsTravelEnabled}, traveling={screen.IsTraveling}, " +
                                $"shopping={ShopSelectionPatch.IsShopping})");
                        result.TrySetResult(false);
                        return;
                    }

                    var points = new List<NMapPoint>();
                    CollectPoints(screen, points);
                    var legal = points
                        .Where(p => GodotObject.IsInstanceValid(p) &&
                                    p.IsInsideTree() && p.IsEnabled && p.Visible)
                        .OrderBy(p => p.Point.coord.row)
                        .ThenBy(p => p.Point.coord.col)
                        .ToList();

                    if (legal.Count == 0)
                    {
                        if (attempt % 8 == 0)
                            MainFile.Logger.Info("MAP: Waiting for reachable nodes");
                        result.TrySetResult(false);
                        return;
                    }

                    long id = ++_decisionId;
                    MainFile.Logger.Info($"MAP: Sending {legal.Count} reachable rooms to Python");
                    _ = RequestChoiceAsync(screen, legal, id, generation);
                    result.TrySetResult(true);
                }
                catch (Exception ex)
                {
                    MainFile.Logger.Info($"MAP READINESS ERROR: {ex}");
                    if (generation == _generation) _decisionPending = false;
                    result.TrySetResult(true);
                }
            }).CallDeferred();

            if (await result.Task)
                return;
        }

        Callable.From(() =>
        {
            if (generation == _generation)
            {
                _decisionPending = false;
                MainFile.Logger.Info("MAP: Readiness timed out; awaiting next map event");
            }
        }).CallDeferred();
    }

    private static void CollectPoints(
        Node root,
        List<NMapPoint> results)
    {
        foreach (Node child in root.GetChildren())
        {
            if (child is NMapPoint point)
                results.Add(point);

            CollectPoints(child, results);
        }
    }

    private static async Task RequestChoiceAsync(
        NMapScreen screen,
        List<NMapPoint> points,
        long decisionId,
        int generation)
    {
        try
        {
            var request = new
            {
                Type = "MapDecision",
                DecisionId = decisionId,
                ProtocolVersion = 2,
                RunObservation = RunObservationExtractor.TryExtractLocal(),
                LegalActions = points.Select((p, i) => new
                {
                    Type = "ChooseRoom",
                    RoomIndex = i,
                    Row = p.Point.coord.row,
                    Column = p.Point.coord.col,
                    RoomType = p.Point.PointType.ToString()
                }).ToArray()
            };

            var response =
                await PythonAgentClient.RequestNeowDecisionAsync(request);

            if (generation != _generation) return;

            if (response == null ||
                response.DecisionId != decisionId ||
                response.ActionIndex < 0 ||
                response.ActionIndex >= points.Count)
            {
                MainFile.Logger.Info("MAP: Invalid response");
                _decisionPending = false;
                return;
            }

            int index = response.ActionIndex;

            Callable.From(() =>
            {
                if (generation != _generation) return;
                if (!GodotObject.IsInstanceValid(screen) ||
                    !screen.IsInsideTree() ||
                    !screen.IsVisibleInTree() ||
                    !screen.IsTravelEnabled ||
                    screen.IsTraveling)
                {
                    _decisionPending = false;
                    return;
                }

                var selected = points[index];

                if (!GodotObject.IsInstanceValid(selected) ||
                    !selected.IsInsideTree() ||
                    !selected.IsEnabled)
                {
                    _decisionPending = false;
                    return;
                }

                MainFile.Logger.Info(
                    $"MAP: Traveling to row " +
                    $"{selected.Point.coord.row}, " +
                    $"column {selected.Point.coord.col}, " +
                    $"type {selected.Point.PointType}"
                );

                selected.ForceClick();
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"MAP ERROR: {ex}");
            if (generation == _generation) _decisionPending = false;
        }
    }
}

