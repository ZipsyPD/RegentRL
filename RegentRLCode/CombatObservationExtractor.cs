using System.Linq;

using MegaCrit.Sts2.Core.MonsterMoves.Intents;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Players;

namespace RegentRL.RegentRLCode;

public static class CombatObservationExtractor
{
    public static CombatObservation Extract(
        CombatState state,
        Player player)
    {
        var creature = player.Creature;
        var combat = player.PlayerCombatState
            ?? throw new System.InvalidOperationException(
                "Player combat state unavailable!"
            );

        var observation = new CombatObservation
        {
            Turn = combat.TurnNumber,
            Player = new PlayerObservation
            {
                Hp = creature.CurrentHp,
                MaxHp = creature.MaxHp,
                Block = creature.Block,
                Energy = combat.Energy,
                MaxEnergy = combat.MaxEnergy,
                Stars = combat.Stars
            }
        };
        // Copy Regent's active powers into observation
        foreach (var power in creature.Powers)
        {
            observation.Player.Powers.Add(new PowerObservation
                    {
                    Id = power.Id.Entry,
                    Amount = power.Amount
                    });
        }

        // Copy enemy information into DTO
        foreach (var enemy in state.Enemies)
        {
            var enemyObservation = new EnemyObservation 
            {
                CombatId = enemy.CombatId,
                Name = enemy.Name,
                Hp = enemy.CurrentHp,
                MaxHp = enemy.MaxHp,
                Block = enemy.Block
                };

            foreach (var power in enemy.Powers)
            {
                enemyObservation.Powers.Add(new PowerObservation
                        {
                        Id = power.Id.Entry,
                        Amount = power.Amount
                        });
            }

            // Visible enemy intents
            if (enemy.Monster != null)
            {
                foreach (var intent in enemy.Monster.NextMove.Intents)
                {
                    var intentObservation = new IntentObservation
                    {
                        Type = intent.IntentType.ToString()
                    };

                    if (intent is AttackIntent attack)
                    {
                        intentObservation.DamagePerHit = attack.GetSingleDamage(
                                state.Players.Select(p => p.Creature),
                                enemy
                                );

                        intentObservation.Hits = attack.Repeats;
                    }

                    enemyObservation.Intents.Add(intentObservation);
                }
            }
            observation.Enemies.Add(enemyObservation);
        }

        // Copy cards in hand and their legal targets
        for (int i = 0; i < combat.Hand.Cards.Count; i++)
        {
            var card = combat.Hand.Cards[i];

            var cardObservation = new CardObservation
            {
                HandIndex = i,
                Id = card.Id.Entry,
                UpgradeLevel = card.CurrentUpgradeLevel,
                EnergyCost = card.EnergyCost.GetAmountToSpend(),
                StarCost = card.CurrentStarCost,
                TargetType = card.TargetType.ToString(),
                Playable = card.CanPlay(),
                NoTargetLegal = card.CanPlayTargeting(null)
            };

            if (cardObservation.Playable)
            {
                foreach (var enemy in state.Enemies)
                {
                    if (card.CanPlayTargeting(enemy))
                    {
                        cardObservation.LegalEnemyTargets.Add(enemy.CombatId);
                    }
                }
            }
            observation.Hand.Add(cardObservation);
        }

        return observation;
    }
}

