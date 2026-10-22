using System;
using System.Linq;
using System.Threading.Tasks;
using HarmonyLib;

using Godot;

using MegaCrit.Sts2.Core.Rewards;
using MegaCrit.Sts2.Core.Multiplayer.Game;
using MegaCrit.Sts2.Core.Runs;

namespace RegentRL.RegentRLCode;

[HarmonyPatch(typeof(RewardsSet), nameof(RewardsSet.Offer))]
public static class RewardSetPatch
{
    [HarmonyPrefix]
    public static void Prefix(RewardsSet __instance)
    {
        MainFile.Logger.Info(
            "REGENTRL REWARDS: Reward set offered."
        );

        MainFile.Logger.Info(
            $"REGENTRL REWARDS: Player {__instance.Player.NetId}"
        );
    }
}

[HarmonyPatch(
    typeof(RewardsSet),
    nameof(RewardsSet.GenerateWithoutOffering)
)]
public static class RewardGenerationPatch
{
    [HarmonyPostfix]
    public static void Postfix(
        RewardsSet __instance,
        ref Task __result)
    {
        __result = LogAfterGeneration(__result, __instance);
    }

    private static async Task LogAfterGeneration(
        Task original,
        RewardsSet set)
    {
        await original;

        var observation = RewardObservationExtractor.Extract(set);

        MainFile.Logger.Info(
                $"REGENTRL REWARD OBSERVATION: SetId={observation.RewardSetId}, " +
                $"Options={observation.Rewards.Count}"
                );

        foreach (var reward in observation.Rewards)
        {
            MainFile.Logger.Info(
                $"REGENTRL REWARD OBSERVATION: " +
                $"Index={reward.RewardIndex}, " +
                $"Type={reward.Type}, " +
                $"Gold={reward.GoldAmount}, " +
                $"Item={reward.ItemId}, " +
                $"Cards=[{string.Join(", ", reward.CardIds)}], " +
                $"Selected={reward.SuccessfullySelected}"
            );
        }

        MainFile.Logger.Info(
            $"REGENTRL REWARDS READY: {set.Rewards.Count} rewards"
        );

        foreach (var reward in set.Rewards)
        {
            string details = reward switch
            {
                GoldReward gold =>
                    $"Gold: {gold.Amount}",

                PotionReward potion =>
                    $"Potion: {potion.Potion?.Id.Entry}",

                RelicReward relic =>
                    $"Relic: {relic.Relic?.Id.Entry}",

                CardReward cards =>
                    "Cards: " + string.Join(
                        ", ",
                        cards.Cards.Select(c => c.Id.Entry)
                    ),

                _ => reward.GetType().Name
            };

            MainFile.Logger.Info(
                $"REGENTRL REWARD OPTION: {details}"
            );
        }
    }
}


[HarmonyPatch(
    typeof(RewardsSetSynchronizer),
    nameof(RewardsSetSynchronizer.BeginRewardsSet)
)]
public static class RewardSetRegisteredPatch
{
    [HarmonyPostfix]
    public static void Postfix(RewardsSet set)
    {
        MainFile.Logger.Info(
            $"REGENTRL REWARD SET REGISTERED: SetId={set.Id}"
        );

        _ = TestRewardDecisionAsync(set);
    }

    private static async Task TestRewardDecisionAsync(RewardsSet set)
    {
        try
        {
            var request = new RewardDecisionRequest
            {
                DecisionId = CardSelectionDecisionIds.Next(),
                Observation = RewardObservationExtractor.Extract(set),
                LegalActions = RewardLegalActionGenerator.Generate(set)
            };

            MainFile.Logger.Info(
                $"REGENTRL PYTHON REWARD REQUEST: " +
                $"DecisionId={request.DecisionId}, " +
                $"Actions={request.LegalActions.Count}"
            );

            var response =
                await PythonAgentClient.RequestRewardDecisionAsync(request);

            if (response == null ||
                response.DecisionId != request.DecisionId ||
                response.ActionIndex < 0 ||
                response.ActionIndex >= request.LegalActions.Count)
            {
                MainFile.Logger.Info(
                    "REGENTRL: Invalid Python reward response."
                );
                return;
            }

            var action = request.LegalActions[response.ActionIndex];

            MainFile.Logger.Info(
                $"REGENTRL PYTHON REWARD CHOICE: " +
                $"Type={action.Type}, " +
                $"RewardIndex={action.RewardIndex}"
            );

            // The socket response may arrive on a background thread.
            // Dispatch game interaction back to Godot's main thread.
            Callable.From(() =>
                    {
                        _= ExecuteRewardChoiceAsync(set, action);
                    }).CallDeferred();
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info(
                $"REGENTRL REWARD ERROR: {ex}"
            );
        }
    }

    private static async Task ExecuteRewardChoiceAsync(
        RewardsSet set,
        RewardActionObservation action)
    {
        try
        {
            var synchronizer =
                RunManager.Instance.RewardsSetSynchronizer;

            if (synchronizer.IsRewardsSetCompleted(set))
            {
                MainFile.Logger.Info(
                    "REGENTRL REWARD: Set already completed."
                );
                return;
            }

            if (action.Type != "SelectReward" ||
                !action.RewardIndex.HasValue)
            {
                MainFile.Logger.Info(
                    "REGENTRL REWARD: Skipping unsupported test action."
                );
                return;
            }

            int index = action.RewardIndex.Value;

            if (index < 0 || index >= set.Rewards.Count)
            {
                MainFile.Logger.Info(
                    "REGENTRL REWARD: Invalid reward index."
                );
                return;
            }

            Reward reward = set.Rewards[index];

            if (reward.SuccessfullySelected || !reward.IsPopulated)
            {
                MainFile.Logger.Info(
                    "REGENTRL REWARD: Reward no longer available."
                );
                return;
            }

            MainFile.Logger.Info(
                $"REGENTRL REWARD EXECUTING: " +
                $"Index={index}, Type={reward.GetType().Name}"
            );

            bool success = await synchronizer.SelectLocalReward(reward);

            MainFile.Logger.Info(
                $"REGENTRL REWARD EXECUTED: Success={success}"
            );
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info(
                $"REGENTRL REWARD EXECUTION ERROR: {ex}"
            );
        }
    }
}

