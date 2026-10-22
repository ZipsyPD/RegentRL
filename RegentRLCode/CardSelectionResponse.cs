using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

public class CardSelectionResponse
{
    public long DecisionId { get; set; }

    // Indices into the Options list, not card IDs.
    // This lets us distinguish duplicate cards.
    public List<int> SelectedIndices { get; set; } = new();
}

