"""Versioned loading and live normalization regressions; no game executable needed."""
import sys
from pathlib import Path

import pytest

top = Path(__file__).resolve().parents[1]
if str(top) not in sys.path:sys.path.insert(0,str(top))
from research import fullrun_encoder_v7 as v7
from research import fullrun_encoder_v5 as v5
from research import fullrun_encoder_v6 as v6
from research.neural_policy import NeuralPolicy, make_model


def test_all_checkpoint_versions_load(tmp_path):
    torch = pytest.importorskip('torch')
    for ver, size in ((5,1536),(6,2048),(7,4096)):
        path=tmp_path/f'v{ver}.pt'
        torch.save({'feature_version':ver,'state_dict':make_model(size).state_dict()},path)
        policy=NeuralPolicy(str(path))
        assert policy.feature_version==ver
        assert policy.model[0].in_features==size
        decision=policy.choose({'Type':'CombatDecision','DecisionId':3,'LegalActions':[{'Type':'EndTurn'}]})
        assert decision == {'DecisionId':3, 'ActionIndex':0}


def test_map_coordinates_and_shop_card_ids():
    run={'Hp':70,'MaxHp':75,'Gold':99}
    def e(p,a):return v7.encode({'Type':p,'RunObservation':run},a)
    assert e('MapDecision',{'Type':'ChooseRoom','Row':3,'Column':0,'RoomType':'Monster'}) == e('MapDecision',{'Type':'SelectMapNode','Row':7,'Option':{'coord':(0,3),'point_type':'MONSTER'}})
    assert e('MapDecision',{'Type':'ChooseRoom','Row':3,'Column':0,'RoomType':'Monster'}) != e('MapDecision',{'Type':'SelectMapNode','Option':{'coord':(1,3),'point_type':'MONSTER'}})
    assert e('ShopDecision',{'Type':'BuyCard','Cost':50,'ItemId':'CARD.FALLING_STAR'}) == e('ShopDecision',{'Type':'BuyItem','Option':{'action':'buy_card','price':50,'card_id':'FALLING_STAR'}})
    assert e('CardRewardDecision',{'Type':'ChooseCard','CardIndex':1,'CardId':'CARD.FALLING_STAR'}) == e('CardRewardDecision',{'Type':'SelectReward','RewardIndex':1,'Option':{'action':'pick_card','index':1,'card_id':'FALLING_STAR'}})


def test_intent_powers_card_costs_and_public_identity():
    from copy import deepcopy
    req={'Type':'CombatDecision', 'Observation':{'Player':{'Hp':65,'MaxHp':75,'Energy':2,'MaxEnergy':3,'Powers':[{'Id':'STRENGTH','Amount':2}]},
         'Enemies':[{'CombatId':81,'MonsterId':'NIBBIT','Hp':17,'MaxHp':20,'Intents':[{'Type':'Attack','DamagePerHit':8,'Hits':2}],'Powers':[]}],
         'Hand':[{'Id':'FALLING_STAR','EnergyCost':1,'StarCost':2,'TargetType':'AnyEnemy'}]},
         'LegalActions':[{'Type':'PlayCard','HandIndex':0,'CardId':'FALLING_STAR','TargetId':81},{'Type':'EndTurn'}]}
    action=req['LegalActions'][0];baseline=v7.encode(req,action)
    assert len(baseline)==4096
    for mutate in (
        lambda r:r['Observation']['Enemies'][0]['Intents'][0].update(DamagePerHit=18),
        lambda r:r['Observation']['Player']['Powers'][0].update(Amount=3),
        lambda r:r['Observation']['Hand'][0].update(StarCost=4),
        lambda r:r['Observation']['Player'].update(MaxEnergy=4),
        lambda r:r['Observation']['Enemies'][0].update(MonsterId='LEAF_SLIME_S'),
    ):
        r=deepcopy(req);mutate(r)
        assert v7.encode(r,action) != baseline
    # Native and simulator legal actions have distinct CombatIds, but the
    # same target slot. Combat instance IDs must never leak into features.
    r=deepcopy(req)
    r['Observation']['Enemies'][0]['CombatId']=567
    r['LegalActions'][0]['TargetId']=567
    assert v7.encode(r,r['LegalActions'][0]) == baseline


def test_old_encoders_are_intact():
    assert v5.FEATURE_VERSION==5 and v5.FEATURES==1536
    assert v6.FEATURE_VERSION==6 and v6.FEATURES==2048
    assert v7.FEATURE_VERSION==7 and v7.FEATURES==4096
