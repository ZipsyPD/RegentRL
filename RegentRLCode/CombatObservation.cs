namespace RegentRL.RegentRLCode;

// Top-level snapshot of the observable combat state
public class CombatObservation
{
    public int Turn { get; set; }
    public PlayerObservation Player { get; set; } = new();
    public List<EnemyObservation> Enemies { get; set; } = new();
    public List<CardObservation> Hand { get; set; } = new();
    public List<PotionObservation> Potions { get; set; } = new();
}

// Player stats and currently available resources
public class PlayerObservation
{
    public int Hp { get; set; }
    public int MaxHp { get; set; }
    public int Block { get; set; }

    public int Energy { get; set; }
    public int MaxEnergy { get; set; }
    public int Stars { get; set; }

    public List<PowerObservation> Powers { get; set; } = new();
}

// Enemy identity, stats, and active powers
public class EnemyObservation
{
    public uint? CombatId { get; set; }
    public string Name { get; set; } = "";

    public int Hp { get; set; }
    public int MaxHp { get; set; }
    public int Block { get; set; }

    public List<PowerObservation> Powers { get; set; } = new();
    public List<IntentObservation> Intents { get; set; } = new();
}

// Buffs and debuffs, including their stack amounts
public class PowerObservation
{
    public string Id { get; set; } = "";
    public int Amount { get; set; }
}

// Publicly visible information about an enemy's next move
public class IntentObservation
{
    public string Type { get; set; } = "";

    // Attack intents only; null for non-attack intent
    public int? DamagePerHit { get; set; }
    public int? Hits { get; set; }
}

// A card currently in Regent's hand
public class CardObservation
{
    public int HandIndex { get; set; }
    public string Id { get; set; } = "";
    public int UpgradeLevel { get; set; }

    public int EnergyCost { get; set; }
    public int StarCost { get; set; }

    public string TargetType { get; set; } = "";
    public bool Playable { get; set; }
    public bool NoTargetLegal { get; set; }

    // Enemies that this card can legally target
    public List<uint?> LegalEnemyTargets { get; set; } = new();
}

// Potions for combat!
public class PotionObservation
{
    public int Slot { get; set; }
    public string Id { get; set; } = "";
    public string Usage { get; set; } = "";
    public string TargetType { get; set; } = "";
    public bool Usable { get; set; }
    public bool NoTargetLegal { get; set; }
    public List<uint> LegalEnemyTargets { get; set; } = new();
}
