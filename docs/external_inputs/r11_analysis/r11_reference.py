#!/usr/bin/env python3
"""R11 selector/stencil mathematical reference; NOT a codec patch.
Expert actions and frozen rate tables are supplied by the caller.
No model here reads the current or future target to choose its own action.
"""
from __future__ import annotations
from typing import Sequence
import random,json
from pathlib import Path

Action=tuple[int,int]
OFFSETS=((-1,0),(0,-1),(-1,-1),(-2,0),(0,-2))

def remap(a:int,action:Action)->int:
    p,k=action
    if a<0 or k not in (0,1):raise ValueError('invalid amplitude/action')
    if p<=k+1 or a<=k:return a
    return k+1 if a==p else a+1 if a<p else a

def lex_select(actions:Sequence[Action],ci:Sequence[Sequence[int]],cf:Sequence[Sequence[int]])->int:
    m=len(actions)
    if m<1 or len(ci)!=len(cf):raise ValueError('invalid loss rows')
    if any(len(r)!=m for r in list(ci)+list(cf)):raise ValueError('loss columns')
    if not ci or len(set(actions))==1:return 0
    integer=[sum(r[e] for r in ci) for e in range(m)]
    tied=[e for e,x in enumerate(integer) if x==min(integer)]
    return min(tied,key=lambda e:(sum(r[e] for r in cf),e))

def evidence_select(actions:Sequence[Action],ci,cf,mapped_rows,*,fallback_r3=False)->int:
    if len(mapped_rows)!=len(ci):raise ValueError('mapping row count')
    if not actions:return 0
    if len(set(actions))==1:return 0
    # Structural evidence: equal rounded costs alone are NOT sufficient.
    effective=sum(len(set(row))>1 for row in mapped_rows)
    if fallback_r3 and effective==0:
        if len(actions)<3:raise ValueError('R3 expert required')
        return 2
    return lex_select(actions,ci,cf)

def validation_positions(i:int,positions:Sequence[tuple[int,int]],cg_ids:Sequence[int],
                         amplitudes:Sequence[int],scope:str='base')->list[int]:
    if scope not in ('base','cg8','tu8'):raise ValueError(scope)
    if len(positions)!=len(cg_ids) or len(positions)!=len(amplitudes):raise ValueError('geometry size')
    inv={xy:j for j,xy in enumerate(positions)}
    x,y=positions[i];out=[]
    for dx,dy in OFFSETS:
        j=inv.get((x+dx,y+dy))
        if j is not None and j<i and cg_ids[j]==cg_ids[i] and amplitudes[j]>0:out.append(j)
    if scope=='base':return out
    extra=[]
    for dx in range(-3,4):
        for dy in range(-3,4):
            radius=abs(dx)+abs(dy)
            if radius<1 or radius>3:continue
            j=inv.get((x+dx,y+dy))
            if j is None or j>=i or j in out or amplitudes[j]<=0:continue
            if scope=='cg8' and cg_ids[j]!=cg_ids[i]:continue
            extra.append((int(cg_ids[j]!=cg_ids[i]),radius,-j,y+dy,x+dx,j))
    for *_,j in sorted(extra):
        if len(out)>=8:break
        out.append(j)
    return out

def test():
    rng=random.Random(110928);counts={'selector_cases':0,'preserved_unique_CI_winners':0,'geometry_cases':0,'no_evidence_checks':0}
    for _ in range(10000):
        actions=[(p if p>=2 else 0,0) for p in [rng.randrange(8) for _ in range(3)]];v=rng.randrange(9)
        targets=[rng.randrange(8) for _ in range(v)];mapped=[[remap(target,a) for a in actions] for target in targets]
        itables=[[rng.randrange(8) for _ in range(16)] for _ in range(v)]
        ftables=[[rng.randrange(300000) for _ in range(16)] for _ in range(v)]
        current_table=[rng.randrange(300000) for _ in range(16)]
        ci=[[table[m] for m in row] for table,row in zip(itables,mapped)]
        cf=[[table[m] for m in row] for table,row in zip(ftables,mapped)]
        alt=[[current_table[m] for m in row] for row in mapped]
        b=lex_select(actions,ci,cf);n=lex_select(actions,ci,alt)
        if v and len(set(actions))>1:
            sums=[sum(r[e] for r in ci) for e in range(3)]
            if sums.count(min(sums))==1:
                assert b==n==sums.index(min(sums));counts['preserved_unique_CI_winners']+=1
        # Different CF tie-break does not leave the integer minimizer set.
        if v and len(set(actions))>1:assert sum(r[n] for r in ci)==min(sum(r[e] for r in ci) for e in range(3))
        # R11-1 differs only on zero structural evidence.
        f=evidence_select(actions,ci,cf,mapped,fallback_r3=True)
        if any(len(set(r))>1 for r in mapped):assert f==b
        if len(set(actions))>1 and not any(len(set(r))>1 for r in mapped):assert f==2;counts['no_evidence_checks']+=1
        counts['selector_cases']+=1
    # Grouped diagonal order constructed for testing, not a VTM normative scan implementation.
    for width,height in [(4,4),(8,4),(8,8),(16,8),(2,8),(8,2)]:
        blocks=sorted([(x,y) for y in range(0,height,4) for x in range(0,width,4)],key=lambda p:(sum(p),p[0]))
        pos=[];cg=[]
        for c,(bx,by) in enumerate(blocks):
            local=sorted([(x,y) for y in range(by,min(by+4,height)) for x in range(bx,min(bx+4,width))],key=lambda p:(sum(p),p[0]))
            pos+=local;cg += [c]*len(local)
        for _ in range(12):
            amplitudes=[rng.randrange(5) for p in pos]
            for i in range(len(pos)):
                base=validation_positions(i,pos,cg,amplitudes)
                same=validation_positions(i,pos,cg,amplitudes,'cg8')
                cross=validation_positions(i,pos,cg,amplitudes,'tu8')
                assert cross[:len(same)]==same
                for scope in ['cg8','tu8']:
                    chosen=validation_positions(i,pos,cg,amplitudes,scope)
                    assert chosen[:len(base)]==base and len(chosen)<=8 and len(set(chosen))==len(chosen)
                    assert all(j<i and amplitudes[j]>0 for j in chosen)
                    if scope=='cg8':assert all(cg[j]==cg[i] for j in chosen)
                    poisoned=amplitudes.copy();poisoned[i:]=[rng.randrange(1000) for _ in poisoned[i:]]
                    assert validation_positions(i,pos,cg,poisoned,scope)==chosen
                    counts['geometry_cases']+=1
    counts['status']='passed';counts['limits']='Synthetic selector and geometry invariants only; no native codec, rate, speed or real CABAC-state verification.'
    return counts

if __name__=='__main__':
    result=test();Path(__file__).with_name('r11_reference_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
