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
    public int Floor { get; set; }
    public int Act { get; set; }
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
            var state = RunManager.Instance.DebugOnlyGetState();
            var player = LocalContext.GetMe(state);
            if (player == null) return null;
            var result = Extract(player);
            // Probe public run progression without relying on decompiled private APIs.
            // A missing public property leaves 0, the same missing-data convention
            // used by the simulator's original encoder.
            result.Floor = ReadVisibleInt(state, "TotalFloor", "Floor", "CurrentFloor");
            result.Act = ReadVisibleInt(state, "CurrentActIndex", "ActIndex");
            return result;
        }
        catch (System.Exception ex)
        {
            MainFile.Logger.Info($"RUN OBSERVATION: Could not capture local player: {ex.Message}");
            return null;
        }
    }

    private static int ReadVisibleInt(object state, params string[] names)
    {
        foreach (var name in names)
        {
            try
            {
                var property = state.GetType().GetProperty(name);
                if (property != null && property.CanRead &&
                    property.GetIndexParameters().Length == 0 &&
                    property.GetValue(state) is int value)
                    return value;
                var field = state.GetType().GetField(name);
                if (field?.GetValue(state) is int fieldValue)
                    return fieldValue;
            }
            catch (System.Exception)
            {
                // A version-dependent API must never suppress the entire run observation.
            }
        }
        return 0;
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
