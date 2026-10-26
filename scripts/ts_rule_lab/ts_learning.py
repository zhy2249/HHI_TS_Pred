"""Causal TS features and integer scoring for the 61-rule offline benchmark.

Python >=3.10, standard library only. No trained thresholds or dataset results.
Current amplitude is returned only as a POST-decision observation; selectors
must not read it until their current predictor has been appended.
"""
from __future__ import annotations
from collections import Counter
from typing import Iterator

REV = 'TS-RULE-LAB-v1'
ACTIONS = ['CURRENT','STATIC_EQ','STATIC_SP','KEEP_F0','KEEP_F1','KEEP_F2',
           'KEEP_F3','KEEP_F4','KEEP_EQ_H','KEEP_SP_H']
EQ, SP = 7, 5
FEATURES = ['L','U','D','LL','UU','n','n_near','n_far','ones_near','ones_far',
 'twos_near','twos_far','unique_nonzero','span','near_agree','far_agree',
 'near_max_gt_far_max','eq_pred','sp_pred','pred_disagree','eq_margin1024','sp_margin1024',
 'prefix_nonzero1024','prefix_ones1024','prefix_twos1024','hist_mode','hist_mode_share1024',
 'recent16_ones1024','recent16_nonzero1024','prefix_count_capped64','log2w','log2h',
 'component','qp','slice_type','is_intra_cu','available_near','available_far']


def remap(a:int,p:int)->int:
    return 0 if a==0 else 1 if a==p else a+1 if a<p else a


def rice_length(v:int,rice:int,dr:int,cutoff:int)->int:
    if v < cutoff << rice:
        return (v >> rice) + 1 + rice
    cap=32-cutoff-dr
    if cap<0: raise ValueError('Unsupported Rice parameters')
    code=(v>>rice)-cutoff
    if code >= (1<<cap)-1: return cutoff+cap+dr
    prefix=0
    while code > (2<<prefix)-2: prefix+=1
    return cutoff+2*prefix+rice+1


def syntax(a:int,rice:int,dr:int,cutoff:int)->int:
    if a<2:return a
    return 2+sum(a>=k for k in (2,4,6,8))+(rice_length((a-10)>>1,rice,dr,cutoff) if a>=10 else 0)


def loss(m:int,p:int,rice:int,dr:int,cutoff:int,keep=True)->int:
    c=syntax(remap(m,p),rice,dr,cutoff)
    if not keep:return 168*c
    if p<=1:return 168*syntax(m,rice,dr,cutoff)
    if p==m:return 168
    if p==m-1:
        c=syntax(m,rice,dr,cutoff)
        return 168*c-4*(c-1)**2 if c<=22 else 1932
    if p==m+1:
        c=syntax(m+1,rice,dr,cutoff)
        return 168*c-4*(c-1)**2 if c<=11 else 84*c+525
    return 168*c


def candidate_order(h,history=0):
    current=max(h[:2]);first=0 if current<=1 else current
    if sum(v>0 for v in h)<3:return [first]
    c=[first]+sorted({0,*(v for v in h if v>1)}-{first})
    if history>1 and history not in c:c.append(history)
    return c


def scores_and_preds(h,rice,dr,cutoff,hist):
    current=max(h[:2]);n=sum(v>0 for v in h)
    c0=candidate_order(h);cp=candidate_order(h,hist)
    if n<3:return [current]*10,{},c0,cp
    ne={p:sum(loss(m,p,rice,dr,cutoff) for m in h[:2] if m) for p in cp}
    fa={p:sum(loss(m,p,rice,dr,cutoff) for m in h[2:] if m) for p in cp}
    scores={};pred=[current]
    for spatial in (False,True):
        ss=[sum((2 if spatial and j<2 else 1)*loss(m,p,rice,dr,cutoff,False)
                for j,m in enumerate(h) if m) for p in c0]
        pred.append(c0[min(range(len(c0)),key=ss.__getitem__)])
    for r in range(5):
        ss=[4*ne[p]+r*fa[p] for p in c0];scores[r]=ss
        pred.append(c0[min(range(len(c0)),key=ss.__getitem__)])
    for r in (4,2):
        pred.append(min(cp,key=lambda p:4*ne[p]+r*fa[p]))
    return pred,(ne,fa,scores),c0,cp


def ratio(n,d):return 1024*n//d if d else 0


def causal_rows(tu:dict)->Iterator[dict]:
    """Construct prefix features; never use source/sequence/POC/x/y identity.

    q is raster order and scan maps scan index to raster index. Zero positions
    remain in the prefix. Historical mode counts nonzero amplitudes, including
    1, and breaks equal-frequency ties toward the smaller amplitude.
    """
    q=tu['q'];scan=tu['scan'];w=tu['w'];height=tu['h'];N=w*height
    if len(q)!=N or sorted(scan)!=list(range(N)):raise ValueError('Invalid scan/q')
    inverse=[0]*N
    for s,p in enumerate(scan):inverse[p]=s
    freq=Counter();hist=0;best=0;nz=0;ones=0;twos=0;recent=[]
    for i,pos in enumerate(scan):
        x=pos%w;y=pos//w
        offsets=[-1 if x else 0,-w if y else 0,-1-w if x and y else 0,
                 -2 if x>=2 else 0,-2*w if y>=2 else 0]
        h=[]
        for off in offsets:
            if off and inverse[pos+off]>=i:raise ValueError('Noncausal neighborhood')
            h.append(abs(q[pos+off]) if off else 0)
        ps,cache,c0,cp=scores_and_preds(h,tu['rice'],tu['range'],tu['rice_cutoff'],hist)
        ne=[x for x in h[:2] if x];fa=[x for x in h[2:] if x];v=ne+fa
        margins=[]
        for r in (4,2):
            ss=sorted(cache[2][r]) if cache else []
            denom=168*(4*len(ne)+r*len(fa))
            margins.append(1024*(ss[1]-ss[0])//denom if len(ss)>1 and denom else 0)
        feat=h+[len(v),len(ne),len(fa),ne.count(1),fa.count(1),ne.count(2),fa.count(2),
                len(set(v)),max(v,default=0)-min(v,default=0),int(len(ne)==2 and len(set(ne))==1),
                int(len(fa)>=2 and len(set(fa))==1),int(max(ne,default=0)>max(fa,default=0)),
                ps[EQ],ps[SP],int(ps[EQ]!=ps[SP]),*margins,ratio(nz,i),ratio(ones,nz),ratio(twos,nz),
                hist,ratio(best,nz),ratio(recent.count(1),len(recent)),ratio(sum(bool(x) for x in recent),len(recent)),
                min(i,64),w.bit_length()-1,height.bit_length()-1,tu['component'],tu['qp'],
                {'B':0,'P':1,'I':2,'L':3}.get(tu['slice_type'],-1),tu['is_intra_cu'],sum(bool(v) for v in offsets[:2]),sum(bool(v) for v in offsets[2:])]
        assert len(feat)==len(FEATURES)
        a=abs(q[pos])
        yield dict(scan=i,x=feat,h=h,pred=ps,c0=c0,cplus=cp,cache=cache,a=a)
        recent.append(a)
        if len(recent)>16:recent.pop(0)
        if a:
            nz+=1;ones+=a==1;twos+=a==2;freq[a]+=1
            if freq[a]>best or (freq[a]==best and a<hist):hist=a;best=freq[a]
