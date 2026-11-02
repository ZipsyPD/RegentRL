using System;
using System.Collections.Generic;
using System.Linq;

using Godot;
using HarmonyLib;

using MegaCrit.Sts2.Core.Context;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Rewards;
using MegaCrit.Sts2.Core.Nodes.Screens;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;
using MegaCrit.Sts2.Core.Rewards;

namespace RegentRL.RegentRLCode;

// Native UI execution: Python chooses a reward; the game's NRewardButton
// claims it, emits RewardClaimed, and removes itself from NRewardsScreen.
[HarmonyPatch(typeof(NRewardsScreen))]
public static class NativeRewardScreenPatch
{
    private sealed class ScreenState
    {
        public bool AwaitingPython;
        public bool ProceedSent;
        public NRewardButton? LastClicked;
        public ulong LastClickAt;
    }

    private static readonly Dictionary<ulong, ScreenState> States = new();
    private static readonly System.Reflection.FieldInfo? RewardsSetField =
        AccessTools.Field(typeof(NRewardsScreen), "_rewardsSet");

    [HarmonyPostfix]
    [HarmonyPatch(nameof(NRewardsScreen.AfterOverlayClosed))]
    public static void Closed(NRewardsScreen __instance)
    {
        States.Remove(__instance.GetInstanceId());
    }

    [HarmonyPostfix]
    [HarmonyPatch(nameof(NRewardsScreen._Process))]
    public static void Tick(NRewardsScreen __instance)
    {
        // _Process runs on the Godot main thread. UI inspection and ForceClick
        // must not happen on a socket continuation thread.
        try
        {
            var screen = __instance;
            if (!GodotObject.IsInstanceValid(screen) || !screen.IsInsideTree() ||
                !screen.IsVisibleInTree() || NOverlayStack.Instance?.Peek() != screen)
                return;

            ulong id = screen.GetInstanceId();
            if (!States.TryGetValue(id, out var state))
                States[id] = state = new ScreenState();

            if (state.AwaitingPython || state.ProceedSent)
                return;

            // Wait until the claimed reward's *button* is removed by the game's
            // RewardClaimed handler, not merely until SuccessfullySelected flips.
            if (state.LastClicked != null)
            {
                if (GodotObject.IsInstanceValid(state.LastClicked) &&
                    state.LastClicked.IsInsideTree())
                {
                    if (Time.GetTicksMsec() - state.LastClickAt > 12000)
                    {
                        MainFile.Logger.Info("REGENTRL UI REWARD: Claim did not dismiss button; manual intervention required.");
                        state.ProceedSent = true; // fail closed; don't double-claim
                    }
                    return;
                }
                state.LastClicked = null;
            }

            if (screen.IsComplete)
            {
                var proceed = screen.GetNodeOrNull<NProceedButton>("ProceedButton");
                if (proceed != null && proceed.IsEnabled)
                {
                    state.ProceedSent = true;
                    MainFile.Logger.Info("REGENTRL UI REWARD: Clicking native Proceed");
                    proceed.ForceClick();
                }
                return;
            }

            if (RewardsSetField?.GetValue(screen) is not RewardsSet set)
                return;

            var buttons = FindRewardButtons(screen);
            var legalButtons = buttons.Where(b => b.IsEnabled &&
                b.Reward != null && !b.Reward.SuccessfullySelected &&
                b.Reward.IsPopulated).ToList();

            if (legalButtons.Count == 0)
                return;
            bool hasPotionSlots =
                LocalContext.GetMe(
                    RunManager.Instance.DebugOnlyGetState()
                )?.HasOpenPotionSlots ?? false;

            var actions = RewardLegalActionGenerator.Generate(set)
                .Where(action =>
                    action.Type != "SelectReward" ||
                    !action.RewardIndex.HasValue ||
                    action.RewardIndex.Value < 0 ||
                    action.RewardIndex.Value >= set.Rewards.Count ||
                    set.Rewards[action.RewardIndex.Value] is not PotionReward ||
                    hasPotionSlots
                )
                .ToList();

            if (actions.Count == 0)
            {
                MainFile.Logger.Info(
                    "REGENTRL UI REWARD: No actionable rewards"
                );
                return;
            }

            var request = new RewardDecisionRequest
            {
                DecisionId = CardSelectionDecisionIds.Next(),
                RunObservation = RunObservationExtractor.TryExtractLocal(),
                Observation = RewardObservationExtractor.Extract(set),
                LegalActions = actions
            };
            state.AwaitingPython = true;
            MainFile.Logger.Info($"REGENTRL UI REWARD: Sending {request.LegalActions.Count} actions to Python");
            _ = RequestAndClick(screen, id, request);
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"REGENTRL UI REWARD TICK ERROR: {ex}");
        }
    }

    private static List<NRewardButton> FindRewardButtons(Node root)
    {
        var buttons = new List<NRewardButton>();
        void Visit(Node node)
        {
            foreach (Node child in node.GetChildren())
            {
                if (child is NRewardButton button)
                    buttons.Add(button);
                Visit(child);
            }
        }
        Visit(root);
        return buttons;
    }

    private static async System.Threading.Tasks.Task RequestAndClick(
        NRewardsScreen screen, ulong screenId, RewardDecisionRequest request)
    {
        try
        {
            var response = await PythonAgentClient.RequestRewardDecisionAsync(request);
            Callable.From(() =>
            {
                if (!States.TryGetValue(screenId, out var state)) return;
                try
                {
                    if (!GodotObject.IsInstanceValid(screen) || !screen.IsInsideTree() ||
                        NOverlayStack.Instance?.Peek() != screen) return;
                    if (response == null || response.DecisionId != request.DecisionId ||
                        response.ActionIndex < 0 || response.ActionIndex >= request.LegalActions.Count)
                        return;

                    var action = request.LegalActions[response.ActionIndex];
                    if (action.Type == "SkipRemainingRewards")
                    {
                        var proceed = screen.GetNodeOrNull<NProceedButton>("ProceedButton");
                        if (proceed != null && proceed.IsEnabled)
                        {
                            state.ProceedSent = true;
                            MainFile.Logger.Info("REGENTRL UI REWARD: Skipping via native Proceed");
                            proceed.ForceClick();
                        }
                        return;
                    }
                    if (action.Type != "SelectReward" || !action.RewardIndex.HasValue)
                        return;
                    if (RewardsSetField?.GetValue(screen) is not RewardsSet set)
                        return;
                    int index = action.RewardIndex.Value;
                    if (index < 0 || index >= set.Rewards.Count) return;
                    Reward target = set.Rewards[index];
                    var button = FindRewardButtons(screen).FirstOrDefault(b =>
                        b.IsEnabled && ReferenceEquals(b.Reward, target));
                    if (button == null)
                    {
                        MainFile.Logger.Info("REGENTRL UI REWARD: No matching enabled reward button");
                        return;
                    }
                    state.LastClicked = button;
                    state.LastClickAt = Time.GetTicksMsec();
                    MainFile.Logger.Info($"REGENTRL UI REWARD: Native click {index} ({target.GetType().Name})");
                    button.ForceClick();
                }
                catch (Exception ex)
                {
                    MainFile.Logger.Info($"REGENTRL UI REWARD CLICK ERROR: {ex}");
                }
                finally
                {
                    state.AwaitingPython = false;
                }
            }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info($"REGENTRL UI REWARD PYTHON ERROR: {ex}");
            Callable.From(() =>
            {
                if (States.TryGetValue(screenId, out var state))
                {
                    state.AwaitingPython = false;
                    state.ProceedSent = true; // fail closed on disconnect
                }
            }).CallDeferred();
        }
    }
}
