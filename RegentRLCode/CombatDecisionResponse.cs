namespace RegentRL.RegentRLCode;

// Response received from the Python agent.
public class CombatDecisionResponse
{
    // Identifies which decision request this response belongs to.
    public long DecisionId { get; set; }

    // Index into the LegalActions list sent with that request.
    public int ActionIndex { get; set; }
}
