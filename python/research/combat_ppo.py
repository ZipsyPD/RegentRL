"""Experimental ON-POLICY PPO, using native-verified STS2 combat episodes.

No toy simulator. No claim that a few combats produce an effective policy.
No future-state inputs. Training only on complete, verified combat episodes.
"""
from __future__ import annotations
import json
import math
import random
from pathlib import Path
import torch
from torch import nn
from torch.distributions import Categorical

FEATURES = 256


def _hash(key):
    import hashlib
    return int.from_bytes(hashlib.blake2b(str(key).encode(), digest_size=8).digest(), 'little') % FEATURES


def encode(request, action=None):
    """Publicly observable combat facts. Action candidate added for actor only."""
    x = [0.0] * FEATURES
    def add(k, v=1.0):
        x[_hash(k)] += float(v)
    obs = request.get('Observation') or {}
    player = obs.get('Player') or {}
    add('bias')
    for k, scale in [('Hp', 80),('MaxHp',80),('Block',30),('Energy',5),('MaxEnergy',5),('Stars',5)]:
        add('p:'+k, (player.get(k) or 0)/scale)
    add('turn', (obs.get('Turn') or 0)/15)
    for power in player.get('Powers',[]) or []:
        if isinstance(power,dict): add('pp:'+str(power.get('Id')), (power.get('Amount') or 1)/10)
    enemies = obs.get('Enemies') or []
    add('enemy_count',len(enemies)/5)
    for enemy in enemies:
        if not isinstance(enemy,dict): continue
        name=str(enemy.get('Name','?'))
        add('enemy:'+name,1)
        for k,scale in [('Hp',100),('MaxHp',100),('Block',30)]:
            add('enemy_'+k,(enemy.get(k) or 0)/scale)
        for intent in enemy.get('Intents',[]) or []:
            if not isinstance(intent,dict): continue
            add('intent:'+str(intent.get('Type','?')))
            add('intent_damage', (intent.get('DamagePerHit') or 0)*(intent.get('Hits') or 1)/30)
        for power in enemy.get('Powers',[]) or []:
            if isinstance(power,dict): add('ep:'+str(power.get('Id')), (power.get('Amount') or 1)/10)
    hand=obs.get('Hand') or []
    add('hand_count',len(hand)/10)
    for card in hand:
        if not isinstance(card,dict): continue
        add('hand:'+str(card.get('Id','?')),0.2)
        if card.get('Playable'): add('playable:'+str(card.get('Id','?')),0.2)
        add('hand_energy_cost',(card.get('EnergyCost') or 0)/30)
    run=request.get('RunObservation') or {}
    add('gold',(run.get('Gold') or 0)/300)
    for relic in run.get('Relics',[]) or []: add('relic:'+str(relic),0.2)
    for card in run.get('Deck',[]) or []:
        if isinstance(card,dict): add('deck:'+str(card.get('CardId','?')),0.07)
    if action is not None:
        typ=str(action.get('Type','?'))
        add('action_type:'+typ)
        if typ=='PlayCard':
            cid=str(action.get('CardId','?'))
            add('selected_card:'+cid)
            idx=action.get('HandIndex')
            if isinstance(idx,int):
                for card in hand:
                    if card.get('HandIndex')==idx:
                        add('selected_cost',(card.get('EnergyCost') or 0)/5)
                        add('selected_starcost',(card.get('StarCost') or 0)/5)
                        add('selected_upgrade',(card.get('UpgradeLevel') or 0)/5)
                        break
            target=action.get('TargetId')
            if target is not None:
                add('has_target')
                for enemy in enemies:
                    if enemy.get('CombatId')==target:
                        add('target_hp',(enemy.get('Hp') or 0)/100)
                        add('target_block',(enemy.get('Block') or 0)/30)
                        break
        elif typ=='UsePotion': add('selected_potion:'+str(action.get('PotionId','?')))
    return [math.tanh(v) for v in x]


class ActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        self.actor=nn.Sequential(nn.Linear(FEATURES,128),nn.Tanh(),nn.Linear(128,64),nn.Tanh(),nn.Linear(64,1))
        self.critic=nn.Sequential(nn.Linear(FEATURES,128),nn.Tanh(),nn.Linear(128,64),nn.Tanh(),nn.Linear(64,1))
    def distribution_value(self,request):
        legal=request.get('LegalActions') or []
        if not legal: raise ValueError('Combat decision has no legal actions')
        candidate=torch.tensor([encode(request,a) for a in legal],dtype=torch.float32)
        state=torch.tensor([encode(request)],dtype=torch.float32)
        logits=self.actor(candidate).flatten()
        dist=Categorical(logits=logits)
        return dist,self.critic(state).flatten()[0]


class CombatPPO:
    def __init__(self, *, train=False, checkpoint=None, checkpoint_out='checkpoints/ppo_combat.pt', seed=42,
                 gamma=0.99, lam=0.95, clip=0.2, epochs=4, lr=0.0003):
        self.train=train
        self.model=ActorCritic()
        torch.manual_seed(seed)
        if checkpoint:
            blob=torch.load(checkpoint,map_location='cpu',weights_only=True)
            if blob.get('schema')!=1: raise ValueError('Incompatible PPO checkpoint')
            self.model.load_state_dict(blob['model'])
        self.opt=torch.optim.Adam(self.model.parameters(),lr=lr)
        self.gamma=gamma; self.lam=lam; self.clip=clip; self.epochs=epochs
        self.output=Path(checkpoint_out)
        self.events=[]    # decisions of current combat in order
        self.by_id={}
        self.updates=0
        self.episodes=0
        self.skipped=0
        self.combat_result=None   # authoritative CombatEnded event, may arrive before action ack
        print(f'PPO: train={train}; checkpoint={checkpoint}; output={self.output}',flush=True)

    def choose(self,request):
        # The server is single-threaded; delayed native confirmations may arrive later.
        # Only one combat episode's samples are retained, never cross-combat stitching.
        dist,value=self.model.distribution_value(request)
        with torch.no_grad():
            if self.train: action=dist.sample()
            else: action=torch.argmax(dist.logits)
            logp=dist.log_prob(action)
        idx=int(action.item())
        if self.train:
            did=request['DecisionId']
            if did in self.by_id:
                raise ValueError(f'Duplicate active combat decision ID {did}')
            sample={'request':request,'action':idx,'old_logp':float(logp.item()),
                    'value':float(value.item()),'ack':None}
            self.events.append(sample)
            self.by_id[did]=sample
            if len(self.events)==1:
                print(f'PPO: collecting combat episode (first decision={did})',flush=True)
        return {'DecisionId':request['DecisionId'],'ActionIndex':idx}

    def resolved(self,event):
        if not self.train or event.get('DecisionType')!='CombatDecision':return
        item=self.by_id.get(event.get('DecisionId'))
        if item is None:
            print(f'PPO: unmatched action acknowledgment id={event.get("DecisionId")}',flush=True)
            return
        if event.get('Executed') is not True:
            print(f'PPO: action not verified id={event.get("DecisionId")}',flush=True)
            return
        item['ack']=event
        print(f'PPO: ack decision={event.get("DecisionId")} terminal={event.get("Terminal")} verified={sum(e["ack"] is not None for e in self.events)}/{len(self.events)}',flush=True)
        if event.get('Terminal') is True:
            outcome=event.get('CombatOutcome')
            if outcome in ('Win','Loss'):
                self.combat_result=outcome
        self._finish_if_complete()

    def run_ended(self, event):
        """A run may end before CombatEnded and its final action ACK arrive.
        Don't clear pending samples until those late native events can reconcile.
        An abandoned run is not a terminal combat outcome.
        """
        if not self.train:
            return
        outcome = event.get('Outcome')
        if outcome == 'Abandoned':
            self.discard_incomplete('run abandoned')
        elif outcome in ('Win', 'Loss'):
            print(f'PPO: run ended outcome={outcome}; awaiting combat boundary and action ACKs', flush=True)
        else:
            print(f'PPO: run ended outcome={outcome}; no inferred combat reward', flush=True)

    def combat_ended(self, event):
        """Native CombatEnded signals outcome, independently of whether the final
        action ACK arrives first. Never counts an unverified action as executed.
        """
        if not self.train: return
        outcome=event.get('Outcome')
        if outcome not in ('Win','Loss'):
            self.discard_incomplete('combat ended without verified win/loss')
            return
        self.combat_result=outcome
        print(f'PPO: native combat ended outcome={outcome} verified={sum(e["ack"] is not None for e in self.events)}/{len(self.events)}',flush=True)
        self._finish_if_complete()

    def combat_started(self):
        if not self.train:return
        # A missing terminal action ACK is not a legitimate training transition.
        # Never carry the old combat's decisions into the next encounter.
        if self.events:
            self._finish_if_complete()
            if self.events:
                self.discard_incomplete('new combat started before previous completed')
        self.combat_result=None

    def _finish_if_complete(self):
        if not self.events or self.combat_result not in ('Win','Loss'):return
        if any(e['ack'] is None for e in self.events):
            return   # Allow reordered confirmations to arrive after CombatEnded.
        # If a terminal ACK is present, native CombatEnded outcome must agree.
        terminal_outcomes={e['ack'].get('CombatOutcome') for e in self.events
                           if e['ack'].get('Terminal') is True}
        if terminal_outcomes and terminal_outcomes!={self.combat_result}:
            self.discard_incomplete('conflicting combat outcome evidence')
            return
        self.episodes+=1
        outcome=self.combat_result
        rewards=[0.0]*len(self.events)
        rewards[-1]=1.0 if outcome=='Win' else -1.0
        self._update(rewards)
        print(f'PPO: verified combat episode={self.episodes} outcome={outcome} actions={len(self.events)} updates={self.updates}',flush=True)
        self.events=[];self.by_id={};self.combat_result=None

    def _update(self,rewards):
        old_values=[e['value'] for e in self.events]
        advantages=[0.0]*len(self.events)
        gae=0.0
        for t in reversed(range(len(self.events))):
            # Terminal episode. Bootstrap 0 after final action.
            next_value=old_values[t+1] if t+1<len(self.events) else 0.0
            delta=rewards[t]+self.gamma*next_value-old_values[t]
            gae=delta+self.gamma*self.lam*gae
            advantages[t]=gae
        returns=[a+v for a,v in zip(advantages,old_values)]
        adv=torch.tensor(advantages,dtype=torch.float32)
        if len(adv)>1:adv=(adv-adv.mean())/(adv.std(unbiased=False)+1e-8)
        for _ in range(self.epochs):
            losses=[]
            for i,item in enumerate(self.events):
                dist,v=self.model.distribution_value(item['request'])
                lp=dist.log_prob(torch.tensor(item['action']))
                ratio=(lp-item['old_logp']).exp()
                objective=torch.minimum(ratio*adv[i],torch.clamp(ratio,1-self.clip,1+self.clip)*adv[i])
                vloss=(v-torch.tensor(returns[i])).square()
                losses.append(-objective+0.5*vloss-0.01*dist.entropy())
            loss=torch.stack(losses).mean()
            self.opt.zero_grad();loss.backward()
            nn.utils.clip_grad_norm_(self.model.parameters(),0.5)
            self.opt.step()
        self.updates+=1
        self.save()
        print(f'PPO: update #{self.updates} loss={loss.item():.4f} checkpoint={self.output}',flush=True)

    def discard_incomplete(self,reason):
        if self.events:
            print(f'PPO: discarded {len(self.events)} unverified/incomplete decisions ({reason})',flush=True)
            self.skipped+=1
            self.events=[]; self.by_id={}; self.combat_result=None

    def save(self):
        self.output.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.output.with_suffix(self.output.suffix+'.tmp')
        torch.save({'schema':1,'model':self.model.state_dict(),'updates':self.updates,
                    'encoder':'combat_ppo_v1'},tmp)
        tmp.replace(self.output)
