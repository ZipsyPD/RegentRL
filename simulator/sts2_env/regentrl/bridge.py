"""Translate simulated combat decisions to RegentRL protocol-v2 requests.

No future information is included. Unrepresentable actions are rejected, never
silently assigned a different legal index. This module uses RegentRL's actual
hashing encoder, copied without changes into feature_encoder.py.
"""
from __future__ import annotations

from sts2_env.core.constants import MAX_ENEMIES, MAX_HAND_SIZE


def _id(item):
    # Enum.value uses auto-assigned integer IDs. Those are NOT the public
    # identifiers sent by C# (Card.Id.Entry, IntentType.ToString()).
    # Encoding numeric Enum values caused a major train-vs-live mismatch.
    if item is None:
        return ''
    return str(getattr(item, 'name', item))


def _power_list(creature):
    powers = getattr(creature, 'powers', {})
    if isinstance(powers, dict):
        return [{'Id': _id(k), 'Amount': getattr(v, 'amount', v)} for k,v in powers.items()]
    return []


def _selection_purpose(prompt):
    """Only infer what the simulator explicitly shows in its choice prompt."""
    text=str(prompt or '').lower()
    for word, purpose in (('transform','Transform'),('remove','Remove'),('upgrade','Upgrade'),
                          ('enchant','Enchant'),('discard','Discard'),('exhaust','Exhaust'),
                          ('duplicate','Duplicate'),('draw','Draw')):
        if word in text:
            return purpose
    return 'Generic'


def _pending_selection(mgr):
    if mgr.phase == mgr.PHASE_COMBAT:
        combat=mgr.get_combat_state()
        return getattr(combat,'pending_choice',None)
    if mgr.phase == mgr.PHASE_EVENT:
        model=getattr(mgr,'_event_model',None)
        return getattr(model,'pending_choice',None)
    return getattr(mgr.run_state,'pending_choice',None)


def _card_selection_info(choice):
    cards = list(choice.options)
    return {'Purpose':_selection_purpose(choice.prompt),
            'Source':(cards[0].source_pile if cards else 'Unknown').title(),
            'MinSelect':(0 if choice.allow_skip else int(choice.min_choices)), 'MaxSelect':int(choice.max_choices),
            'SelectedIndices':sorted(choice.selected_indices),
            'OptionDetails':[{'Index':i,'CardId':_id(opt.card.card_id),
                              'UpgradeLevel':int(opt.card.upgraded)} for i,opt in enumerate(cards)],
            'Options':[_id(opt.card.card_id) for opt in cards],
            'SelectionPrompt':str(choice.prompt)}


