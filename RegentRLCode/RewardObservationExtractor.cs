
using System.Linq;
using MegaCrit.Sts2.Core.Rewards;

namespace RegentRL.RegentRLCode;

public static class RewardObservationExtractor
{
    public static RewardObservation Extract(RewardsSet set)
    {
        var observation = new RewardObservation
        {
            RewardSetId = set.Id
        };

        for (int i = 0; i < set.Rewards.Count; i++)
        {
            Reward reward = set.Rewards[i];

            var option = new RewardOptionObservation
            {
                RewardIndex = i,
                Type = reward switch
                {
                    GoldReward => "Gold",
                    CardReward => "Card",
                    PotionReward => "Potion",
                    RelicReward => "Relic",
                    CardRemovalReward => "RemoveCard",
                    SpecialCardReward => "SpecialCard",
                    LinkedRewardSet => "Linked",
                    _ => reward.GetType().Name
                },
                SuccessfullySelected = reward.SuccessfullySelected
            };

            switch (reward)
            {
                case GoldReward gold:
                    option.GoldAmount = gold.Amount;
                    break;

                case CardReward cards:
                    option.CardIds = cards.Cards
                        .Select(card => card.Id.Entry)
                        .ToList();
                    break;

                case PotionReward potion:
                    option.ItemId = potion.Potion?.Id.Entry;
                    break;

                case RelicReward relic:
                    option.ItemId = relic.Relic?.Id.Entry;
                    break;
            }

            observation.Rewards.Add(option);
        }

        return observation;
    }
}

