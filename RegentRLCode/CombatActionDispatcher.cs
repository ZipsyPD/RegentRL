using System.Linq;

using MegaCrit.Sts2.Core.GameActions;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Players;

namespace RegentRL.RegentRLCode;

// Validates and executes actions selected by the RL agent.
public static class CombatActionDispatcher
{
    public static bool TryExecute(
        CombatState state,
        Player player,
        CombatLegalAction action)
    {

        if (action.Type == "EndTurn")
        {
            if (!CombatManager.Instance.IsInProgress ||
                    state.CurrentSide != CombatSide.Player)
                return false;

            var playerCombat = player.PlayerCombatState;
            if (playerCombat == null)
                return false;

            RunManager.Instance.ActionQueueSynchronizer.RequestEnqueue(
                    new EndPlayerTurnAction(player, playerCombat.TurnNumber)
                    );

            return true;
        }

        if (action.Type != "PlayCard")
            return false;

        if (!CombatManager.Instance.IsInProgress ||
                state.CurrentSide != CombatSide.Player ||
                !action.HandIndex.HasValue)
            return false;

        var combat = player.PlayerCombatState;
        if (combat == null)
            return false;

        int index = action.HandIndex.Value;

        if (index < 0 || index >= combat.Hand.Cards.Count)
            return false;

        var card = combat.Hand.Cards[index];

        // Reject actions whose card no longer matches the observation
        if (card.Id.Entry != action.CardId || !card.CanPlay())
            return false;

        var target = action.TargetId.HasValue
            ? state.Enemies.FirstOrDefault(enemy =>
                    enemy.CombatId == action.TargetId.Value)
            : null;

        // Reject missing targets and illegal targeting.
        if (action.TargetId.HasValue && target == null)
            return false;

        if (!card.CanPlayTargeting(target))
            return false;

        RunManager.Instance.ActionQueueSynchronizer.RequestEnqueue(
                new PlayCardAction(card, target)
                );

        return true;
    }
}
