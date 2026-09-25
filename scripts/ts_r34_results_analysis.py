#!/usr/bin/env python3
"""Read-only R3 B / R4 CE result audit (2026-09-21).

Current is the only primary anchor. Missing R3-1/2 B QP22 may use the
corresponding complete Current RD point ONLY with --impute-r3-b-qp22.
All other missing/failed/partial points fail closed. Source files are not edited.
BD-rate is computed component-first, then (6Y+U+V)/8, sequence-equal means.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics as st

from ts_fixed_analyze import ALL_SEQUENCES, QPS, pchip_integral, self_test, workbook_bdrate, write_csv
from ts_fixed_workbook_analysis import CLASSES, points
from ts_predictor_cross_round_analysis import BANDS, compare, quality_bands, weighted
from ts_predictor_naming import R4_MODE_NUMBERS, experiment_directory
from ts_r3_results_analysis import common_bands, distribution

R3 = ('r3_risk_guard', 'r3_risk_guard_y')
R4 = tuple(R4_MODE_NUMBERS)
COMPONENTS = ('Y', 'U', 'V', 'weighted')
GROUPS = ('B', 'C', 'E', 'CE', 'BCE')


def csv_points(path):
    """Skip header and wholly empty template rows, never skip partial failures."""
    result, seen = {}, set()
    with path.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.reader(f):
            if not row or '.ecm.' not in row[0]:
                continue
            key = row[0]
            if key in seen:
                raise ValueError(f'Duplicate CSV key: {path} {key}')
            seen.add(key)
            if len(row) == 1 or not any(v.strip() for v in row[1:]):
                continue
            if len(row) < 10 or row[9].strip() != 'pass':
                raise ValueError(f'Incomplete/failed CSV point: {path} {key}')
            values = list(map(float, row[1:5]))
            if not all(math.isfinite(v) for v in values) or values[0] <= 0:
                raise ValueError(f'Invalid CSV RD point: {path} {key}')
            result[key] = (values, 'pass')
    return result


def resolve_point(mode, seq, qp, test, anchor, allow_imputation=False):
    key = f'{seq}.Q{qp}.ecm.lb'
    if key not in anchor or anchor[key][1] != 'pass':
        raise ValueError(f'Missing/failed Current: {key}')
    if key in test:
        values, status = test[key]
        if status != 'pass' or len(values) != 4 or not all(math.isfinite(v) for v in values) or values[0] <= 0:
            raise ValueError(f'Invalid measured point: {mode} {key}')
        return list(values), False
    if allow_imputation and mode in R3 and CLASSES[seq] == 'B' and qp == 22:
        return list(anchor[key][0]), True
    raise ValueError(f'Missing point, imputation disallowed: {mode} {key}')


def measured_three_point(anchor, test):
    """Diagnostic 27/32/37-only PCHIP, distinct curves/range from main four-point BD."""
    if len(anchor) != 3 or len(test) != 3:
        raise ValueError('Three measured points required')
    result = {}
    for i, comp in enumerate('YUV', 1):
        curves = [sorted((p[i], p[0]) for p in curve) for curve in (anchor, test)]
        for curve in curves:
            if not all(math.isfinite(q) and math.isfinite(r) and r > 0 for q, r in curve):
                raise ValueError('Invalid RD point')
            if not all(q0 < q1 and r0 < r1 for (q0, r0), (q1, r1) in zip(curve, curve[1:])):
                raise ValueError('Non-monotonic three-point curve')
        lo, hi = max(c[0][0] for c in curves), min(c[-1][0] for c in curves)
        if hi <= lo:
            raise ValueError('No common quality interval')
        areas = [pchip_integral([q for q, r in c], [math.log(r) for q, r in c], lo, hi) for c in curves]
        result[comp] = 100 * math.expm1((areas[1] - areas[0]) / (hi - lo))
    result['weighted'] = weighted([result[c] for c in 'YUV'])
    return result


def groups(rows):
    for group in GROUPS:
        selected = [r for r in rows if r['class'] in group]
        expected = {s for s, (c, _) in ALL_SEQUENCES.items() if c in group}
        if {r['sequence'] for r in selected} == expected:
            yield group, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('experiments'))
    parser.add_argument('--anchor', type=Path, default=Path('scripts/JVET-hhi.xlsm'))
    parser.add_argument('--fixed-root', type=Path, default=Path('runs/ts_fixed_LB_CE_half'))
    parser.add_argument('--out', type=Path, default=Path('runs/ts_r34_results_20260921'))
    parser.add_argument('--impute-r3-b-qp22', action='store_true')
    args = parser.parse_args()
    self_test()
    hashes, sources, audits, imputed = {}, [], [], []

    def record(path, **meta):
        hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        sources.append(dict(path=str(path), sha256=hashes[path], **meta))

    record(args.anchor, role='Current Reference')
    anchor = points(args.anchor, 'Reference')
    # Also audit the user's copy; never substitute a different Reference silently.
    user_anchor = args.root / 'JVET-hhi.xlsm'
    record(user_anchor, role='user Current copy, equality audit')
    if points(user_anchor, 'Reference') != anchor:
        raise ValueError('User Current copy differs from canonical Current')
    specs = []
    for number, mode in enumerate(R3, 1):
        directory = args.root / 'ts_predictor_r3' / mode
        specs.append((mode, 'BCE', directory / 'JVET-hhi.xlsm',
                      [directory / f'R3_{number}.csv', directory / f'R3_{number}_B.csv']))
    for mode, number in R4_MODE_NUMBERS.items():
        directory = experiment_directory(args.root / 'ts_predictor_r4', mode)
        specs.append((mode, 'CE', directory / f'R4_{number}_JVET-hhi.xlsm',
                      [directory / f'R4_{number}.csv']))
    for mode in ('nopred', 'directional'):
        specs.append((mode, 'BCE', args.fixed_root / mode / 'JVET-hhi.xlsm', []))

    curves, acurves, flags, perseq, raw, bands = {}, {}, {}, [], [], []
    max_vba_gap = 0.0
    for mode, classes, path, csv_paths in specs:
        record(path, mode=mode, role='result workbook')
        if points(path, 'Reference') != anchor:
            raise ValueError(f'Non-Current Reference: {path}')
        test = points(path, 'Test')
        combined = {}
        for csv_path in csv_paths:
            record(csv_path, mode=mode, role='RD CSV audit')
            cp = csv_points(csv_path)
            if combined.keys() & cp.keys():
                raise ValueError(f'Overlapping CSV sets: {csv_path}')
            combined.update(cp)
        if csv_paths and combined != test:
            raise ValueError(f'CSV/workbook value, status or key mismatch: {path}')
        expected_keys = {f'{s}.Q{q}.ecm.lb' for s, (c, _) in ALL_SEQUENCES.items()
                         if c in classes for q in QPS}
        if csv_paths and set(test) - expected_keys:
            raise ValueError(f'Unexpected result scope: {path}')
        audits.append(dict(mode=mode, workbook_numeric_points=len(test),
                           measured_lb_points=len(test.keys() & expected_keys),
                           csv_equal=True if csv_paths else None, reference_equal=True))
        for seq, (cls, _) in ALL_SEQUENCES.items():
            if cls not in classes:
                continue
            a, t, mask = [], [], []
            for qp in QPS:
                key = f'{seq}.Q{qp}.ecm.lb'
                value, filled = resolve_point(mode, seq, qp, test, anchor, args.impute_r3_b_qp22)
                a.append(anchor[key][0]); t.append(value); mask.append(filled)
                meta = dict(mode=mode, sequence=seq, **{'class': cls}, qp=qp,
                            imputed=filled, origin='Current replacement' if filled else 'measured')
                if filled:
                    imputed.append(dict(**meta, key=key, source=str(path)))
                raw.append(dict(**meta, identical_to_Current=a[-1] == value,
                    **dict(zip(('anchor_rate','anchor_Y','anchor_U','anchor_V'), a[-1])),
                    **dict(zip(('test_rate','test_Y','test_U','test_V'), value)),
                    rate_delta_pct=100*(value[0]/a[-1][0]-1),
                    **{f'{c}_delta_db': value[i]-a[-1][i] for i,c in enumerate('YUV',1)}))
            acurves[seq], curves[mode,seq], flags[mode,seq] = a, t, mask
            meta = dict(mode=mode, sequence=seq, **{'class': cls}, imputed_points=sum(mask))
            row = dict(**meta, **compare(a,t), cubic=compare(a,t,'cubic')['weighted'])
            perseq.append(row)
            bands.extend(dict(**meta, **r) for r in quality_bands(a,t))
            for i,c in enumerate('YUV',1):
                gap = abs(row[c]-workbook_bdrate([(p[i],p[0]) for p in a], [(p[i],p[0]) for p in t]))
                max_vba_gap = max(max_vba_gap,gap)

    summaries, band_summary, qp_summary, loo, contributions = [], [], [], [], []
    for mode, *_ in specs:
        mode_rows = [r for r in perseq if r['mode']==mode]
        for group, rr in groups(mode_rows):
            meta = dict(mode=mode,group=group,sequences=len(rr),imputed_points=sum(r['imputed_points'] for r in rr))
            gain_mass = -sum(min(r['weighted'],0) for r in rr)
            loss_mass = sum(max(r['weighted'],0) for r in rr)
            summaries.append(dict(**meta,**distribution([r['weighted'] for r in rr]),
                **{c:st.mean(r[c] for r in rr) for c in ('Y','U','V','cubic')},
                without_PartyScene=st.mean(r['weighted'] for r in rr if r['sequence']!='PartyScene'),
                Y_contribution=st.mean(r['Y'] for r in rr)*.75,
                U_contribution=st.mean(r['U'] for r in rr)/8,
                V_contribution=st.mean(r['V'] for r in rr)/8,
                gain_mass_pp=gain_mass,loss_mass_pp=loss_mass))
            for r in rr:
                loo.append(dict(**meta,removed=r['sequence'],mean_remaining=st.mean(v['weighted'] for v in rr if v is not r)))
                contributions.append(dict(**meta,sequence=r['sequence'],contribution_pp=r['weighted']/len(rr),
                    gain_mass_share=-min(r['weighted'],0)/gain_mass if gain_mass else 0,
                    loss_mass_share=max(r['weighted'],0)/loss_mass if loss_mass else 0))
            for band in BANDS:
                bb = [r for r in bands if r['mode']==mode and r['class'] in group and r['band']==band]
                band_summary.append(dict(**meta,band=band,**{c:st.mean(r[c] for r in bb) for c in COMPONENTS},
                    improved=sum(r['weighted']<0 for r in bb)))
            for qp in QPS:
                pp = [r for r in raw if r['mode']==mode and r['class'] in group and r['qp']==qp]
                # Never mix placeholders into measured-only QP summaries.
                measured = [r for r in pp if not r['imputed']]
                qp_summary.append(dict(mode=mode,group=group,qp=qp,measured_points=len(measured),
                    imputed_excluded=len(pp)-len(measured),
                    identical_points=sum(r['identical_to_Current'] for r in measured),
                    **{k:st.mean(r[k] for r in measured) if measured else None
                       for k in ('rate_delta_pct','Y_delta_db','U_delta_db','V_delta_db')}))

    pairs = [(m,R3[0]) for m in R4] + [(R3[1],R3[0])]
    pairs += [(m,ref) for m in R3+R4 for ref in ('nopred','directional')]
    pair_rows, pair_summary, common, common_summary, identities = [], [], [], [], []
    for mode, reference in pairs:
        available = [s for s in ALL_SEQUENCES if (mode,s) in curves and (reference,s) in curves]
        rr = []
        for seq in available:
            r,t = curves[reference,seq],curves[mode,seq]
            meta = dict(mode=mode,reference=reference,sequence=seq,**{'class':CLASSES[seq]},
                imputed_points=sum(flags[mode,seq])+sum(flags[reference,seq]))
            row = dict(**meta,**compare(r,t)); rr.append(row); pair_rows.append(row)
            identities.append(dict(**meta,same_qps=';'.join(str(q) for q,a,b in zip(QPS,r,t) if a==b),
                same_count=sum(a==b for a,b in zip(r,t)),
                measured_same_count=sum(a==b and not f and not g for a,b,f,g in zip(r,t,flags[reference,seq],flags[mode,seq]))))
            if mode in R4 and reference==R3[0]:
                common.extend(dict(**meta,**row) for row in common_bands(acurves[seq],r,t))
        for group, selected in groups(rr):
            pair_summary.append(dict(mode=mode,reference=reference,group=group,sequences=len(selected),
                imputed_points=sum(r['imputed_points'] for r in selected),
                **distribution([r['weighted'] for r in selected]),
                **{c:st.mean(r[c] for r in selected) for c in 'YUV'}))
        if mode in R4 and reference==R3[0]:
            for group in ('C','E','CE'):
                for band in BANDS:
                    bb = [r for r in common if r['mode']==mode and r['class'] in group and r['band']==band]
                    common_summary.append(dict(mode=mode,reference=reference,group=group,band=band,
                        **{k:st.mean(r[k] for r in bb) for k in bb[0] if k.startswith(('parent_','test_','direct_','delta_'))},
                        direct_improved=sum(r['direct_weighted']<0 for r in bb)))

    # Missing-point sensitivity: no QP22, no placeholder, no four-point slope leakage.
    three_rows, three_summary, three_pairs = [], [], []
    for mode, *_ in specs:
        rr=[]
        for seq in ALL_SEQUENCES:
            if (mode,seq) not in curves:
                continue
            if any(flags[mode,seq][1:]):
                raise ValueError('Unexpected imputation in measured three-point curve')
            row=dict(mode=mode,sequence=seq,**{'class':CLASSES[seq]},
                     **measured_three_point(acurves[seq][1:],curves[mode,seq][1:]))
            rr.append(row); three_rows.append(row)
        for group, selected in groups(rr):
            three_summary.append(dict(mode=mode,group=group,sequences=len(selected),
                **{c:st.mean(r[c] for r in selected) for c in COMPONENTS},
                improved=sum(r['weighted']<0 for r in selected)))
    rr = [dict(sequence=s, **{'class': CLASSES[s]},
               **measured_three_point(curves[R3[0],s][1:], curves[R3[1],s][1:]))
          for s in ALL_SEQUENCES]
    for group, selected in groups(rr):
        three_pairs.append(dict(mode=R3[1],reference=R3[0],group=group,
            **{c:st.mean(r[c] for r in selected) for c in COMPONENTS},
            improved=sum(r['weighted']<0 for r in selected)))

    stress, thresholds = [], []
    for mode in R3:
        missing_seqs=[s for s in ALL_SEQUENCES if any(flags[mode,s])]
        base=next(r for r in summaries if r['mode']==mode and r['group']=='BCE')['mean']
        for target in (-.05,-.08,-.10):
            thresholds.append(dict(mode=mode,target=target,current_provisional_BCE=base,
                missing_sequences=len(missing_seqs),required_mean_BD_change_missing_pp=(12*(target-base)/len(missing_seqs)) if missing_seqs else None))
        for delta in (-1.0,-.5,-.2,-.1,0,.1,.2,.5,1.0):
            rr=[]
            for seq in ALL_SEQUENCES:
                t=[p[:] for p in curves[mode,seq]]
                if seq in missing_seqs:
                    t[0][0]*=1+delta/100
                rr.append(dict(sequence=seq,**{'class':CLASSES[seq]},**compare(acurves[seq],t)))
            for group in ('B','BCE'):
                stress.append(dict(mode=mode,group=group,missing_qp22_rate_delta_pct=delta,
                    weighted=st.mean(r['weighted'] for r in rr if r['class'] in group),
                    assumption='all missing QP22 rate shifted equally; PSNR held at Current; NOT CI/bounds'))

    decisions=[]
    for mode in R4:
        s=next(r for r in summaries if r['mode']==mode and r['group']=='CE')
        p=next(r for r in pair_summary if r['mode']==mode and r['reference']==R3[0] and r['group']=='CE')
        low=next(r for r in common_summary if r['mode']==mode and r['group']=='CE' and r['band']==BANDS[0])
        high=next(r for r in common_summary if r['mode']==mode and r['group']=='CE' and r['band']==BANDS[2])
        gates=dict(Current_mean=s['mean']<0,Current_median=s['median']<=0,
            without_PartyScene=s['without_PartyScene']<=0,direct_R3_mean=p['mean']<0,
            direct_R3_median=p['median']<=0,low_quality_not_worse=low['delta_weighted_pp']<=1e-10,
            high_quality_Current_gain=high['test_weighted']<0)
        decisions.append(dict(mode=mode,**gates,numeric_gate=all(gates.values()),
            activity_gate='unverified: remote logs/build/config/hash unavailable',
            **{f'B_required_for_BCE_{abs(t):.2f}':(12*t-7*s['mean'])/5 for t in (-.05,-.08,-.10)}))

    outputs=dict(points=raw,imputed_points=imputed,by_sequence=perseq,summary=summaries,
        quality_bands=bands,quality_band_summary=band_summary,qp_summary=qp_summary,
        leave_one_out=loo,contributions=contributions,pairwise_by_sequence=pair_rows,
        pairwise_summary=pair_summary,identical_points=identities,
        common_R3_bands=common,common_R3_band_summary=common_summary,
        measured_27_37_by_sequence=three_rows,measured_27_37_summary=three_summary,
        measured_27_37_R3_pair_summary=three_pairs,
        imputation_stress=stress,target_sensitivity=thresholds,protocol_decisions=decisions)
    args.out.mkdir(parents=True,exist_ok=True)
    for name,rows in outputs.items():
        if rows:
            write_csv(args.out/(name+'.csv'),rows)
        elif name == 'imputed_points':
            # A later complete rerun must not leave a stale imputation manifest.
            with (args.out/(name+'.csv')).open('w',newline='') as f:
                csv.writer(f).writerow(('mode','sequence','class','qp','imputed','origin','key','source'))
    for path,digest in hashes.items():
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise RuntimeError(f'Source changed during analysis: {path}')
    audit=dict(primary='Current; component-first PCHIP; (6Y+U+V)/8; CE=7, BCE=12 sequence-equal',
        source_files=sources,source_audits=audits,imputed=imputed,
        imputation_authorized=args.impute_r3_b_qp22,vba_max_difference_pp=max_vba_gap,
        source_hashes_unchanged=True,
        bootstrap='10000 equal-sequence resamples, seed 20260918; descriptive; excludes missing-point uncertainty; no multiple-testing adjustment',
        measured_three_point='separate 27/32/37-only PCHIP diagnostic, not the primary 4-point result',
        scope='LB R3-1/2 B+CE, R4-1..6 CE; previous fixed controls; auxiliary E_.xlsm excluded',
        limitations=['No remote build/config/half-frame/hash/activity verification',
                     'Rounded RD point equality is not bit-exact proof',
                     'No CG/size/selector activity/Oracle capture data',
                     'CE reused for development; R4 not an independent holdout'])
    (args.out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    for r in summaries:
        if r['group'] in ('B','CE','BCE'):
            print(f"{r['mode']:22} {r['group']:3} {r['mean']:+.6f}% median={r['median']:+.6f}% "
                  f"wins={r['improved']}/{r['sequences']} imputed={r['imputed_points']}")
    print(f'VBA maximum difference: {max_vba_gap:.3g} pp; imputed: {len(imputed)}; all source hashes unchanged')


if __name__=='__main__':
    main()
