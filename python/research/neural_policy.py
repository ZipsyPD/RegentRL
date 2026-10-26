"""Minimal real-ST​S2 behavior-cloning policy. Fixed reproducible feature hashing."""
from __future__ import annotations
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


def make_model():
    import torch.nn as nn
    return nn.Sequential(nn.Linear(FEATURES,128),nn.Tanh(),nn.Linear(128,64),nn.Tanh(),nn.Linear(64,1))

class NeuralPolicy:
    def __init__(self, checkpoint: str):
        import torch
        self.torch = torch
        self.model = make_model()
        try:
            blob=torch.load(checkpoint,map_location='cpu',weights_only=True)
        except TypeError:
            raise RuntimeError('PyTorch with weights_only loading is required')
        if blob.get('feature_version') != 1:
            raise ValueError('Incompatible feature encoder version')
        self.model.load_state_dict(blob['state_dict'])
        self.model.eval()
    def choose(self, request:dict) -> dict:
        actions=request.get('LegalActions')
        if not isinstance(actions,list) or not actions: raise ValueError('No legal actions')
        feats=self.torch.tensor([encode(request,a) for a in actions],dtype=self.torch.float32)
        with self.torch.no_grad(): scores=self.model(feats).view(-1)
        idx=int(scores.argmax().item())
        return {'DecisionId':request['DecisionId'],'ActionIndex':idx}
