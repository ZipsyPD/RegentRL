"""V5 positional state/action encoder. No feature hashing or modulo collisions.
Fixed-width numeric fields and UTF-8 identifiers; explicit truncation limits.
A truncated field is a limitation, not a learned representation of its contents.
"""
from __future__ import annotations
import math
FEATURE_VERSION = 6
FEATURES = 2048

class Writer:
    def __init__(self): self.x=[0.0]*FEATURES;self.pos=0
    def num(self,v,scale=1):
        try: z=float(v);z=math.copysign(math.log1p(abs(z)),z)/scale if math.isfinite(z) else 0.0
        except (ValueError,TypeError,OverflowError): z=0.0
        if self.pos<FEATURES:self.x[self.pos]=math.tanh(z)
        self.pos+=1
    def token(self,v,width=24):
        b=str(v if v is not None else '').encode('utf-8')[:width]
        for i in range(width):
            if self.pos<FEATURES:self.x[self.pos]=(b[i]/127.5-1) if i<len(b) else 0.0
            self.pos+=1
    def record(self, obj, tokens=2, nums=4):
        if not isinstance(obj,dict):obj={'Value':obj}
        keys=sorted(obj)
        words=[(k,obj[k]) for k in keys if isinstance(obj[k],(str,bool)) or obj[k] is None]
        numbers=[(k,obj[k]) for k in keys if isinstance(obj[k],(int,float)) and not isinstance(obj[k],bool)]
        for i in range(tokens):
            if i<len(words): self.token(words[i][0],12);self.token(words[i][1],24)
            else:self.token('',12);self.token('',24)
        for i in range(nums):
            if i<len(numbers):self.token(numbers[i][0],12);self.num(numbers[i][1],8)
            else:self.token('',12);self.num(0)

def _canonical_action(request, action):
    """Align live shop/rest decisions with simulator action descriptors."""
    if not isinstance(action, dict):
        return action
    phase = request.get('Type')
    t = action.get('Type')
    if phase == 'ShopDecision' and t in ('BuyCard','BuyRelic','BuyPotion','RemoveCard','BuyItem'):
        original = action.get('Option') or {}
        if t == 'BuyItem' and isinstance(original,dict):
            kind = str(original.get('action',''))
            item = str(original.get({'buy_card':'card_id','buy_relic':'relic_id',
                                     'buy_potion':'potion_id'}.get(kind,''), '') or '')
            price = original.get('price',0)
        else:
            kind = {'BuyCard':'buy_card','BuyRelic':'buy_relic',
                    'BuyPotion':'buy_potion','RemoveCard':'remove_card'}.get(t,'')
            item = str(action.get('ItemId') or '')
            price = action.get('Cost',0)
        # Writer.record() keeps two string fields. The second must be the
        # item identifier (not rarity), or all relics/potions alias together.
        return {'Type':'BuyItem','Option':{
            'action':kind,
            'item_id':item,
            'price':price,
        }}
    if phase == 'RestSiteDecision' and t in ('ChooseRestOption','RestOption'):
        o = action.get('Option') or {}
        option_id = str(action.get('OptionId') or o.get('option_id') or '').upper()
        return {'Type':'RestOption', 'Option':{'action':'rest_option','option_id':option_id}}
    return action

