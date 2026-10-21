using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

// Information sent to the Python agent when a decision is needed.
public class CombatDecisionRequest
{
    public long DecisionId { get; set; }

    public CombatObservation Observation { get; set; } = new();

    public List<CombatLegalAction> LegalActions { get; set; } = new();
}
