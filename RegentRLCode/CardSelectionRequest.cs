
using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

public class CardSelectionRequest
{
    public string Type { get; set; } = "CardSelection";

    public int ProtocolVersion { get; set; } = 1;

    public long DecisionId { get; set; }

    public RunObservation? RunObservation { get; set; }

    public int MinSelect { get; set; }

    public int MaxSelect { get; set; }

    public List<string> Options { get; set; } = new();

    // Additional structured data; Options remains for existing Python clients.
    public List<CardSelectionOption> OptionDetails { get; set; } = new();

    // Purpose for training
    public string Purpose { get; set; } = "Unknown";

    public string Source { get; set; } = "Unknown";
}


public class CardSelectionOption
{
    public int Index { get; set; }
    public string CardId { get; set; } = "";
    public int UpgradeLevel { get; set; }
}
