"""RegentRL v8 model-only card-choice contract.

v7 remains available unchanged for old checkpoints. The v8 tail adds visible
card reward, selection, bundle and event metadata. It never reads outcomes,
future draws or private RNG.
"""
from __future__ import annotations
import math
try:
    from . import fullrun_encoder_v7 as legacy
except ImportError:  # Direct file loading by the legacy server adapter.
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('regentrl_v7_compat',Path(__file__).with_name('fullrun_encoder_v7.py'))
    legacy=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)

FEATURE_VERSION=8
FEATURES=6144

def _dict(v):return v if isinstance(v,dict) else {}
def _list(v):return v if isinstance(v,(list,tuple)) else []
def _id(v):return legacy._id(v)
def _num(v):return legacy._num(v)

def _event_id(value):
    # C# concrete event class names often end in EventModel while simulator
    # event_id uses SCREAMING_SNAKE_CASE. Use only the visible identity.
    text=str(value or '')
    for suffix in ('EventModel','Model','Event'):
        if text.lower().endswith(suffix.lower()):
            text=text[:-len(suffix)]
            break
    return ''.join(ch for ch in text if ch.isalnum()).upper()
def _get(a,b,*keys):
    for key in keys:
        if a.get(key) is not None:return a[key]
        if b.get(key) is not None:return b[key]
    return None

def _action(req, action):
    action=_dict(action); option=_dict(action.get('Option')); phase=req.get('Type')
    typ=action.get('Type','')
    if phase=='CardSelection':
        if typ=='ConfirmSelection':return {'Type':'ConfirmSelection'}
        return {'Type':'SelectCard','Index':_get(action,option,'Index','ChoiceIndex','index'),
                'CardId':_id(_get(action,option,'CardId','card_id')),
                'UpgradeLevel':_get(action,option,'UpgradeLevel','upgrade_level') or 0}
    if phase=='BundleDecision' or typ=='ChooseBundle':
        return {'Type':'ChooseBundle','BundleIndex':_get(action,option,'BundleIndex','index') or 0,
                'CardIds':_list(_get(action,option,'CardIds','card_ids')),
                'Rarities':_list(_get(action,option,'Rarities','rarities'))}
    return legacy.canonical_action(req,action)

canonical_action=_action

class Tail:
    def __init__(self):self.data=[0.0]*2048;self.pos=0
    def token(self,v,width=48):
        if self.pos+width>len(self.data):raise ValueError('v8 tail overflow')
        s=_id(v).upper().encode('utf8')[:width]
        for i,ch in enumerate(s):self.data[self.pos+i]=ch/127.5-1
        self.pos+=width
    def num(self,v):
        if self.pos>=len(self.data):raise ValueError('v8 tail overflow')
        f=_num(v);self.data[self.pos]=math.tanh(math.copysign(math.log1p(abs(f)),f)/8)
        self.pos+=1

def encode(request,action):
    req=_dict(request); action=_dict(action); normalized=_action(req,action)
    # Let old encoder encode fixed general gameplay features, with the v8
    # normalization for choice actions only. Do not modify the v7 module.
    base_req=dict(req)
    if req.get('Type')=='BundleDecision':
        base_req['Type']='CardRewardDecision'
    baseline=legacy.encode(base_req,normalized)
    w=Tail(); opt=_dict(action.get('Option'))
    w.token(base_req.get('Type'));w.token(normalized.get('Type'))
    w.token(_event_id(req.get('EventId')));w.token(req.get('EventName'))
    # Simulator prompt has no equivalent on live CardSelection; purpose is shared.
    w.token(req.get('Purpose'));w.token(req.get('Source'))
    w.num(req.get('MinSelect'));w.num(req.get('MaxSelect'))
    selected={int(i) for i in _list(req.get('SelectedIndices')) if isinstance(i,int)}
    w.num(len(selected));w.num(len(_list(req.get('Options'))))
    # Complete candidate identities are critical: policy must know what it is
    # selecting FROM, not just the current card being scored.
    details=_list(req.get('OptionDetails'))
    options=_list(req.get('Options'))
    for i in range(16):
        c=_dict(details[i]) if i<len(details) else {}
        fallback=options[i] if i<len(options) else ''
        w.token(c.get('CardId',fallback),32);w.num(c.get('UpgradeLevel'))
        w.num(i in selected)
    w.num(_get(action,opt,'Index','ChoiceIndex','CardIndex','RewardIndex','BundleIndex','index'))
    w.token(_get(action,opt,'CardId','card_id'),48)
    w.token(_get(action,opt,'Rarity','rarity'))
    w.num(_get(action,opt,'UpgradeLevel','upgraded'))
    enchantments=_get(action,opt,'Enchantments','enchantments')
    enchantments=_dict(enchantments)
    w.num(len(enchantments))
    for key,val in sorted(enchantments.items())[:4]:
        w.token(key,24);w.num(val if isinstance(val,(int,float,bool)) else 1)
    for i in range(8):
        cards=_list(_get(action,opt,'CardIds','card_ids'))
        rarities=_list(_get(action,opt,'Rarities','rarities'))
        w.token(cards[i] if i<len(cards) else '',32)
        w.token(rarities[i] if i<len(rarities) else '',24)
    w.num(len(_list(_get(action,opt,'CardIds','card_ids'))))
    w.token(_get(action,opt,'OptionId','option_id'),48)
    w.token(_get(action,opt,'Description','description'),120)
    w.token(_get(action,opt,'Name','label'),72)
    return baseline+w.data
