using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

public class CardSelectionExperience
{
    // Which Python selection request this represents.
    public long DecisionId { get; set; }

    // Which cards were available to select.
    public List<string> Options { get; set; } = new();

    // Legal selection count constraints.
    public int MinSelect { get; set; }
    public int MaxSelect { get; set; }

    // The indices Python actually selected.
    public List<int> SelectedIndices { get; set; } = new();

    // Purpose for RL training
    public string Purpose { get; set; } = "Unknown";
    public string Source { get; set; } = "Unknown";
}

