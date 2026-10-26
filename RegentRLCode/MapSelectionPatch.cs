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

    [HarmonyPatch(typeof(NMapScreen), nameof(NMapScreen.Open))]
    [HarmonyPostfix]
    public static void OnMapOpened(NMapScreen __instance)
    {
        MainFile.Logger.Info("MAP: Open hook fired");
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
        _ = StartDecisionAsync(screen);
    }

    private static async Task StartDecisionAsync(NMapScreen screen)
    {
        // Give the map time to enable travel.
        await Task.Delay(400);
        Callable.From(() =>
        {
            bool valid = GodotObject.IsInstanceValid(screen);
            bool inTree = valid && screen.IsInsideTree();
            bool visible = inTree && screen.IsVisibleInTree();

            MainFile.Logger.Info(
                $"MAP: Readiness check: " +
                $"valid={valid}, " +
                $"insideTree={inTree}, " +
                $"visible={visible}, " +
                $"travelEnabled={(inTree && screen.IsTravelEnabled)}, " +
                $"traveling={(inTree && screen.IsTraveling)}"
            );

            if (!inTree ||
                !visible ||
                !screen.IsTravelEnabled ||
                screen.IsTraveling)
            {
                _decisionPending = false;
                return;
            }

            if (ShopSelectionPatch.IsShopping)
            {
                _decisionPending = false;
                return;
            }

            var points = new List<NMapPoint>();
            CollectPoints(screen, points);

            var legal = points
                .Where(p =>
                    GodotObject.IsInstanceValid(p) &&
                    p.IsInsideTree() &&
                    p.IsEnabled &&
                    p.Visible)
                .OrderBy(p => p.Point.coord.row)
                .ThenBy(p => p.Point.coord.col)
                .ToList();

            if (legal.Count == 0)
            {
                MainFile.Logger.Info(
                    "MAP: No reachable nodes currently available"
                );
                _decisionPending = false;
                return;
            }

            long id = ++_decisionId;

            MainFile.Logger.Info(
                $"MAP: Sending {legal.Count} reachable rooms to Python"
            );

            _ = RequestChoiceAsync(screen, legal, id);
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
        long decisionId)
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
            _decisionPending = false;
        }
    }
}