def combat_request(env, *, decision_id=0):
    """Return (RegentRL request, ordered simulator action IDs) for combat.

    Only the simple card/end-turn/potion phase is supported. Choice screens
    require a distinct RegentRL CardSelection protocol and are rejected.
    """
    from sts2_env.gym_env.action_space import action_to_card_and_target, action_to_potion_and_target, is_potion_action
    mgr = env._mgr
    if mgr is None or mgr.phase != mgr.PHASE_COMBAT:
        raise ValueError('combat_request requires active combat')
    combat = mgr.get_combat_state()
    if combat is None or combat.is_over or combat.pending_choice is not None:
        raise ValueError('Combat ended or a selection protocol is pending')
    run = mgr.run_state.player
    enemies = list(combat.enemies)
    actions, ids = [], []
    mask = env.action_masks()
    hand = list(combat.hand)
    for idx, legal in enumerate(mask):
        if not legal or idx >= 115:
            continue
        if idx == 0:
            action = {'Type':'EndTurn','HandIndex':None,'CardId':'','TargetId':None,'PotionSlot':None,'PotionId':''}
        elif is_potion_action(idx):
            slot, target = action_to_potion_and_target(idx)
            if slot is None or slot >= len(combat.potions) or combat.potions[slot] is None:
                continue
            potion = combat.potions[slot]
            action = {'Type':'UsePotion','HandIndex':None,'CardId':'', 'TargetId': enemies[target].combat_id if target is not None else None,
                      'PotionSlot':slot,'PotionId':_id(getattr(potion, 'potion_id', ''))}
        else:
            hand_idx, target = action_to_card_and_target(idx)
            if hand_idx is None or hand_idx >= len(hand):
                continue
            if target is not None and target >= len(enemies):
                continue
            action = {'Type':'PlayCard','HandIndex':hand_idx,'CardId':_id(hand[hand_idx].card_id),
                      'TargetId':enemies[target].combat_id if target is not None else None,
                      'PotionSlot':None,'PotionId':''}
        ids.append(idx)
        actions.append(action)
    if not actions:
        raise ValueError('No mappable combat actions')
    # The current RegentRL combat protocol cannot represent every simulator
    # multiplayer/select-player action. This adapter trains only mapped actions.
    request = {'Type':'CombatDecision','DecisionId':decision_id,'ProtocolVersion':2,
               'RunObservation':{
                 'Hp':run.current_hp, 'MaxHp':run.max_hp, 'Gold':run.gold,
                 'Floor':mgr.run_state.total_floor, 'Act':mgr.run_state.current_act_index,
                 'Deck':[{'CardId':_id(c.card_id),'UpgradeLevel':int(c.upgraded)} for c in run.deck],
                 'Relics':[_id(r) for r in run.relics],
                 'PotionSlots':[{'Slot':i,'PotionId':_id(p.potion_id) if p else None} for i,p in enumerate(run.potions)]},
               'Observation':{'Turn':combat.turn_count,'Player':{
                 'Hp':combat.player.current_hp,'MaxHp':combat.player.max_hp,
                 'Block':combat.player.block,'Energy':combat.energy,'MaxEnergy':combat.max_energy,'Stars':combat.stars,
                 'Powers':_power_list(combat.player)},
                 'Enemies':[{'CombatId':e.combat_id,'Hp':e.current_hp,'MaxHp':e.max_hp,'Block':e.block,
                             'MonsterId':str(e.monster_id or ''),'Powers':_power_list(e), 'Intents':[{'Type':_id(intent.intent_type),'DamagePerHit':intent.damage,'Hits':intent.hits} for intent in (combat.enemy_ais[e.combat_id].current_move.intents if e.combat_id in combat.enemy_ais else [])]} for e in enemies],
                 'Hand':[{'HandIndex':i,'Id':_id(c.card_id),'UpgradeLevel':int(c.upgraded),
                          'EnergyCost':c.cost,'StarCost':c.star_cost,
                          'TargetType':_id(c.target_type_for(combat.player))} for i,c in enumerate(hand)]},
               'LegalActions':actions}
    return request, ids


def selected_simulator_action(request, action_ids, response):
    if response.get('DecisionId') != request.get('DecisionId'):
        raise ValueError('DecisionId mismatch')
    idx = response.get('ActionIndex')
    if type(idx) is not int or not 0 <= idx < len(action_ids):
        raise ValueError('Invalid RegentRL action index')
    return action_ids[idx]


