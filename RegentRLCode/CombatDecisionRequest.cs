using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

// Information sent to the Python agent when a decision is needed.
public class CombatDecisionRequest
{
    public string Type { get; set; } = "CombatDecision";
    public long DecisionId { get; set; }

    public CombatObservation Observation { get; set; } = new();

    public int ProtocolVersion { get; set; } = 2;
    public RunObservation? RunObservation { get; set; }

    public List<CombatLegalAction> LegalActions { get; set; } = new();
}
