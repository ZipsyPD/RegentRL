namespace RegentRL.RegentRLCode;

// One action the RL agent is allowed to choose.
public class CombatLegalAction
{
    public string Type { get; set; } = "";

    // Identifies the specific card in the current hand.
    // Important because multiple cards can have the same ID.
    public int? HandIndex { get; set; }

    public string CardId { get; set; } = "";

    // Null for cards that do not require a creature target.
    public uint? TargetId { get; set; }
}
