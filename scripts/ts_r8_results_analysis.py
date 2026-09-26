#!/usr/bin/env python3
"""Read-only audit of seven received R8 LB CE experiments (19 excluded).

Component-first PCHIP BD, then 6:1:1; equal sequence weights. No imputation,
no source workbook writes, no inference of remote codec identity from 'pass'.
"""
import argparse
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import statistics as st

from ts_fixed_analyze import QPS, SEQUENCES, pchip_integral, self_test, workbook_bdrate, write_csv
from ts_fixed_workbook_analysis import CLASSES, points
from ts_predictor_cross_round_analysis import BANDS, compare, weighted
from ts_r3_results_analysis import common_bands, distribution
from ts_r6_results_analysis import check_columns, csv_columns, required_points

MODES = (1, 4, 8, 13, 15, 16, 17)
COMPONENTS = ('Y', 'U', 'V', 'weighted')
PRIMARY = {1:'R7-1', 4:'R8-1', 8:'R7-2', 13:'R8-1', 15:'R7-1', 16:'R8-1', 17:'R8-1'}


def summarize(rows):
    if len({r['sequence'] for r in rows}) != len(rows): raise ValueError('Duplicate sequences')
    vals = [r['weighted'] for r in rows]
    return dict(sequences=len(rows), **distribution(vals),
                **{c:st.mean(r[c] for r in rows) for c in 'YUV'},
                without_PartyScene=st.mean(r['weighted'] for r in rows if r['sequence']!='PartyScene'),
                without_best=(sum(vals)-min(vals))/(len(vals)-1),
                without_worst=(sum(vals)-max(vals))/(len(vals)-1),
                Y_contribution=st.mean(r['Y'] for r in rows)*6/8,
                UV_contribution=st.mean(r['U']+r['V'] for r in rows)/8)


def factorial(c00, c01, c10, c11):
    """2x2 interaction on identical FOUR-curve PSNR ranges, component by component.

First factor is sparse Smax. Second is guard or candidate completion.
*_effect are BD percentages; interaction_log_pp is 100*difference-of-log-gaps,
NOT subtraction of separately integrated BD percentages.
"""
    result = {}
    for i,c in enumerate('YUV',1):
        curves = [sorted((p[i],p[0]) for p in curve) for curve in (c00,c01,c10,c11)]
        lo,hi = max(curve[0][0] for curve in curves),min(curve[-1][0] for curve in curves)
        if hi<=lo: raise ValueError('No four-curve common quality range')
        mu = [pchip_integral([q for q,r in curve],[math.log(r) for q,r in curve],lo,hi)/(hi-lo)
              for curve in curves]
        effects = dict(sparse_without_second=mu[2]-mu[0], sparse_with_second=mu[3]-mu[1],
                       second_without_sparse=mu[1]-mu[0], second_with_sparse=mu[3]-mu[2])
        for k,v in effects.items(): result[f'{k}_{c}'] = 100*math.expm1(v)
        result[f'interaction_log_pp_{c}'] = 100*((mu[3]-mu[2])-(mu[1]-mu[0]))
        result[f'{c}_low_db'],result[f'{c}_high_db']=lo,hi
    for k in ('sparse_without_second','sparse_with_second','second_without_sparse','second_with_sparse','interaction_log_pp'):
        result[f'{k}_weighted']=weighted([result[f'{k}_{c}'] for c in 'YUV'])
    return result


