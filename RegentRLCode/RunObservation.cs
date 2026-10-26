using System.Collections.Generic;
using System.Linq;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Context;
using MegaCrit.Sts2.Core.Runs;

namespace RegentRL.RegentRLCode;

// Information already available to a player. No RNG seeds or hidden draw order.
public sealed class RunObservation
{
    public int Hp { get; set; }
    public int MaxHp { get; set; }
    public int Gold { get; set; }
    public List<RunCardObservation> Deck { get; set; } = new();
    public List<string> Relics { get; set; } = new();
    public List<RunPotionObservation> PotionSlots { get; set; } = new();
}

public sealed class RunCardObservation
{
    public string CardId { get; set; } = "";
    public int UpgradeLevel { get; set; }
}

public sealed class RunPotionObservation
{
    public int Slot { get; set; }
    public string? PotionId { get; set; }
}

public static class RunObservationExtractor
{
    // Safe for a decision that can occur outside active combat.
    // Never infer hidden RNG, seed, or draw order.
    public static RunObservation? TryExtractLocal()
    {
        try
        {
            var player = LocalContext.GetMe(RunManager.Instance.DebugOnlyGetState());
            return player == null ? null : Extract(player);
        }
        catch (System.Exception ex)
        {
            MainFile.Logger.Info($"RUN OBSERVATION: Could not capture local player: {ex.Message}");
            return null;
        }
    }

    public static RunObservation Extract(Player player)
    {
        return new RunObservation
        {
            Hp = player.Creature.CurrentHp,
            MaxHp = player.Creature.MaxHp,
            Gold = player.Gold,
            Deck = player.Deck.Cards.Select(card => new RunCardObservation
            {
                CardId = card.Id.Entry,
                UpgradeLevel = card.CurrentUpgradeLevel
            }).ToList(),
            Relics = player.Relics.Select(relic => relic.Id.Entry).ToList(),
            PotionSlots = player.PotionSlots.Select((potion, index) => new RunPotionObservation
            {
                Slot = index,
                PotionId = potion?.Id.Entry
            }).ToList()
        };
    }
}
