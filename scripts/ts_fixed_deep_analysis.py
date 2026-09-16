#!/usr/bin/env python3
"""Target-aware analysis of completed CE results. Does not launch coding jobs."""
import argparse
import json
import math
from pathlib import Path
import statistics as st

import ts_fixed_analyze as base


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, default=Path('runs/ts_fixed_LB_CE_half'))
    p.add_argument('--anchor', type=Path, default=Path('scripts/JVET-hhi.xlsm'))
    p.add_argument('--out', type=Path, default=Path('runs/ts_fixed_LB_CE_half/target_analysis'))
    args = p.parse_args()
    audited = base.audit(args.run,args.anchor)
    anchor = base.reference_points(args.anchor)
    tests = {(r['fixed_predictor'],r['sequence'],r['qp']):r for r in audited}
    data = json.loads((args.run/'analysis_611/analysis.json').read_text())
    assert data['weighting'].startswith('BD_YUV=(6*BD_Y+BD_U+BD_V)/8 AFTER')
    seqrows = data['sequence_results']
    summary, bands, influence, contrasts = [], [], [], []
    for mode in base.MODES:
        rows = [r for r in seqrows if r['mode']==mode]
        ce = st.mean(r['YUV611_pchip_pct'] for r in rows)
        for target in (-.05,-.08,-.1):
            summary.append({'mode':mode,'CE_mean_pct':ce,'BCE_target_pct':target,
                            'required_B_mean_pct':(12*target-7*ce)/5,
                            'BCE_if_B_zero_pct':7*ce/12})
        for removed in rows:
            others = [r for r in rows if r is not removed]
            influence.append({'mode':mode,'removed_sequence':removed['sequence'],
                              'remaining_mean_pct':st.mean(r['YUV611_pchip_pct'] for r in others)})
        for seq in base.SEQUENCES:
            aa = [anchor[seq,q] for q in base.QPS]
            tt = [tests[mode,seq,q] for q in base.QPS]
            component_bands = {}
            for component,key in [('Y','ypsnr'),('U','upsnr'),('V','vpsnr')]:
                a = sorted((r[key],r['kbps']) for r in aa)
                t = sorted((r[key],r['kbps']) for r in tt)
                low,high = max(a[0][0],t[0][0]), min(a[-1][0],t[-1][0])
                cuts = [low,aa[2][key],aa[1][key],high] # QP37..32..27..22; clipped endpoints
                assert all(x<y for x,y in zip(cuts,cuts[1:]))
                areas = []
                for i,(lo,hi) in enumerate(zip(cuts,cuts[1:])):
                    def integrate(curve):
                        return base.pchip_integral([q for q,r in curve],[math.log(r) for q,r in curve],lo,hi)
                    area = integrate(t)-integrate(a)
                    areas.append(area)
                    component_bands[component,i] = 100*math.expm1(area/(hi-lo))
                actual = 100*math.expm1(sum(areas)/(high-low))
                expected = next(r for r in rows if r['sequence']==seq)[component+'_pchip_pct']
                assert abs(actual-expected)<1e-9
            for i,label in enumerate(('QP32-37','QP27-32','QP22-27')):
                row = {'mode':mode,'sequence':seq,'class':base.SEQUENCES[seq][0],'anchor_quality_band':label}
                row.update({c+'_BD_pct':component_bands[c,i] for c in ('Y','U','V')})
                row['YUV611_BD_pct'] = (6*row['Y_BD_pct']+row['U_BD_pct']+row['V_BD_pct'])/8
                bands.append(row)
    for other in ('gradient','directional'):
        for seq in base.SEQUENCES:
            r0=next(r for r in seqrows if r['sequence']==seq and r['mode']=='nopred')
            r1=next(r for r in seqrows if r['sequence']==seq and r['mode']==other)
            contrasts.append({'mode':other,'sequence':seq,
                              'difference_vs_nopred_pp':r1['YUV611_pchip_pct']-r0['YUV611_pchip_pct']})
    band_summary=[]
    for mode in base.MODES:
        for cls in ('CE','C','E'):
            for label in ('QP22-27','QP27-32','QP32-37'):
                vals=[r['YUV611_BD_pct'] for r in bands if r['mode']==mode and r['anchor_quality_band']==label
                      and (cls=='CE' or r['class']==cls)]
                band_summary.append({'mode':mode,'class':cls,'band':label,'mean_pct':st.mean(vals),
                                     'improved_sequences':sum(v<0 for v in vals)})
    # Hindsight sequence-level choice is only an overfitting diagnostic, NOT a CG oracle or adaptive bound.
    hindsight=[]
    for seq in base.SEQUENCES:
        candidates={'current':0.0, **{r['mode']:r['YUV611_pchip_pct'] for r in seqrows if r['sequence']==seq}}
        best=min(candidates,key=candidates.get)
        hindsight.append({'sequence':seq,'best_hindsight_mode':best,'BD_pct':candidates[best]})
    policies=[]
    for mode in ('nopred','directional'):
        for seq in base.SEQUENCES:
            result={'policy':mode+'_nominalQP_le27_else_current','sequence':seq,'class':base.SEQUENCES[seq][0],
                    'status':'exploratory RD-point reuse; NOT slice/TU QP-gated codec result'}
            for method in ('pchip','cubic'):
                values=[]
                for comp,key in [('Y','ypsnr'),('U','upsnr'),('V','vpsnr')]:
                    aa=[(anchor[seq,q][key],anchor[seq,q]['kbps']) for q in base.QPS]
                    chosen=[tests[mode,seq,q] if q<=27 else anchor[seq,q] for q in base.QPS]
                    bb=[(r[key],r['kbps']) for r in chosen]
                    val=base.bd_rate(aa,bb,method)[0]
                    values.append(val)
                    result[f'{comp}_{method}_pct']=val
                result[f'YUV611_{method}_pct']=(6*values[0]+values[1]+values[2])/8
            policies.append(result)
        ce=st.mean(r['YUV611_pchip_pct'] for r in policies if r['policy'].startswith(mode+'_'))
        for target in (-.05,-.08,-.1):
            summary.append({'mode':mode+'_nominalQP_le27_else_current_DIAGNOSTIC',
                            'CE_mean_pct':ce,'BCE_target_pct':target,
                            'required_B_mean_pct':(12*target-7*ce)/5,'BCE_if_B_zero_pct':7*ce/12})
    args.out.mkdir(parents=True,exist_ok=True)
    for filename,rows in [('B_required_targets.csv',summary),('quality_bands.csv',bands),
                          ('quality_band_summary.csv',band_summary),('leave_one_sequence_out.csv',influence),
                          ('paired_mode_contrasts.csv',contrasts),('hindsight_sequence_selection.csv',hindsight),
                          ('qp_policy_diagnostic.csv',policies)]:
        base.write_csv(args.out/filename,rows)
    report={'B_sequences':['MarketPlace','RitualDance','Cactus','BasketballDrive','BQTerrace'],
            'BCE_aggregation':'12 equal-weight sequences (5 B + 4 C + 3 E)',
            'targets':summary,'band_summary':band_summary,'leave_one_out':influence,'qp_policy_diagnostic':policies,
            'hindsight_selection':hindsight,'hindsight_mean_pct':st.mean(r['BD_pct'] for r in hindsight),
            'band_definition':'Integrate original 4-point PCHIP on three component-specific anchor-quality intervals; not 2-point refitting; band means not directly additive',
            'component_weighting':'(6 BD_Y+BD_U+BD_V)/8; each component uses own overlap'}
    (args.out/'target_analysis.json').write_text(json.dumps(report,indent=2))
    print('B requirements:',summary)
    print('Bands CE:',[r for r in band_summary if r['class']=='CE'])
    print('Hindsight only:',hindsight,report['hindsight_mean_pct'])
    for mode in ('nopred','directional'):
        subset=[r for r in policies if r['policy'].startswith(mode+'_')]
        print('QP policy diagnostic',mode,'pchip',st.mean(r['YUV611_pchip_pct'] for r in subset),
              'cubic',st.mean(r['YUV611_cubic_pct'] for r in subset),
              'leave PartyScene',st.mean(r['YUV611_pchip_pct'] for r in subset if r['sequence']!='PartyScene'))
    for mode in base.MODES:
        vals=[r['remaining_mean_pct'] for r in influence if r['mode']==mode]
        print('LOO',mode,min(vals),max(vals))
    for mode in ('gradient','directional'):
        vals=[r['difference_vs_nopred_pp'] for r in contrasts if r['mode']==mode]
        print('Compared to nopred',mode,st.mean(vals),'better on',sum(v<0 for v in vals),'of 7')


if __name__=='__main__':
    main()
