"""Behavior cloning: learn chosen real-game legal actions, not RL rewards."""
import argparse
import json
import random
from pathlib import Path

def main():
    import torch
    from .neural_policy import encode,make_model
    ap=argparse.ArgumentParser()
    ap.add_argument('--data',type=Path,default=Path(__file__).resolve().parents[1]/'trajectories')
    ap.add_argument('--checkpoint',type=Path,default=Path(__file__).resolve().parents[1]/'checkpoints'/'bc_demo.pt')
    ap.add_argument('--human-only',action='store_true',help='Use only native-verified human terminal demonstrations')
    ap.add_argument('--epochs',type=int,default=12)
    ap.add_argument('--seed',type=int,default=42)
    args=ap.parse_args()
    torch.manual_seed(args.seed);random.seed(args.seed)
    files=sorted(args.data.glob('*_verified.jsonl')) if args.data.is_dir() else [args.data]
    decisions=[]
    for file in files:
        for line in file.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            rec=json.loads(line)
            if rec.get('Executed') is not True:continue
            req=rec.get('FullRequest') or {}
            if args.human_only and req.get('DemonstrationSource') != 'HumanTerminal': continue
            actions=req.get('LegalActions')
            idx=(rec.get('PolicyResponse') or {}).get('ActionIndex')
            if not isinstance(actions,list) or not actions or type(idx) is not int or not 0<=idx<len(actions):continue
            decisions.append((req,actions,idx))
    if not decisions:raise SystemExit('No verified decisions with valid ActionIndex found')
    print(f'Loaded {len(decisions)} verified labeled decisions from {len(files)} file(s).')
    print('BEHAVIOR CLONING: imitates recorded actions; NOT PPO.')
    if args.human_only: print('Dataset filter: verified HumanTerminal decisions only.')
    random.shuffle(decisions)
    model=make_model(); opt=torch.optim.Adam(model.parameters(),lr=.002)
    for epoch in range(args.epochs):
        model.train();total=0;correct=0
        for req, actions, idx in decisions:
            feats=torch.tensor([encode(req,a) for a in actions],dtype=torch.float32)
            logits=model(feats).view(1,-1)
            target=torch.tensor([idx])
            loss=torch.nn.functional.cross_entropy(logits,target)
            opt.zero_grad();loss.backward();opt.step()
            total+=float(loss.item());correct+=int(logits.argmax().item()==idx)
        print(f'epoch {epoch+1:02d} | train_loss={total/len(decisions):.4f} | train_agreement={correct/len(decisions):.1%}')
    args.checkpoint.parent.mkdir(parents=True,exist_ok=True)
    torch.save({'feature_version':1,'state_dict':model.state_dict(),'algorithm':'behavior_cloning'},args.checkpoint)
    print(f'Saved checkpoint: {args.checkpoint}')
    print('Training-set agreement is NOT held-out accuracy or gameplay quality.')
if __name__=='__main__':main()
