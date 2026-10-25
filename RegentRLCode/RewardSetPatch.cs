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


// Reward selection is driven by the visible NRewardsScreen in
// NativeRewardScreenPatch.cs. Do not call SelectLocalReward directly here:
// doing so bypasses NRewardButton.RewardClaimed and leaves stale UI.
