"""RegentRL v7: fixed-slot public-information encoder shared by simulator and live game.

Model-only normalization: NEVER change the wire-protocol action or its index.
Old v5/v6 code is preserved in versioned modules for checkpoint compatibility.
No RNG seeds, hidden moves, or future rewards are read here.
"""
from __future__ import annotations

import math

FEATURE_VERSION = 7
FEATURES = 4096


def _id(v):
    """Normalize game ModelId.ToString() (CARD.STRIKE_REGENT) and bare IDs."""
    if v is None:
        return ''
    text = str(v)
    return text.split('.', 1)[1] if text.split('.', 1)[0].upper() in {'CARD','RELIC','POTION','POWER','MONSTER','ENEMY'} and '.' in text else text


def _num(v):
    if isinstance(v, bool):
        return int(v)
    try:
        f = float(v)
        return f if math.isfinite(f) else 0.0
    except (ValueError, TypeError, OverflowError):
        return 0.0


def _dict(v):
    return v if isinstance(v, dict) else {}


def _list(v):
    return v if isinstance(v, (list, tuple)) else []


def _coalesce(*values):
    return next((v for v in values if v is not None), None)


def _phase(t):
    return 'EventDecision' if t == 'NeowDecision' else t or ''


def canonical_action(request, action):
    """Convert semantically equivalent live/simulator actions into one scoring schema."""
    action = _dict(action)
    phase = _phase(request.get('Type'))
    typ = action.get('Type', '')
    option = _dict(action.get('Option'))
    if phase == 'MapDecision':
        coord = option.get('coord')
        col = coord[0] if isinstance(coord, (list,tuple)) and len(coord) == 2 else None
        row = coord[1] if isinstance(coord, (list,tuple)) and len(coord) == 2 else None
        return {'Type':'ChooseRoom', 'Row':_coalesce(row, action.get('Row'), 0),
                'Column':_coalesce(action.get('Column'), col, 0),
                'RoomType': str(_coalesce(action.get('RoomType'),option.get('point_type'),'')).upper().replace('_','')}
    if phase == 'ShopDecision':
        if typ == 'LeaveShop':
            return {'Type':'LeaveShop'}
        kind = {'BuyCard':'buy_card','BuyRelic':'buy_relic','BuyPotion':'buy_potion',
                'RemoveCard':'remove_card'}.get(typ, option.get('action',''))
        item = _coalesce(action.get('ItemId'),option.get({'buy_card':'card_id','buy_relic':'relic_id','buy_potion':'potion_id'}.get(kind,'')), '')
        return {'Type':'BuyItem', 'Kind':kind, 'ItemId':_id(item),
                'Cost':_coalesce(action.get('Cost'),option.get('price'),0)}
    if phase == 'CardRewardDecision':
        kind = option.get('action','')
        if typ in ('SkipReward','SkipRemainingRewards') or kind in ('skip_card','skip_reward'):
            return {'Type':'SkipReward'}
        if typ == 'RerollReward' or kind in ('reroll_card_reward','reroll'):
            return {'Type':'RerollReward'}
        if typ == 'ChooseCard' or kind == 'pick_card':
            return {'Type':'ChooseCard','CardId':_id(_coalesce(action.get('CardId'),option.get('card_id'),'')),
                    'CardIndex':_coalesce(action.get('CardIndex'),option.get('index'),action.get('RewardIndex'),0)}
        return {'Type':typ,'ChoiceKind':kind,'ItemId':_id(_coalesce(option.get('potion_id'),option.get('relic_id'),''))}
    if phase == 'RestSiteDecision':
        return {'Type':'RestOption','OptionId':str(_coalesce(action.get('OptionId'),option.get('option_id'), '')).upper()}
    if phase == 'RewardDecision':
        if typ in ('SkipReward','SkipRemainingRewards'):
            return {'Type':'SkipReward'}
        if typ in ('SelectReward',):
            reward_idx=_coalesce(action.get('RewardIndex'),option.get('index'),0)
            native_rewards=_list(_dict(request.get('Observation')).get('Rewards'))
            matching=next((o for o in native_rewards if isinstance(o,dict) and o.get('RewardIndex') == reward_idx),{})
            # Keep item and reward type when the native reward screen provides
            # them. Simulator's boss-relic choice provides relic_id in Option.
            return {'Type':'SelectReward','RewardIndex':reward_idx,
                    'ChoiceKind': _coalesce(matching.get('Type'), 'Relic' if option.get('relic_id') else ''),
                    'ItemId': _id(_coalesce(matching.get('ItemId'),option.get('relic_id'), '')),
                    'Cost':matching.get('GoldAmount',0)}
        # The simulator's boss-relic choice contains information not present in
        # the current live reward protocol. Preserve the native kind, don't fake parity.
        return {'Type':typ, 'ChoiceKind':option.get('action',''),
                'ItemId':_id(option.get('relic_id',''))}
    if phase == 'EventDecision':
        if typ in ('ChooseOption','EventOption'):
            return {'Type':'ChooseOption', 'OptionIndex':_coalesce(action.get('OptionIndex'),action.get('ChoiceIndex'),option.get('index'),0),
                    'Name':str(_coalesce(action.get('Name'),option.get('label'),option.get('option_id'),''))}
    if typ in ('PlayCard','UsePotion'):
        return {'Type':typ,'CardId':_id(action.get('CardId')),'PotionId':_id(action.get('PotionId')),
                'HandIndex':action.get('HandIndex'),'PotionSlot':action.get('PotionSlot'),
                'TargetId':action.get('TargetId')}
    if phase == 'CardSelection' and typ == 'ChooseOption':
        return {'Type':'SelectCard','CardId':_id(_coalesce(option.get('card_id'),action.get('CardId'),'')),
                'Index':_coalesce(option.get('index'),action.get('ChoiceIndex'),0),
                'UpgradeLevel':option.get('upgrade_level',0)}
    if typ in ('SelectCard','ChooseOption'):
        return {'Type':typ,'CardId':_id(action.get('CardId')),
                'Index':_coalesce(action.get('Index'),action.get('ChoiceIndex'),0),
                'UpgradeLevel':action.get('UpgradeLevel',0),
                'OptionDetail':_dict(action.get('OptionDetail'))}
    return action


