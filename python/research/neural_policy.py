"""Minimal real-ST​S2 behavior-cloning policy. Fixed reproducible feature hashing."""
from __future__ import annotations
try:
    from .fullrun_encoder import encode as fullrun_encode, FEATURES as FULLRUN_FEATURES
    from .fullrun_encoder_v7 import encode as fullrun_encode_v7, FEATURES as FULLRUN_V7_FEATURES
    from .fullrun_encoder_v6 import encode as fullrun_encode_v6, FEATURES as FULLRUN_V6_FEATURES
    from .fullrun_encoder_v5 import FEATURES as FULLRUN_V5_FEATURES
    from .fullrun_encoder_v5 import encode as fullrun_encode_v5
except ImportError:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("regentrl_fullrun_encoder", __import__("pathlib").Path(__file__).with_name("fullrun_encoder.py"))
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    fullrun_encode = _mod.encode
    FULLRUN_FEATURES = _mod.FEATURES
    _sp7 = _ilu.spec_from_file_location("regentrl_fullrun_encoder_v7", __import__("pathlib").Path(__file__).with_name("fullrun_encoder_v7.py"))
    _m7 = _ilu.module_from_spec(_sp7)
    _sp7.loader.exec_module(_m7)
    fullrun_encode_v7 = _m7.encode
    FULLRUN_V7_FEATURES = _m7.FEATURES
    _sp6 = _ilu.spec_from_file_location("regentrl_fullrun_encoder_v6", __import__("pathlib").Path(__file__).with_name("fullrun_encoder_v6.py"))
    _m6 = _ilu.module_from_spec(_sp6)
    _sp6.loader.exec_module(_m6)
    fullrun_encode_v6 = _m6.encode
    FULLRUN_V6_FEATURES = _m6.FEATURES
    _sp5 = _ilu.spec_from_file_location("regentrl_fullrun_encoder_v5", __import__("pathlib").Path(__file__).with_name("fullrun_encoder_v5.py"))
    _m5 = _ilu.module_from_spec(_sp5)
    _sp5.loader.exec_module(_m5)
    fullrun_encode_v5 = _m5.encode
    FULLRUN_V5_FEATURES = _m5.FEATURES
try:
    from .fullrun_encoder_v3 import encode as fullrun_encode_v3
except ImportError:
    import importlib.util as _ilu3
    _sp3 = _ilu3.spec_from_file_location("regentrl_fullrun_encoder_v3", __import__("pathlib").Path(__file__).with_name("fullrun_encoder_v3.py"))
    _m3 = _ilu3.module_from_spec(_sp3)
    _sp3.loader.exec_module(_m3)
    fullrun_encode_v3 = _m3.encode
import hashlib
import json
import math
from pathlib import Path

FEATURES = 256

def _hash(name: str) -> int:
    return int.from_bytes(hashlib.blake2b(name.encode('utf-8'), digest_size=8).digest(), 'little') % FEATURES

def _put(out: list[float], key: str, val: float = 1.0):
    out[_hash(key)] += float(val)

def encode(request: dict, action: dict) -> list[float]:
    """Only information sent at decision time, never NextObservation or outcome."""
    x = [0.0] * FEATURES
    _put(x, 'bias')
    _put(x, 'phase:' + str(request.get('Type', 'Unknown')))
    run = request.get('RunObservation') or {}
    for name,scale in (('Hp',100),('MaxHp',100),('Gold',200)):
        try: _put(x, 'run:'+name, float(run.get(name,0))/scale)
        except (TypeError,ValueError): pass
    for card in run.get('Deck',[]) or []:
        if isinstance(card,dict): _put(x, 'deck:'+str(card.get('CardId','?')), .1)
    for relic in run.get('Relics',[]) or []: _put(x,'relic:'+str(relic),.3)
    for potion in run.get('PotionSlots',[]) or []:
        if isinstance(potion,dict) and potion.get('PotionId'): _put(x,'potion:'+str(potion['PotionId']), .3)
    # Distinguish actions by actual content, NOT by their list index.
    for k,v in sorted(action.items()):
        if v is None: continue
        if isinstance(v, (str,bool)):
            _put(x,'action:'+k+'='+str(v))
        elif isinstance(v,(int,float)):
            _put(x,'action:'+k+'='+str(v))
            if k in ('Cost','EnergyCost','Damage','Row','Column'):
                _put(x,'numeric:'+k,float(v)/20)
        elif isinstance(v,list):
            for item in v: _put(x,'action:'+k+'='+str(item),.2)
    # Include selected combat information when present; never future data.
    obs = request.get('Observation') or request.get('CombatObservation') or {}
    if isinstance(obs,dict):
        for k in ('Energy','Stars','PlayerHp','PlayerBlock'):
            if isinstance(obs.get(k),(int,float)):_put(x,'combat:'+k,float(obs[k])/20)
    # Compress counts without exploding hashed collisions.
    return [math.tanh(v) for v in x]


