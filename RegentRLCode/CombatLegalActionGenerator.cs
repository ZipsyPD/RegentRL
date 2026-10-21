using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

public static class CombatLegalActionGenerator
{
    public static List<CombatLegalAction> Generate(
        CombatObservation observation)
    {
        var actions = new List<CombatLegalAction>();

        foreach (var card in observation.Hand)
        {
            if (!card.Playable)
                continue;

            if (card.NoTargetLegal)
            {
                actions.Add(new CombatLegalAction
                {
                    Type = "PlayCard",
                    HandIndex = card.HandIndex,
                    CardId = card.Id,
                    TargetId = null
                });
            }

            foreach (var targetId in card.LegalEnemyTargets)
            {
                if (!targetId.HasValue)
                    continue;

                actions.Add(new CombatLegalAction
                {
                    Type = "PlayCard",
                    HandIndex = card.HandIndex,
                    CardId = card.Id,
                    TargetId = targetId
                });
            }
        }

        // Ending the turn is always an available decision
        // in our initial player-turn action model.
        actions.Add(new CombatLegalAction
        {
            Type = "EndTurn"
        });

        return actions;
    }
}