def _target_index(target_id, enemies):
    if target_id is None:
        return -1
    for i, enemy in enumerate(enemies):
        if _dict(enemy).get('CombatId') == target_id:
            return i
    # Target IDs vary from run to run; never encode raw combat instance IDs.
    return -2


class Writer:
    def __init__(self):
        self.x=[0.0]*FEATURES
        self.pos=0
    def num(self, val, scale=8):
        if self.pos >= FEATURES:
            raise ValueError(f'v7 feature overflow at {self.pos}')
        v=_num(val)
        self.x[self.pos] = math.tanh(math.copysign(math.log1p(abs(v)),v) / scale)
        self.pos+=1
    def token(self, val, width=24):
        data=_id(val).upper().encode('utf-8')[:width]
        if self.pos+width>FEATURES:
            raise ValueError(f'v7 token overflow at {self.pos}')
        for k,byte in enumerate(data):
            self.x[self.pos+k]=byte/127.5-1
        self.pos+=width
    def powers(self, src, count):
        powers = _list(src)
        self.num(len(powers))
        # Status powers are a set, not an ordered sequence.
        powers=sorted((_dict(p) for p in powers), key=lambda p: _id(_coalesce(p.get('Id'),p.get('PowerId'),'')))
        for i in range(count):
            p=powers[i] if i<len(powers) else {}
            self.token(_coalesce(p.get('Id'),p.get('PowerId'),''))
            self.num(p.get('Amount',0))
    def intents(self, src, count):
        intents = _list(src)
        self.num(len(intents))
        for i in range(count):
            p=_dict(intents[i]) if i<len(intents) else {}
            self.token(str(_coalesce(p.get('Type'),p.get('IntentType'), '')).replace('_',''))
            self.num(_coalesce(p.get('DamagePerHit'),p.get('Damage'),0))
            self.num(_coalesce(p.get('Hits'),p.get('Count'),0))


