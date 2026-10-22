using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

public class RewardObservation
{
    public int RewardSetId { get; set; }

    public List<RewardOptionObservation> Rewards { get; set; } = new();
}

public class RewardOptionObservation
{
    public int RewardIndex { get; set; }

    public string Type { get; set; } = "";

    public int? GoldAmount { get; set; }

    public string? ItemId { get; set; }

    public List<string> CardIds { get; set; } = new();

    public bool SuccessfullySelected { get; set; }
}

