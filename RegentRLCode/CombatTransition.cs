using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

public class CombatTransition
{
    public CombatObservation Before { get; set; } = new();

    public CombatObservation After { get; set; } = new();

    public List<CombatActionObservation> Actions { get; set; } = new();

    // True when this transition corresponds to an agent-selected action.
    // False for manual gameplay or transitions without confirmed attribution.
    public bool IsAgentAction { get; set; }

    public bool EndedTurn { get; set; }

    // Whether this transition ended combat.
    // Distinct from EndedTurn, which represents the player's end-turn decision
    public bool Terminal { get; set; }

    // Outcome of the terminal combat: "Win" or "Loss",
    // Empty for ordinary non-terminal transitions.
    public string Outcome { get; set; } = "";
}

public class CombatActionObservation
{
    public string Type { get; set; } = "";

    public string CardId { get; set; } = "";

    public uint? TargetId { get; set; }

    public int? HandIndex { get; set; }
}
