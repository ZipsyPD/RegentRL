"""Version 3 shared action-aware encoder for full-run RegentRL requests.

Uses only current observations and legal action values. No outcomes, future
state, or action-list position. Deterministic bounded hashing (256 floats).
"""
from __future__ import annotations
import hashlib
import math

FEATURES = 256
FEATURE_VERSION = 3

def _put(x, key, value=1.0):
    i = int.from_bytes(hashlib.blake2b(str(key).encode(), digest_size=8).digest(), 'little') % FEATURES
    x[i] += float(value)

def _walk(x, prefix, obj, depth=0):
    if depth > 7 or obj is None:
        return
    if isinstance(obj, bool):
        _put(x, prefix+'='+str(obj), .35)
    elif isinstance(obj, (int,float)):
        if math.isfinite(float(obj)):
            _put(x, prefix, math.copysign(math.log1p(abs(float(obj))), float(obj))/8)
    elif isinstance(obj,str):
        _put(x, prefix+'='+obj, .5)
    elif isinstance(obj,dict):
        for k,v in sorted(obj.items()):
            if k in ('NextObservation','Outcome','Reward','FutureState','Seed'):
                continue
            _walk(x, prefix+'/'+str(k),v,depth+1)
    elif isinstance(obj,(list,tuple)):
        _put(x, prefix+'/count', math.log1p(len(obj))/5)
        for i,v in enumerate(obj[:80]):
            # Bag-of-elements plus positional information for hand, enemies, and options.
            _walk(x,prefix+'/item',v,depth+1)
            if i < 12:
                _walk(x,prefix+'/'+str(i),v,depth+1)

def encode(request,action):
    x=[0.0]*FEATURES
    _put(x,'bias')
    _walk(x,'phase',str(request.get('Type','Unknown')))
    for key in ('RunObservation','Observation','CombatObservation','SelectionObservation', 'Options', 'Context'):
        if key in request:
            _walk(x,key,request[key])
    _walk(x,'candidate_action',action)
    return [math.tanh(v) for v in x]
