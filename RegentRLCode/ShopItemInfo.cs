using MegaCrit.Sts2.Core.Entities.Merchant;

namespace RegentRL.RegentRLCode;

// Resolve a native merchant entry to an item identity before it is purchased.
public static class ShopItemInfo
{
    public static string? Id(MerchantEntry entry) => entry switch
    {
        MerchantCardEntry card => card.CreationResult?.Card.Id.Entry,
        MerchantRelicEntry relic => relic.Model?.Id.Entry,
        MerchantPotionEntry potion => potion.Model?.Id.Entry,
        _ => null
    };

    public static string? Name(MerchantEntry entry) => entry switch
    {
        MerchantCardEntry card => card.CreationResult?.Card.Title,
        MerchantRelicEntry relic => relic.Model?.Title.GetFormattedText(),
        MerchantPotionEntry potion => potion.Model?.Title.GetFormattedText(),
        _ => null
    };
}