def encode(request, action):
    request=_dict(request)
    action=canonical_action(request,action)
    obs=_dict(_coalesce(request.get('Observation'),request.get('CombatObservation')))
    player=_dict(obs.get('Player'))
    enemies=_list(obs.get('Enemies'))
    run=_dict(request.get('RunObservation'))
    w=Writer()
    w.num(1)
    w.token(_phase(request.get('Type')))
    for key in ('Hp','MaxHp','Gold','Floor','Act'):
        w.num(run.get(key,0))
    # Deck is a multiset. Deterministic ordering prevents source/order parity drift.
    deck=[]
    for c in _list(run.get('Deck')):
        c=_dict(c) if isinstance(c,dict) else {'CardId':c}
        deck.append((_id(c.get('CardId')),c.get('UpgradeLevel',0)))
    deck.sort(key=lambda c:(c[0],_num(c[1])))
    w.num(len(deck))
    for i in range(20):
        card,up=deck[i] if i<len(deck) else ('',0)
        w.token(card);w.num(up)
    relics=sorted(_id(c) for c in _list(run.get('Relics')))
    w.num(len(relics))
    for i in range(10):w.token(relics[i] if i<len(relics) else '')
    potions=_list(run.get('PotionSlots'))
    w.num(len(potions))
    for i in range(9):
        potion=potions[i] if i<len(potions) else None
        w.token(_dict(potion).get('PotionId') if isinstance(potion,dict) else potion)
    for key in ('Turn','Hp','MaxHp','Block','Energy','MaxEnergy','Stars'):
        w.num(_coalesce(obs.get(key),player.get(key),0))
    w.powers(player.get('Powers'),8)
    w.num(len(enemies))
    for i in range(5):
        e=_dict(enemies[i]) if i<len(enemies) else {}
        # Public enemy model identity, plus a run-independent target slot.
        w.token(e.get('MonsterId', ''))
        w.num(i if i<len(enemies) else -1)
        for key in ('Hp','MaxHp','Block'):w.num(e.get(key,0))
        w.intents(e.get('Intents'),4)
        w.powers(e.get('Powers'),5)
    hand=_list(obs.get('Hand'))
    w.num(len(hand))
    # Hand Playable is derived from legal actions on both paths; simulator does
    # not emit a Playable field, and native CanPlay() differs from actual legality.
    playable={a.get('HandIndex') for a in _list(request.get('LegalActions'))
              if isinstance(a,dict) and a.get('Type')=='PlayCard'}
    for i in range(10):
        c=_dict(hand[i]) if i<len(hand) else {}
        w.token(_coalesce(c.get('Id'),c.get('CardId'),''))
        for key in ('EnergyCost','StarCost','UpgradeLevel'):
            w.num(c.get(key,0))
        w.num(i in playable and i<len(hand))
        # Native TargetType names and simulator enum names use different casing.
        w.token(str(c.get('TargetType','')).upper().replace('_',''))
        untargeted=any(isinstance(a,dict) and a.get('Type')=='PlayCard' and a.get('HandIndex')==i and a.get('TargetId') is None for a in _list(request.get('LegalActions')))
        w.num(untargeted)
    # Potion observation also carries public target/usage state on live requests.
    # The model currently relies on legal potion actions instead of source-only
    # usability flags, to avoid a simulator/live feature mismatch.
    w.num(request.get('MinSelect',0));w.num(request.get('MaxSelect',0))
    w.token(request.get('Purpose',''));w.token(request.get('Source',''))
    w.token(action.get('Type',''))
    for key in ('CardId','PotionId','RoomType','ItemId','Kind','OptionId','ChoiceKind','Name'):
        w.token(action.get(key,''))
    for key in ('HandIndex','PotionSlot','Row','Column','CardIndex','RewardIndex','ChoiceIndex',
                'OptionIndex','Index','UpgradeLevel','Cost'):
        w.num(action.get(key,0))
    w.num(_target_index(action.get('TargetId'),enemies))
    detail=_dict(action.get('OptionDetail'))
    w.token(_coalesce(detail.get('CardId'),detail.get('Id'),''))
    w.num(detail.get('UpgradeLevel',0))
    # Unknown action types remain distinguishable by their extra scalar fields;
    # the current native RewardDecision has only index, not reward identity.
    return w.x