def encode(request,action):
    action=_canonical_action(request,action)
    w=Writer();w.num(1)
    w.token(request.get('Type'),24)
    run=request.get('RunObservation') or {}
    for k in ('Hp','MaxHp','Gold','Floor','Act') : w.num(run.get(k,0),8)
    deck=run.get('Deck') or []
    w.num(len(deck),8)
    # Content of deck is represented by explicit card identifiers at fixed positions.
    for c in deck[:12]:
        if isinstance(c,dict):w.token(c.get('CardId'),24);w.num(c.get('UpgradeLevel',0),4)
        else:w.token(c,24);w.num(0)
    for _ in range(max(0,12-len(deck))):w.token('',24);w.num(0)
    for key,n in (('Relics',5),('PotionSlots',3)):
        seq=run.get(key) or []
        w.num(len(seq),8)
        for i in range(n):
            obj=seq[i] if i<len(seq) else None
            if isinstance(obj,dict):obj=obj.get('PotionId',obj.get('RelicId',''))
            w.token(obj,24)
    obs=request.get('Observation') or request.get('CombatObservation') or {}
    if not isinstance(obs,dict):obs={}
    player=obs.get('Player') or {}
    if not isinstance(player,dict):player={}
    for k in ('Turn','TurnNumber','Hp','MaxHp','Block','Energy','Stars'):
        w.num(obs.get(k,player.get(k,0)),8)
    enemies=obs.get('Enemies') or []
    w.num(len(enemies),8)
    for e in enemies[:3]:
        if not isinstance(e,dict):e={}
        w.token(str(e.get('CombatId',e.get('EnemyId',e.get('Id','')))),24)
        for k in ('Hp','MaxHp','Block') :w.num(e.get(k,0),8)
        intents=e.get('Intents') or []
        w.num(len(intents),8)
        intent=intents[0] if intents else {}
        if isinstance(intent,dict):
            w.token(intent.get('Type',intent.get('IntentType','')),24)
            w.num(intent.get('DamagePerHit', intent.get('Damage', 0)), 8); w.num(intent.get('Hits', 0), 8); w.num(intent.get('Count', 0), 8)
        else:w.token(str(intent),24);w.num(0);w.num(0);w.num(0)
    for _ in range(max(0,3-len(enemies))):w.token('',24);[w.num(0) for i in range(5)];w.token('',24);[w.num(0) for i in range(3)]
    hand=obs.get('Hand') or []
    w.num(len(hand),8)
    for c in hand[:8]:
        if not isinstance(c,dict):c={}
        w.token(c.get('CardId', c.get('Id', '')),24)
        for k in ('EnergyCost','Cost','UpgradeLevel','Playable'):w.num(c.get(k,0),8)
    for _ in range(max(0,8-len(hand))):w.token('',24);[w.num(0) for i in range(4)]
    w.token(request.get('Purpose',''),24);w.token(request.get('Source',''),24)
    w.num(request.get('MinSelect',0),8);w.num(request.get('MaxSelect',0),8)
    # Dedicated action region: distinguish playable actions with identical state.
    if not isinstance(action,dict):action={'Value':action}
    for key in ('Type','CardId','PotionId','RoomType','Purpose'):
        w.token(action.get(key,''),24)
    for key in ('HandIndex','TargetId','PotionSlot','Row','Column','RewardIndex','ChoiceIndex','Index','UpgradeLevel','Cost'):
        w.num(action.get(key,0),8)
    # Nested choice content is encoded with stable positions rather than hashing.
    option=action.get('Option') or {}
    w.record(option,2,4)
    # CardSelection live candidates use OptionDetails directly.
    w.record(action.get('OptionDetail') or {},1,2)
    # v6 extension: fixed-capacity public combat information. Appended after
    # the v5 region so phase-independent action features retain their order.
    def powers(seq, count):
        seq = seq if isinstance(seq, list) else []
        w.num(len(seq), 8)
        for p in seq[:count]:
            p = p if isinstance(p, dict) else {}
            w.token(p.get('Id', p.get('PowerId','')), 24)
            w.num(p.get('Amount', 0), 8)
        for _ in range(max(0, count-len(seq))):
            w.token('',24);w.num(0)
    powers(player.get('Powers'), 4)
    for e in enemies[:3]:
        e=e if isinstance(e,dict) else {}
        powers(e.get('Powers'), 3)
        intents=e.get('Intents') or []
        # First intent already appears above; retain the next two public intents.
        for intent in intents[1:3]:
            intent=intent if isinstance(intent,dict) else {'Type':str(intent)}
            w.token(intent.get('Type', intent.get('IntentType','')),24)
            w.num(intent.get('DamagePerHit',intent.get('Damage',0)),8)
            w.num(intent.get('Hits',0),8)
        for _ in range(max(0,2-len(intents[1:3]))):
            w.token('',24);w.num(0);w.num(0)
    return w.x
