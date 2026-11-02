import tempfile
import unittest
from pathlib import Path
from research.combat_ppo import CombatPPO


def req(i):
    return {'Type':'CombatDecision','DecisionId':i,'Observation':{
      'Turn':1,'Player':{'Hp':70,'MaxHp':75,'Energy':3,'Block':0,'Stars':0},
      'Enemies':[{'CombatId':1,'Name':'Example','Hp':20,'MaxHp':30,'Block':0,'Intents':[{'Type':'Attack','DamagePerHit':6,'Hits':1}]}],
      'Hand':[{'HandIndex':0,'Id':'STRIKE_REGENT','Playable':True,'EnergyCost':1}]},
      'LegalActions':[{'Type':'PlayCard','CardId':'STRIKE_REGENT','HandIndex':0,'TargetId':1}, {'Type':'EndTurn'}],
      'RunObservation':{'Hp':70,'MaxHp':75,'Gold':99,'Deck':[],'Relics':[]}}

class PPOTests(unittest.TestCase):
    def test_verified_episode_updates(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ppo.pt';p=CombatPPO(train=True,checkpoint_out=str(path))
            self.assertIn(p.choose(req(1))['ActionIndex'],(0,1))
            p.resolved({'DecisionType':'CombatDecision','DecisionId':1,'Executed':True,'Terminal':False,'NextObservation':req(1)['Observation']})
            p.choose(req(2))
            p.resolved({'DecisionType':'CombatDecision','DecisionId':2,'Executed':True,'Terminal':True,'CombatOutcome':'Win','NextObservation':req(2)['Observation']})
            self.assertEqual(p.updates,1)
            self.assertTrue(path.exists())
            check=CombatPPO(checkpoint=str(path))
            self.assertIn(check.choose(req(3))['ActionIndex'],(0,1))
    def test_incomplete_episode_is_not_trained(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ppo.pt';p=CombatPPO(train=True,checkpoint_out=str(path))
            p.choose(req(1));p.choose(req(2))
            p.resolved({'DecisionType':'CombatDecision','DecisionId':2,'Executed':True,'Terminal':True,'CombatOutcome':'Loss','NextObservation':req(2)['Observation']})
            self.assertEqual(p.updates,0)
            self.assertFalse(path.exists())
if __name__=='__main__':unittest.main()

class LifecycleTests(unittest.TestCase):
    def test_combat_end_arrives_before_last_ack(self):
        with tempfile.TemporaryDirectory() as d:
            p=CombatPPO(train=True, checkpoint_out=str(Path(d)/'ppo.pt'))
            p.combat_started()
            p.choose(req(10));p.choose(req(11))
            p.resolved({'DecisionType':'CombatDecision','DecisionId':10,'Executed':True,'Terminal':False})
            p.combat_ended({'Outcome':'Win'})
            self.assertEqual(p.updates,0)
            p.resolved({'DecisionType':'CombatDecision','DecisionId':11,'Executed':True,'Terminal':False})
            self.assertEqual(p.updates,1)
    def test_new_combat_discards_missing_ack(self):
        with tempfile.TemporaryDirectory() as d:
            p=CombatPPO(train=True,checkpoint_out=str(Path(d)/'ppo.pt'))
            p.choose(req(10));p.combat_ended({'Outcome':'Loss'})
            p.combat_started()
            self.assertEqual(p.updates,0)
            self.assertEqual(len(p.events),0)


class RunEndOrderingTests(unittest.TestCase):
    def test_run_loss_before_combat_end_and_ack_trains(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ppo.pt'
            p=CombatPPO(train=True,checkpoint_out=str(path))
            p.choose(req(76))
            p.run_ended({'Event':'Ended','Outcome':'Loss'})
            self.assertEqual(len(p.events),1)
            p.combat_ended({'Outcome':'Loss'})
            self.assertEqual(p.updates,0)
            p.resolved({'DecisionType':'CombatDecision','DecisionId':76,'Executed':True,
                        'Terminal':True,'CombatOutcome':'Loss'})
            self.assertEqual(p.updates,1)
            self.assertTrue(path.exists())

    def test_abandoned_run_does_not_train(self):
        with tempfile.TemporaryDirectory() as d:
            p=CombatPPO(train=True,checkpoint_out=str(Path(d)/'ppo.pt'))
            p.choose(req(1));p.run_ended({'Event':'Ended','Outcome':'Abandoned'})
            self.assertEqual(p.updates,0)
            self.assertEqual(len(p.events),0)
