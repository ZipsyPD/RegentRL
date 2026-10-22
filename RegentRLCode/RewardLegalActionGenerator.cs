using System.Collections.Generic;
using MegaCrit.Sts2.Core.Rewards;

namespace RegentRL.RegentRLCode;

public static class RewardLegalActionGenerator
{
    public static List<RewardActionObservation> Generate(
        RewardsSet set)
    {
        var actions = new List<RewardActionObservation>();

        for (int i = 0; i < set.Rewards.Count; i++)
        {
            Reward reward = set.Rewards[i];

            // Already collected rewards cannot be collected again.
            if (reward.SuccessfullySelected)
                continue;

            // Only offer actions for fully generated rewards.
            if (!reward.IsPopulated)
                continue;

            actions.Add(new RewardActionObservation
            {
                Type = "SelectReward",
                RewardIndex = i
            });
        }

        // Leaving rewards behind is only allowed when
        // STS2 permits skipping the set.
        if (!set.DisallowSkipping)
        {
            actions.Add(new RewardActionObservation
            {
                Type = "SkipRemainingRewards",
                RewardIndex = null
            });
        }

        return actions;
    }
}

