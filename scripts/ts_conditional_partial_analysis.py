#!/usr/bin/env python3
"""Provisional LB CE analysis: only missing QP22 may use anchor, explicitly labelled."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics as st

from ts_fixed_analyze import SEQUENCES, QPS, bd_rate, workbook_bdrate, write_csv, self_test
from ts_fixed_workbook_analysis import points

MODES = ('q32', 'conf2', 'prev', 'ewma', 'q32_ewma')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('experiments/ts_conditional_v1'))
    parser.add_argument('--anchor', type=Path, default=Path('scripts/JVET-hhi.xlsm'))
    parser.add_argument('--out', type=Path, default=Path('runs/ts_conditional_partial_20260918'))
    parser.add_argument('--modes', default=','.join(MODES), help='Comma-separated revision1 or R2 mode names')
    parser.add_argument('--phase-folder', choices=('LB_BCE','LB_CE'), default='LB_BCE')
    args = parser.parse_args()
    modes = tuple(args.modes.split(','))
    supported = (*MODES, 'r2_modal', 'r2_risk', 'r2_cn_log', 'r2_cn_frac')
    if len(set(modes)) != len(modes) or any(m not in supported for m in modes):
        parser.error('Invalid or duplicate modes')
    self_test()
    anchor = points(args.anchor, 'Reference')
    raw, results, sources, missing = [], [], [], []
    gap = 0.0
    for mode in modes:
        path = args.root/mode/args.phase_folder/'JVET-hhi.xlsm'
        test = points(path, 'Test')
        assert points(path, 'Reference') == anchor, (mode, 'reference mismatch')
        # Supplementary flat CSVs are checked, never used to silently replace workbook data.
        csv_audits = []
        for cp in path.parent.glob('*.csv'):
            checked = 0
            with cp.open(encoding='utf-8-sig', newline='') as f:
                for row in csv.reader(f):
                    if len(row) >= 5 and '.ecm.lb' in row[0]:
                        assert row[0] in test and [float(x) for x in row[1:5]] == test[row[0]][0], (cp, row[0])
                        checked += 1
            csv_audits.append(dict(path=str(cp), sha256=hashlib.sha256(cp.read_bytes()).hexdigest(), checked_points=checked))
        sources.append(dict(mode=mode, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), csv_audits=csv_audits))
        for seq, (cls, _) in SEQUENCES.items():
            ac, tc, imputed, unavailable = [], [], [], []
            for qp in QPS:
                key = f'{seq}.Q{qp}.ecm.lb'
                a = anchor[key][0]
                assert anchor[key][1] == 'pass'
                if key in test:
                    assert test[key][1] == 'pass', (mode, key)
                    t, origin = test[key][0], 'measured'
                else:
                    missing.append(dict(mode=mode, sequence=seq, qp=qp, action='anchor_fill' if qp == 22 else 'exclude_curve'))
                    if qp == 22:
                        t, origin = a, 'anchor_imputed_QP22'
                        imputed.append(qp)
                    else:
                        t, origin = None, 'missing_not_imputed'
                        unavailable.append(qp)
                raw.append(dict(mode=mode, sequence=seq, qp=qp, origin=origin,
                    identical_to_anchor=(t == a) if t else '',
                    **{f'anchor_{c}':v for c,v in zip(('kbps','Y','U','V'),a)},
                    **{f'test_{c}':v for c,v in zip(('kbps','Y','U','V'),t or ['']*4)}))
                ac.append(a); tc.append(t)
            if unavailable:
                continue
            row = dict(mode=mode, sequence=seq, **{'class':cls},
                       provenance='QP22_imputed' if imputed else 'fully_measured')
            for method in ('pchip', 'cubic'):
                vals = []
                for i,c in enumerate('YUV',1):
                    aa, tt = [(p[i],p[0]) for p in ac], [(p[i],p[0]) for p in tc]
                    value, _, _ = bd_rate(aa,tt,method)
                    row[f'{c}_{method}'] = value; vals.append(value)
                    if method == 'pchip':
                        gap = max(gap,abs(value-workbook_bdrate(aa,tt)))
                row[f'weighted_{method}'] = (6*vals[0]+vals[1]+vals[2])/8
            results.append(row)
    common = set.intersection(*[{r['sequence'] for r in results if r['mode']==m} for m in modes])
    common_measured = set.intersection(*[{r['sequence'] for r in results if r['mode']==m and r['provenance']=='fully_measured'} for m in modes])
    summaries = []
    for mode in modes:
        for group in ('C','E','CE','common','fully_measured','common_fully_measured'):
            rs = [r for r in results if r['mode']==mode and (
                (group in ('C','E','CE') and r['class'] in group) or
                (group=='common' and r['sequence'] in common) or
                (group=='fully_measured' and r['provenance']=='fully_measured') or
                (group=='common_fully_measured' and r['sequence'] in common_measured))]
            if not rs:
                continue
            v = [r['weighted_pchip'] for r in rs]
            rng = random.Random(20260918)
            boot = sorted(st.mean(rng.choices(v,k=len(v))) for _ in range(10000))
            percentiles = st.quantiles(v, n=100, method='inclusive') if len(v)>1 else [v[0]]*99
            summaries.append(dict(mode=mode,group=group,n=len(rs),imputed_curves=sum(r['provenance']!='fully_measured' for r in rs),
                sequences=';'.join(r['sequence'] for r in rs), mean=st.mean(v), median=st.median(v),
                stddev=st.stdev(v) if len(v)>1 else 0, min=min(v),max=max(v), improved=sum(x<0 for x in v),
                ci_low=boot[249],ci_high=boot[9749],cubic=st.mean(r['weighted_cubic'] for r in rs),
                p10=percentiles[9],p90=percentiles[89],
                loo_min=min((sum(v)-x)/(len(v)-1) for x in v) if len(v)>1 else '',
                loo_max=max((sum(v)-x)/(len(v)-1) for x in v) if len(v)>1 else '',
                **{c:st.mean(r[f'{c}_pchip'] for r in rs) for c in 'YUV'}))
    sensitivity = []
    # Hypothetical QP22 rate shifts at anchor PSNR, not measurements or error bounds.
    for mode in modes:
        valid = [r['sequence'] for r in results if r['mode']==mode]
        for shift in (-1.0, -0.5, 0.0, 0.5, 1.0):
            values = []
            for seq in valid:
                rs = [r for r in raw if r['mode']==mode and r['sequence']==seq]
                component_bd = []
                for c in 'YUV':
                    a = [(r['anchor_'+c],r['anchor_kbps']) for r in rs]
                    t = [(r['test_'+c],r['test_kbps']*(1+shift/100 if r['origin']=='anchor_imputed_QP22' else 1)) for r in rs]
                    component_bd.append(bd_rate(a,t)[0])
                values.append((6*component_bd[0]+component_bd[1]+component_bd[2])/8)
            sensitivity.append(dict(mode=mode, hypothetical_missing_QP22_rate_shift_pct=shift,
                                    sequences=len(valid), weighted_mean=st.mean(values)))
    activity = []
    for mode in modes:
        for qp in QPS:
            rs = [r for r in raw if r['mode']==mode and r['qp']==qp and r['origin']=='measured']
            activity.append(dict(mode=mode, qp=qp, measured=len(rs),
                equal_RD_points=sum(r['identical_to_anchor'] for r in rs),
                changed_RD_points=sum(not r['identical_to_anchor'] for r in rs),
                mean_same_qp_rate_pct=st.mean(100*(r['test_kbps']/r['anchor_kbps']-1) for r in rs) if rs else '',
                **{f'mean_{c}_delta_db': st.mean(r['test_'+c]-r['anchor_'+c] for r in rs) if rs else '' for c in 'YUV'}))
    # Secondary mechanism comparisons only; Current remains the sole formal anchor.
    paired, paired_summary = [], []
    for reference, candidate in (('r2_modal','r2_risk'), ('r2_cn_log','r2_cn_frac')):
        if reference not in modes or candidate not in modes:
            continue
        for group, sequences in (('all_available',common), ('common_fully_measured',common_measured)):
            values, filled = [], 0
            for seq in SEQUENCES:
                if seq not in sequences:
                    continue
                curves = []
                has_fill = False
                for mode in (reference, candidate):
                    rs = sorted([r for r in raw if r['mode']==mode and r['sequence']==seq],key=lambda r:r['qp'])
                    has_fill |= any(r['origin']=='anchor_imputed_QP22' for r in rs)
                    curves.append([[r['test_kbps'],*[r['test_'+c] for c in 'YUV']] for r in rs])
                a, t = curves
                v = [bd_rate([(p[i],p[0]) for p in a],[(p[i],p[0]) for p in t])[0] for i in (1,2,3)]
                value = (6*v[0]+v[1]+v[2])/8
                values.append(value); filled += has_fill
                paired.append(dict(reference_method=reference,candidate_method=candidate,group=group,sequence=seq,
                                   imputed=has_fill,Y=v[0],U=v[1],V=v[2],weighted=value))
            if not values:
                continue
            rng=random.Random(20260919)
            boot=sorted(st.mean(rng.choices(values,k=len(values))) for _ in range(10000))
            paired_summary.append(dict(reference_method=reference,candidate_method=candidate,group=group,
                n=len(values),imputed_curves=filled,mean=st.mean(values),improved=sum(v<0 for v in values),
                ci_low=boot[249],ci_high=boot[9749]))
    required_b = []
    for r in summaries:
        if r['group']=='CE' and r['n']==7:
            for target in (-.05,-.08,-.10):
                required_b.append(dict(mode=r['mode'],ce_mean=r['mean'],imputed_curves=r['imputed_curves'],
                    target_bce=target,required_b_mean=(12*target-7*r['mean'])/5))
    args.out.mkdir(parents=True, exist_ok=True)
    for name,rows in [('points',raw),('by_sequence',results),('summary',summaries),('missing',missing),('activity',activity),
                      ('imputation_sensitivity',sensitivity),('paired_by_sequence',paired),('paired_summary',paired_summary),
                      ('required_b',required_b)]:
        if rows:
            write_csv(args.out/(name+'.csv'), rows)
    audit=dict(sources=sources,anchor_predictor='current',anchor_sha256=hashlib.sha256(args.anchor.read_bytes()).hexdigest(),
        measured_points=sum(r['origin']=='measured' for r in raw),imputed_points=sum(r['origin']=='anchor_imputed_QP22' for r in raw),
        missing=missing,common_sequences=sorted(common),common_fully_measured=sorted(common_measured),vba_max_gap_pp=gap,
        limitation='Only workbook/CSV numeric audit. Missing QP22 replaced by anchor per user; no QP27 imputation. Bootstrap conditional on imputation; not uncertainty of missing results. RD equality is not bitstream equality.')
    (args.out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    for r in summaries:
        print(f"{r['mode']:9} {r['group']:22} n={r['n']} fill={r['imputed_curves']} mean={r['mean']:+.6f}%")


if __name__ == '__main__':
    main()
