#!/usr/bin/env python3
"""Causal, finite TS rule suite. No codec invocation, no current-a selector input.

All candidate policies are fixed BEFORE full-corpus measurements. 61 members
fit the existing TSCPRED schedule limit (64). Values read from current q are
used only after the predictor at that position has been appended.
"""
from __future__ import annotations
import itertools, json
from pathlib import Path
import ts_learning as L

REV='TS-RULE-SUITE-v1'


def catalogue():
    out=[dict(id=name, family='fixed', kind='fixed', action=i) for i,name in enumerate(L.ACTIONS)]
    out += [dict(id='GUARD_EXTRA_NEAR',family='causal_gate',kind='guard'),
            dict(id='SINGLE_NEAR_F3',family='causal_gate',kind='single_near'),
            dict(id='NEAR_AGREEMENT_ONLY',family='causal_gate',kind='agreement')]
    for den in (64,16,4):
        out.append(dict(id=f'MARGIN_1_{den}',family='causal_gate',kind='margin',den=den))
    for k,initial_name,phase,feedback in itertools.product((2,4),('zero','half','equal'),(1,2),('hit','cost','margin')):
        initial={'zero':0,'half':k//2,'equal':k}[initial_name]
        out.append(dict(id=f'S_K{k}_{initial_name}_P{phase}_{feedback}',family='state',kind='state',
                        k=k,initial=initial,phase=phase,feedback=feedback,guard=False))
    for initial_name,phase in itertools.product(('zero','half','equal'),(1,2)):
        initial={'zero':0,'half':2,'equal':4}[initial_name]
        out.append(dict(id=f'HYBRID_K4_{initial_name}_P{phase}',family='hybrid',kind='state',
                        k=4,initial=initial,phase=phase,feedback='margin',guard=True))
    for cap in (2,4,8):
        out.append(dict(id=f'EXPERT_DEBT_B{cap}',family='expert_credit',kind='expert',cap=cap))
    assert len(out)==61 and len({c['id'] for c in out})==61
    return out


def sign(x): return (x>0)-(x<0)


def grid_action(k,r):
    if k not in (2,4) or not 0<=r<=k: raise ValueError('Unsupported grid')
    return 3+(4*r//k)


def guarded_action(row,action,k,r,tu):
    """Revoke only the largest EXTRA near vote, not the whole observation."""
    e=row['pred'][L.EQ]; p=row['pred'][action]
    if p==e or not row['cache']: return action,False
    h=row['h']
    d=[L.loss(m,e,tu['rice'],tu['range'],tu['rice_cutoff'])-
       L.loss(m,p,tu['rice'],tu['range'],tu['rice_cutoff']) if m else 0 for m in h]
    gain=k*sum(d[:2])+r*sum(d[2:])
    extra=(k-r)*max(0,*d[:2])
    if gain>extra: return action,False
    return L.EQ,True


def feedback_direction(row,r,cfg,tu):
    """Post-decision only. This function deliberately reads row['a']."""
    a=row['a']; h=row['h']; near=sum(bool(v) for v in h[:2]); far=sum(bool(v) for v in h[2:])
    if not a or near+far<3 or not near or not far: return 0,'ineligible'
    k=cfg['k']; grid=[row['pred'][grid_action(k,t)] for t in range(k+1)]
    if cfg['feedback']=='hit': values=[-int(a==p and p>1) for p in grid]
    else: values=[L.syntax(L.remap(a,p),tu['rice'],tu['range'],tu['rice_cutoff']) for p in grid]
    target=min(range(k+1),key=lambda t:(values[t],abs(t-r),-t))
    d=sign(target-r)
    if d: return d,'winner_cost' if cfg['feedback']!='hit' else 'hit'
    if cfg['feedback']=='margin':
        p=grid[r]; ne,fa,_=row['cache']
        real=lambda t:L.syntax(L.remap(a,t),tu['rice'],tu['range'],tu['rice_cutoff'])
        targetp=min(row['c0'],key=lambda t:(real(t),t!=p,k*ne[t]+r*fa[t],row['c0'].index(t)))
        if real(targetp)<real(p):
            z=near*(fa[targetp]-fa[p])-far*(ne[targetp]-ne[p])
            d=-sign(z)
            if d:return d,'candidate_margin'
    return 0,'neutral'


def predict(tu,cfg,trace=False,prepared=None):
    actions=[];pred=[];events=[]
    if cfg['kind']=='state':
        k=cfg['k']; phase=cfg['phase']; init=cfg['initial']
        state=(k+1)*phase-1 if init==k else init*phase
    debt={0:0,L.EQ:0,L.SP:0}
    for row in (L.causal_rows(tu) if prepared is None else prepared):
        before=state if cfg['kind']=='state' else None
        protected=False
        if cfg['kind']=='fixed': action=cfg['action']
        elif cfg['kind']=='state':
            r=state//phase; action=grid_action(k,r)
            if cfg['guard']: action,protected=guarded_action(row,action,k,r,tu)
        elif cfg['kind']=='guard': action,protected=guarded_action(row,L.SP,2,1,tu)
        elif cfg['kind']=='single_near': action=6 if sum(v>0 for v in row['h'][:2])==1 else L.SP
        elif cfg['kind']=='agreement':
            h=row['h']; action=L.SP if h[0]>0 and h[0]==h[1] else L.EQ
        elif cfg['kind']=='margin':
            action=L.SP
            if row['pred'][L.SP]!=row['pred'][L.EQ] and row['cache']:
                ne,fa,_=row['cache']; p=row['pred'][L.SP]; e=row['pred'][L.EQ]
                gain=2*(ne[e]-ne[p])+(fa[e]-fa[p])
                W=2*sum(v>0 for v in row['h'][:2])+sum(v>0 for v in row['h'][2:])
                if gain*cfg['den']<=168*W: action=L.EQ; protected=True
        elif cfg['kind']=='expert':
            # Immutable tie order: EQ, CURRENT, SP. The current q is not read.
            action=min((L.EQ,0,L.SP),key=lambda j:debt[j])
        else: raise ValueError('Unknown rule kind')
        p=row['pred'][action]
        pred.append(p);actions.append(action)
        # Current observation becomes available ONLY after this choice.
        direction=0; reason='not_state'
        if cfg['kind']=='state':
            direction,reason=feedback_direction(row,state//phase,cfg,tu)
            state=max(0,min((k+1)*phase-1,state+direction))
        elif cfg['kind']=='expert' and row['a'] and sum(v>0 for v in row['h'])>=3:
            c=lambda j:L.syntax(L.remap(row['a'],row['pred'][j]),tu['rice'],tu['range'],tu['rice_cutoff'])
            base=c(0)
            for j in (L.EQ,L.SP): debt[j]=max(-cfg['cap'],min(cfg['cap'],debt[j]+c(j)-base))
        if trace:
            events.append(dict(scan=row['scan'],a=row['a'],H=row['h'],pred=p,action=action,
                state_before=before,state_after=state if cfg['kind']=='state' else None,
                weight_before=before//phase if cfg['kind']=='state' else None,
                weight_after=state//phase if cfg['kind']=='state' else None,
                direction=direction,feedback=reason,guarded=protected,
                debt_after=dict(debt) if cfg['kind']=='expert' else None))
    return pred,actions,events


def signature(tu,pred):
    if len(pred)!=len(tu['scan']):raise ValueError('Wrong predictor length')
    return tuple(L.remap(abs(tu['q'][p]),pred[i]) for i,p in enumerate(tu['scan']))


if __name__=='__main__':
    print(json.dumps(dict(revision=REV,count=61,methods=catalogue()),ensure_ascii=False,indent=2))
