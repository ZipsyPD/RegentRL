using System;
using System.Linq;
using Godot;

namespace RegentRL.RegentRLCode;

// Only records native execution when a specific selected result is visible in state.
// SceneTreeTimer callbacks run on the Godot main thread. No false positives from clicks.
public static class NoncombatEffectVerifier
{
    public static void ConfirmRelic(SceneTree tree, long decisionId, string beforeRelics)
    {
        ObserveLater(tree, "NeowDecision", decisionId, beforeRelics,
            after => string.Join("|", after.Relics) != beforeRelics);
    }

    public static void ConfirmDeckGain(SceneTree tree, string decisionType, long decisionId,
        RunObservation? before, string[] expectedCardIds)
    {
        if (before == null || expectedCardIds.Length == 0) return;
        ObserveLater(tree, decisionType, decisionId, "", after =>
        {
            // Require all selected cards to appear as an increased multiset count.
            foreach (var cardId in expectedCardIds.Distinct())
            {
                int needed = expectedCardIds.Count(x => x == cardId);
                int oldCount = before.Deck.Count(x => x.CardId == cardId);
                int newCount = after.Deck.Count(x => x.CardId == cardId);
                if (newCount - oldCount < needed) return false;
            }
            return true;
        });
    }

    private static void ObserveLater(SceneTree tree, string decisionType, long decisionId,
        string ignored, Func<RunObservation, bool> predicate, int attempt = 0)
    {
        tree.CreateTimer(0.45).Timeout += () =>
        {
            var after = RunObservationExtractor.TryExtractLocal();
            if (after != null && predicate(after))
                RunLifecycleBridge.SendVerifiedNoncombatAction(decisionType, decisionId, after);
            else if (attempt < 7)
                ObserveLater(tree, decisionType, decisionId, ignored, predicate, attempt + 1);
            else
                MainFile.Logger.Info($"TRACE: {decisionType} {decisionId} has no verified effect; keeping proposal only");
        };
    }
}