def make_model(features=FEATURES):
    import torch.nn as nn
    return nn.Sequential(nn.Linear(features,128),nn.Tanh(),nn.Linear(128,64),nn.Tanh(),nn.Linear(64,1))

class NeuralPolicy:
    def __init__(self, checkpoint: str):
        import torch
        self.torch = torch
        self.model = None
        try:
            blob=torch.load(checkpoint,map_location='cpu',weights_only=True)
        except TypeError:
            raise RuntimeError('PyTorch with weights_only loading is required')
        if blob.get('feature_version') not in (1, 3, 5, 6, 7, 8):
            raise ValueError('Incompatible feature encoder version')
        self.feature_version = blob['feature_version']
        self.model = make_model({5:FULLRUN_V5_FEATURES, 6:FULLRUN_V6_FEATURES, 7:FULLRUN_V7_FEATURES, 8:FULLRUN_FEATURES}.get(self.feature_version, FEATURES))
        self.model.load_state_dict(blob['state_dict'])
        self.model.eval()
    def choose(self, request:dict) -> dict:
        actions=request.get('LegalActions')
        if not isinstance(actions,list) or not actions: raise ValueError('No legal actions')
        feats=self.torch.tensor([(fullrun_encode(request,a) if self.feature_version == 8 else fullrun_encode_v7(request,a) if self.feature_version == 7 else fullrun_encode_v6(request,a) if self.feature_version == 6 else fullrun_encode_v5(request,a) if self.feature_version == 5 else fullrun_encode_v3(request,a) if self.feature_version == 3 else encode(request,a)) for a in actions],dtype=self.torch.float32)
        with self.torch.no_grad(): scores=self.model(feats).view(-1)
        idx=int(scores.argmax().item())
        return {'DecisionId':request['DecisionId'],'ActionIndex':idx}

    def select_cards(self,request):
        """Return protocol-compatible index list; rank live card candidates with v5."""
        if self.feature_version not in (5, 6, 7, 8):
            raise ValueError('Neural CardSelection requires encoder v5')
        opts=request.get('Options') or []
        details=request.get('OptionDetails') or []
        low=max(0,int(request.get('MinSelect',0)))
        high=min(len(opts),int(request.get('MaxSelect',len(opts))))
        if low>high:raise ValueError('Invalid CardSelection limits')
        candidates=[]
        for i,opt in enumerate(opts):
            detail=next((d for d in details if isinstance(d,dict) and d.get('Index')==i),None)
            if detail is None:detail={'Index':i,'CardId':opt}
            candidates.append({'Type':'SelectCard','CardId':detail.get('CardId',str(opt)),
                               'Index':i,'UpgradeLevel':detail.get('UpgradeLevel',0),
                               'OptionDetail':detail})
        if not candidates:return {'DecisionId':request['DecisionId'],'SelectedIndices':[]}
        if self.feature_version == 8:
            # Match simulator's sequential choose/confirm protocol, but return
            # one native subset. Only add candidates; no toggling selected cards.
            import copy
            current = copy.deepcopy(request)
            selected=[]
            minimum=low
            for _ in range(high+1):
                current['SelectedIndices']=selected[:]
                legal=[]
                if len(selected)>=minimum:
                    legal.append({'Type':'ConfirmSelection'})
                if len(selected)<high:
                    legal.extend(c for i,c in enumerate(candidates) if i not in selected)
                if not legal:
                    break
                fs=self.torch.tensor([fullrun_encode(current,a) for a in legal],dtype=self.torch.float32)
                with self.torch.no_grad():scores=self.model(fs).view(-1)
                best=legal[int(scores.argmax().item())]
                if best['Type']=='ConfirmSelection':break
                selected.append(int(best['Index']))
            if not low<=len(selected)<=high:
                raise RuntimeError('V8 selection did not satisfy limits')
            return {'DecisionId':request['DecisionId'],'SelectedIndices':sorted(selected)}
        fs=self.torch.tensor([(fullrun_encode(request,a) if self.feature_version == 8 else fullrun_encode_v7(request,a) if self.feature_version == 7 else fullrun_encode_v6(request,a) if self.feature_version == 6 else fullrun_encode_v5(request,a)) for a in candidates],dtype=self.torch.float32)
        with self.torch.no_grad():scores=self.model(fs).flatten().tolist()
        # Count policy is not trained on real multi-select constraints yet;
        # preserve old valid default count while learning which cards to take.
        count=high
        chosen=sorted(range(len(candidates)),key=lambda i:(-scores[i],i))[:count]
        return {'DecisionId':request['DecisionId'],'SelectedIndices':sorted(chosen)}
