using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

public class RewardActionObservation
{
    public string Type { get; set; } = "";
    public int? RewardIndex { get; set; }
}

public class RewardDecisionRequest
{
    public string Type { get; set; } = "RewardDecision";
    public long DecisionId { get; set; }
    public RewardObservation Observation { get; set; } = new();
    public List<RewardActionObservation> LegalActions { get; set; } = new();
}

public class RewardDecisionResponse
{
    public long DecisionId { get; set; }
    public int ActionIndex { get; set; }
}