def fullrun_request(env, *, decision_id=0):
    """Return (version-3 model request, exact simulator action IDs).

    Uses the simulator action mask for the source of truth. All phases are
    trainable, including otherwise unrepresentable specialized selections.
    The synthesized action schema is model-only; RegentRL's wire protocol
    and its existing C# action descriptors are never changed.
    """
    from sts2_env.gym_env.run_env import _LAYOUT
    mgr=env._mgr
    if mgr is None or mgr.is_over:
        raise ValueError('No active run')
    if mgr.phase == mgr.PHASE_COMBAT and mgr.get_combat_state() is not None:
        combat=mgr.get_combat_state()
        if not combat.is_over and combat.pending_choice is None:
            # Preserve the existing combat adapter when it can represent every legal action.
            request,ids=combat_request(env,decision_id=decision_id)
            return request,ids
    mask=env.action_masks()
    ids=[int(i) for i,legal in enumerate(mask) if legal]
    selection=_pending_selection(mgr)
    if selection is not None:
        ids=[i for i in ids if i==0 or (i>0 and i-1 not in selection.selected_indices)]
    if not ids:
        raise RuntimeError('No legal simulator actions')
    available=mgr.get_available_actions()
    phase=mgr.phase
    phase_types={
        mgr.PHASE_MAP_CHOICE:'MapDecision',
        mgr.PHASE_CARD_REWARD:'CardRewardDecision',
        mgr.PHASE_BOSS_RELIC:'RewardDecision',
        mgr.PHASE_SHOP:'ShopDecision',
        mgr.PHASE_REST_SITE:'RestSiteDecision',
        mgr.PHASE_EVENT:'EventDecision',
        mgr.PHASE_TREASURE:'RewardDecision',
        mgr.PHASE_COMBAT:'CardSelection',
    }
    type_name=phase_types.get(phase,'RunDecision')
    selection=_pending_selection(mgr)
    actions=[]
    for idx in ids:
        description={'Type':type_name,'SimulatorActionId':idx}
        if selection is not None:
            # The simulator toggles chosen cards; the live native selector only
            # submits a subset. Train on monotonic additions and ConfirmSelection.
            if idx == 0:
                description={'Type':'ConfirmSelection'}
            else:
                k=idx-1
                opts=selection.options
                if not 0 <= k < len(opts):
                    raise ValueError(f'Invalid card choice slot {idx}')
                card=opts[k].card
                description={'Type':'SelectCard','Index':k,'CardId':_id(card.card_id),
                             'UpgradeLevel':int(card.upgraded)}
            type_name='CardSelection'
        elif phase==mgr.PHASE_MAP_CHOICE:
            local=idx-_LAYOUT.map_start
            description={'Type':'SelectMapNode','Option':available[local] if local<len(available) else {}}
        elif phase==mgr.PHASE_CARD_REWARD:
            if _LAYOUT.player_select_start<=idx<_LAYOUT.player_select_start+_LAYOUT.player_select_size:
                b=idx-_LAYOUT.player_select_start
                bundles=[a for a in available if a.get('action')=='pick_card_bundle']
                option=bundles[b] if b<len(bundles) else {}
                description={'Type':'ChooseBundle','BundleIndex':b,
                             'CardIds':option.get('card_ids',[]),
                             'Rarities':option.get('rarities',[])}
            elif idx==_LAYOUT.card_reward_reroll: description={'Type':'RerollReward'}
            elif idx==_LAYOUT.card_reward_start+3: description={'Type':'SkipReward'}
            else:
                n=(idx-_LAYOUT.card_reward_extra_start+3) if idx>=_LAYOUT.card_reward_extra_start else idx-_LAYOUT.card_reward_start
                picks=[a for a in available if a.get('action') in ('pick_card','pick_potion','pick_relic_reward')]
                description={'Type':'SelectReward','RewardIndex':n,'Option':picks[n] if n<len(picks) else {}}
        elif phase==mgr.PHASE_BOSS_RELIC:
            local=idx-_LAYOUT.boss_relic_start
            picks=[a for a in available if a.get('action')=='pick_relic']
            description={'Type':'SelectReward','RewardIndex':local,'Option':picks[local] if local<len(picks) else {}}
        elif phase==mgr.PHASE_SHOP:
            local=idx-_LAYOUT.shop_start
            buys=env._get_shop_buy_actions()
            description={'Type':'LeaveShop'} if local==0 else {'Type':'BuyItem','Option':buys[local-1] if local-1<len(buys) else {}}
        elif phase==mgr.PHASE_REST_SITE:
            local=idx-_LAYOUT.rest_start
            opts=[a for a in available if a.get('action')=='rest_option']
            description={'Type':'RestOption','Option':opts[local] if local<len(opts) else {}}
        elif phase==mgr.PHASE_EVENT:
            local=idx-_LAYOUT.event_start
            opts=[a for a in available if a.get('action')=='event_choice']
            description={'Type':'EventOption','ChoiceIndex':local,'Option':opts[local] if local<len(opts) else {}}
        elif phase==mgr.PHASE_TREASURE:description={'Type':'CollectTreasure'}
        actions.append(description)
    player=mgr.run_state.player
    obs={'Hp':player.current_hp,'MaxHp':player.max_hp,'Gold':player.gold,
         'Floor':mgr.run_state.total_floor, 'Act':mgr.run_state.current_act_index,
         'Deck':[{'CardId':_id(c.card_id),'UpgradeLevel':int(c.upgraded)} for c in player.deck],
         'Relics':[_id(r) for r in player.relics],
         'PotionSlots':[{'Slot':i,'PotionId':_id(p.potion_id) if p else None} for i,p in enumerate(player.potions)]}
    request={'Type':type_name,'DecisionId':decision_id,'ProtocolVersion':2,
             'RunObservation':obs,'Observation':{'Phase':str(phase), 'AvailableActions':available},'LegalActions':actions}
    if selection is not None:
        request.update(_card_selection_info(selection))
    if phase==mgr.PHASE_EVENT and selection is None:
        ev=getattr(mgr,'_event_model',None)
        request['EventId']=str(getattr(ev,'event_id','') or (type(ev).__name__ if ev else ''))
    return request,ids