def analyse(root):
    hashes={}; checks=[]; curves={}; raw=[]; timing=[]
    def remember(path):
        hashes[path]=hashlib.sha256(path.read_bytes()).hexdigest()
        return path
    anchor_path=remember(root/'scripts/JVET-hhi.xlsm')
    anchor=points(anchor_path,'Reference'); keys=required_points(anchor,SEQUENCES)
    for s in SEQUENCES: curves['Current',s]=[anchor[f'{s}.Q{q}.ecm.lb'][0] for q in QPS]
    specs=[('R2-2','experiments/ts_predictor_r2/r2_risk/LB_CE/JVET-hhi.xlsm',None),
           ('R3-1','experiments/ts_predictor_r3/r3_risk_guard/JVET-hhi.xlsm',None),
           ('R6-2','experiments/ts_predictor_r6/R6_2_JVET-hhi.xlsm','experiments/ts_predictor_r6/R6_2.csv'),
           ('R6-5','experiments/ts_predictor_r6/R6_5_JVET-hhi.xlsm','experiments/ts_predictor_r6/R6_5.csv'),
           ('R7-1','experiments/ts_predictor_r7/R7_1_JVET-hhi.xlsm','experiments/ts_predictor_r7/R7_1.csv'),
           ('R7-2','experiments/ts_predictor_r7/R7_2_JVET-hhi.xlsm','experiments/ts_predictor_r7/R7_2.csv')]
    specs += [(f'R8-{m}',f'experiments/ts_predictor_r8/r8_{m}_JVET-hhi.xlsm',
               f'experiments/ts_predictor_r8/{m}.csv') for m in MODES]
    for mode,name,csv_name in specs:
        path=remember(root/name); test=points(path,'Test')
        reference=points(path,'Reference')
        if reference!=anchor: raise ValueError(f'Non-Current Reference: {path}')
        required_points(test,SEQUENCES)
        if mode.startswith('R8-') and set(test)!=keys: raise ValueError(f'Unexpected R8 scope: {path}')
        if csv_name:
            csv_path=remember(root/csv_name); check_columns(path,[csv_path],keys)
            for key,value in csv_columns(csv_path).items():
                timing.append(dict(mode=mode,key=key,encode_seconds=value[4],decode_seconds=value[5],
                                   encoder_memory=value[6],decoder_memory=value[7],comparability='not_verified'))
        checks.append(dict(mode=mode,measured_CE_points=len(keys),imputed=0,Reference_equal=True,
                           CSV_B_J_equal=True if csv_name else None,excluded_other_points=len(set(test)-keys)))
        for s in SEQUENCES: curves[mode,s]=[test[f'{s}.Q{q}.ecm.lb'][0] for q in QPS]
    pairs=[(m,'Current') for m,_,_ in specs]
    for m in MODES:
        pairs += [(f'R8-{m}',ref) for ref in ('R3-1',PRIMARY[m])]
    pairs += [('R8-4','R7-2'),('R8-16','R8-15'),('R8-17','R8-4'),
              ('R8-4','R6-5'),('R8-8','R6-2'),('R7-2','R7-1')]
    pairs=list(dict.fromkeys(pairs))
    result=[]; summary=[]; bands=[]; band_summary=[]; jackknife=[]; qp_summary=[]
    vba_gap=0.0
    for mode,reference in pairs:
        rr=[]
        for s in SEQUENCES:
            a,t=curves[reference,s],curves[mode,s]
            meta=dict(mode=mode,reference=reference,sequence=s,**{'class':CLASSES[s]})
            r={**meta,**compare(a,t)}; rr.append(r)
            for i,c in enumerate('YUV',1):
                vba_gap=max(vba_gap,abs(r[c]-workbook_bdrate([(p[i],p[0]) for p in a],[(p[i],p[0]) for p in t])))
            for q,aa,tt in zip(QPS,a,t):
                raw.append(dict(**meta,qp=q,rate_delta_pct=100*(tt[0]/aa[0]-1),
                                **dict(zip(('reference_rate','reference_Y','reference_U','reference_V'),aa)),
                                **dict(zip(('test_rate','test_Y','test_U','test_V'),tt)),
                                **{f'{c}_delta_db':tt[i]-aa[i] for i,c in enumerate('YUV',1)},
                                identical_at_table_precision=aa==tt))
            if mode.startswith('R8-'):
                bands.extend({**meta,**b} for b in common_bands(curves['Current',s],a,t))
        result.extend(rr)
        for group in ('C','E','CE'):
            subset=[r for r in rr if r['class'] in group]
            summary.append(dict(mode=mode,reference=reference,group=group,**summarize(subset)))
            if mode.startswith('R8-'):
                for band in BANDS:
                    bb=[r for r in bands if r['mode']==mode and r['reference']==reference and r['class'] in group and r['band']==band]
                    band_summary.append(dict(mode=mode,reference=reference,group=group,band=band,
                        **{c:st.mean(r['direct_'+c] for r in bb) for c in COMPONENTS},
                        improved=sum(r['direct_weighted']<0 for r in bb)))
        for removed in SEQUENCES:
            jackknife.append(dict(mode=mode,reference=reference,removed=removed,
                                  mean_remaining=st.mean(r['weighted'] for r in rr if r['sequence']!=removed)))
        for q in QPS:
            qq=[r for r in raw if r['mode']==mode and r['reference']==reference and r['qp']==q]
            qp_summary.append(dict(mode=mode,reference=reference,qp=q,
                **{k:st.mean(r[k] for r in qq) for k in ('rate_delta_pct','Y_delta_db','U_delta_db','V_delta_db')},
                identical_points=sum(r['identical_at_table_precision'] for r in qq)))
    interactions=[]; interaction_summary=[]
    for label,names in [('sparse_x_guard',('R7-1','R7-2','R8-1','R8-4')),
                        ('sparse_x_completion',('R7-1','R8-15','R8-1','R8-16'))]:
        rr=[dict(factors=label,sequence=s,**{'class':CLASSES[s]},**factorial(*(curves[m,s] for m in names))) for s in SEQUENCES]
        interactions.extend(rr)
        for group in ('C','E','CE'):
            selected=[r for r in rr if r['class'] in group]
            numeric=[k for k in rr[0] if k not in ('factors','sequence','class') and not k.endswith(('_low_db','_high_db'))]
            interaction_summary.append(dict(factors=label,group=group,
                **{k:st.mean(r[k] for r in selected) for k in numeric}))
    identities=[]
    for ma,mb in combinations(MODES,2):
        for s in SEQUENCES:
            same=[q for q,a,b in zip(QPS,curves[f'R8-{ma}',s],curves[f'R8-{mb}',s]) if a==b]
            identities.append(dict(mode=f'R8-{ma}',reference=f'R8-{mb}',sequence=s,
                                   identical_points=len(same),same_qps=';'.join(map(str,same))))
    if vba_gap>1e-8: raise ValueError('Workbook VBA cross-check failed')
    for path,digest in hashes.items():
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise ValueError(f'Source changed: {path}')
    audit=dict(scope='R8 seven modes, LB CE 196 measured points; R8-19 excluded, no imputation',
               calculation='PCHIP per Y/U/V, then (6Y+U+V)/8, seven sequences equal weight',
               max_workbook_VBA_gap_pp=vba_gap,checks=checks,sources_unchanged=True,
               sources=[dict(path=str(p.relative_to(root)),sha256=d) for p,d in hashes.items()],
               remote_macro_binary_config_frames_hash_activity_verified=False,
               bootstrap='10000 sequence resamples, seed 20260918, descriptive; repeatedly reused CE is not holdout',
               limitations=['No R8 B or RA data; no BCE conclusion','No genuine run metadata or activity logs',
                            'No TU-size/n/cutoff or q-change attribution from workbooks',
                            'CSV timing is archived but not comparable without hardware/stats/thread evidence',
                            'Equal rounded RD points are not equal bitstreams; unequal points do not certify mode identity'])
    return dict(by_sequence=result,summary=summary,points=raw,qp_summary=qp_summary,
                common_quality_bands=bands,common_quality_band_summary=band_summary,
                leave_one_out=jackknife,factorial_by_sequence=interactions,factorial_summary=interaction_summary,
                identical_points=identities,unaudited_timing=timing),audit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--out',type=Path,default=Path('runs/ts_r8_results_20260926'))
    args=p.parse_args(); root=args.root.resolve()
    if not args.out.resolve().is_relative_to(root/'runs'): p.error('--out must be under project runs/')
    self_test(); outputs,audit=analyse(root); args.out.mkdir(parents=True,exist_ok=True)
    for name,rows in outputs.items(): write_csv(args.out/(name+'.csv'),rows)
    (args.out/'audit.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    for r in outputs['summary']:
        if r['group']=='CE': print(f"{r['mode']:5} vs {r['reference']:7}: {r['mean']:+.9f}% median={r['median']:+.6f}% wins={r['improved']}/7")


if __name__=='__main__': main()
