
using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

public class CardSelectionRequest
{
    public string Type { get; set; } = "CardSelection";

    public long DecisionId { get; set; }

    public int MinSelect { get; set; }

    public int MaxSelect { get; set; }

    public List<string> Options { get; set; } = new();
}

