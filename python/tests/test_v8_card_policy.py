"""Live v8 selection behavior uses the same select/confirm actions as training."""
from pathlib import Path
import pytest
from research.neural_policy import NeuralPolicy,make_model
from research import fullrun_encoder as v8
from research import fullrun_encoder_v7 as v7


def request(minimum, maximum):
    return {'Type':'CardSelection','DecisionId':12,'Purpose':'Transform','Source':'Deck',
            'MinSelect':minimum,'MaxSelect':maximum,
            'Options':['STRIKE_REGENT','PILLAR_OF_CREATION','DEFEND_REGENT'],
            'OptionDetails':[{'Index':i,'CardId':cid,'UpgradeLevel':0} for i,cid in enumerate(['STRIKE_REGENT','PILLAR_OF_CREATION','DEFEND_REGENT'])]}


def test_v8_old_checkpoint_and_optional_selection(tmp_path):
    torch=pytest.importorskip('torch')
    for ver,features in ((7,4096),(8,6144)):
        m=make_model(features)
        for p in m.parameters():p.data.zero_()
        path=tmp_path/f'v{ver}.pt'
        torch.save({'feature_version':ver,'state_dict':m.state_dict()},path)
        policy=NeuralPolicy(str(path))
        assert policy.feature_version==ver
        assert policy.model[0].in_features==features
        if ver==8:
            # All-zero scores: confirm has priority when legal, so optional 0-2 is 0.
            assert policy.select_cards(request(0,2))['SelectedIndices']==[]
            assert policy.select_cards(request(1,3))['SelectedIndices']==[0]
            assert policy.select_cards(request(2,2))['SelectedIndices']==[0,1]
            assert policy.select_cards(request(3,3))['SelectedIndices']==[0,1,2]
            assert policy.choose({'Type':'BundleDecision','DecisionId':99,'LegalActions':[{'Type':'ChooseBundle','BundleIndex':0,'CardIds':['X','Y']}]})['ActionIndex']==0


def test_encoder_is_v8_and_v7_stays_frozen():
    assert v8.FEATURE_VERSION==8 and v8.FEATURES==6144
    assert v7.FEATURE_VERSION==7 and v7.FEATURES==4096
