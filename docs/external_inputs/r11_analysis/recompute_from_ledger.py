#!/usr/bin/env python3
"""Recompute key R10 and R9-B tables from the repository's existing CSV.
python recompute_from_ledger.py --repo . --out /tmp/r11-results
Requires numpy and scipy. Percent units, no new imputation or extrapolation.
"""
import argparse,csv,hashlib,json
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator

PIN='f326167ecb1cd7fba0486d39c4370ee9875e7d13'
CE=['BQMall','BasketballDrill','PartyScene','RaceHorsesC','FourPeople','Johnny','KristenAndSara']
BS=['BQTerrace','BasketballDrive','Cactus','MarketPlace','RitualDance']
QS=[22,27,32,37]

def read(source):
    data={};states={}
    for row in csv.DictReader(source.open(encoding='utf-8-sig',newline='')):
        model=row['experiment'];s=row['sequence'];q=int(row['qp'])
        if row['configuration']!='LB' or s not in CE+BS:continue
        if model not in ['R3-1','R9-9']+[f'R10-{i}' for i in range(1,7)]:continue
        if row['anchor_record_status']!='pass':raise ValueError('Reference failed')
        state=row['status']
        if state!='anchor_imputed' and not(state=='measured' and row['test_record_status']=='pass'):
            raise ValueError(f'Unusable {model}/{s}/{q}: {state}')
        for m,prefix in [('Current','anchor'),(model,'test')]:
            key=(m,s,q);v=np.array([float(row[prefix+'_'+x]) for x in ['rate_kbps','psnr_y_db','psnr_u_db','psnr_v_db']])
            if not np.isfinite(v).all() or v[0]<=0:raise ValueError('Invalid RD')
            if key in data and not np.array_equal(data[key],v):raise ValueError('Conflicting RD')
            data[key]=v;states[key]='measured' if m=='Current' else state
    return data,states

def bd(data,test,ref,s,qps):
    x=np.array([data[test,s,q] for q in qps]);y=np.array([data[ref,s,q] for q in qps]);v=[]
    for c in (1,2,3):
        a=x[np.argsort(x[:,c])];b=y[np.argsort(y[:,c])]
        if np.any(np.diff(a[:,c])<=0) or np.any(np.diff(b[:,c])<=0):raise ValueError('PSNR order')
        lo=max(a[0,c],b[0,c]);hi=min(a[-1,c],b[-1,c])
        if hi<=lo:raise ValueError('No common interval')
        f=PchipInterpolator(a[:,c],np.log(a[:,0]));g=PchipInterpolator(b[:,c],np.log(b[:,0]))
        v.append(float(100*np.expm1((f.integrate(lo,hi)-g.integrate(lo,hi))/(hi-lo))))
    return v+[(6*v[0]+v[1]+v[2])/8]

def write(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--out',type=Path,required=True);p.add_argument('--allow-updated-ledger',action='store_true');args=p.parse_args()
    source=args.repo/'docs/experiments/results/rd_points.csv';raw=source.read_bytes();blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if blob!=PIN and not args.allow_updated_ledger:raise ValueError('Ledger differs from pinned source; inspect changes or explicitly allow updated data')
    d,st=read(source);args.out.mkdir(parents=True,exist_ok=True);summary=[];seq=[];bt=[]
    for t in [f'R10-{i}' for i in range(1,7)]:
        for ref in ['Current','R9-9','R3-1']:
            for scope,ss in [('C',CE[:4]),('E',CE[4:]),('CE',CE),('complete5',[s for s in CE if s not in ['PartyScene','RaceHorsesC']])]:
                v=np.mean([bd(d,t,ref,s,QS) for s in ss],axis=0)
                summary.append(dict(test=t,reference=ref,scope=scope,imputed_points=sum(st[t,s,q]=='anchor_imputed' for s in ss for q in QS),**dict(zip(['Y','U','V','BD611'],v))))
            for s in CE:seq.append(dict(test=t,reference=ref,sequence=s,**dict(zip(['Y','U','V','BD611'],bd(d,t,ref,s,QS)))))
    for ref in ['Current','R3-1']:
        for qps,label in [(QS,'4pt_with_existing_imputations'),([27,32,37],'3pt_measured_diagnostic')]:
            allv=[]
            for s in BS:
                count=sum(st['R9-9',s,q]=='anchor_imputed' for q in qps)
                if len(qps)==3 and count:raise ValueError('Measured interval contains imputation')
                v=bd(d,'R9-9',ref,s,qps);allv.append(v)
                bt.append(dict(reference=ref,sequence=s,scope=label,imputed_points=count,**dict(zip(['Y','U','V','BD611'],v))))
            bt.append(dict(reference=ref,sequence='B-average',scope=label,imputed_points=sum(st['R9-9',s,q]=='anchor_imputed' for s in BS for q in qps),**dict(zip(['Y','U','V','BD611'],np.mean(allv,axis=0)))))
    write(args.out/'R10_key_summary.csv',summary);write(args.out/'R10_key_sequence.csv',seq);write(args.out/'R9_B_key_analysis.csv',bt)
    (args.out/'source_audit.json').write_text(json.dumps({'ledger_git_blob':blob,'pinned_match':blob==PIN,'new_imputation':False,'B_three_point_is_full_CTC':False},indent=2))
    print('Wrote derived tables to',args.out)
if __name__=='__main__':main()
