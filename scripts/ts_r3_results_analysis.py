#!/usr/bin/env python3
"""Read-only R3 CE audit and frozen-protocol comparisons; never impute RD points.

Current is the sole primary anchor. All BD metrics integrate components first,
then weight (6Y+U+V)/8. Parent-band comparisons share a THREE-curve quality range.
Only derived CSV/JSON files are written; source workbooks are not modified.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import statistics as st

from ts_fixed_analyze import QPS, SEQUENCES, pchip_integral, self_test, sheet_values, workbook_bdrate, write_csv
from ts_fixed_workbook_analysis import CLASSES, points
from ts_predictor_cross_round_analysis import BANDS, compare, quality_bands, weighted
from ts_r2_analyze import R3_MODES

PARENTS = dict(zip(R3_MODES, ('r2_risk', 'r2_risk', 'r2_cn_log', 'r2_cn_log')))
COMPONENTS = ('Y', 'U', 'V', 'weighted')


def common_bands(anchor, parent, test):
    """Four-point PCHIPs, common outer limits, Current QP32/27 inner cuts."""
    rows = [dict(band=label) for label in BANDS]
    for i, comp in enumerate('YUV', 1):
        curves = [sorted((p[i], p[0]) for p in curve) for curve in (anchor, parent, test)]
        lo, hi = max(c[0][0] for c in curves), min(c[-1][0] for c in curves)
        cuts = (lo, anchor[2][i], anchor[1][i], hi)
        if not all(a < b for a, b in zip(cuts, cuts[1:])):
            raise ValueError(f'Insufficient common quality range: {cuts}')
        for row, low, high in zip(rows, cuts, cuts[1:]):
            areas = [pchip_integral([q for q, r in c], [math.log(r) for q, r in c], low, high)
                     for c in curves]
            for key, a, b in [('parent', 0, 1), ('test', 0, 2), ('direct', 1, 2)]:
                row[f'{key}_{comp}'] = 100 * math.expm1((areas[b] - areas[a]) / (high - low))
            row[f'delta_{comp}_pp'] = row[f'test_{comp}'] - row[f'parent_{comp}']
            row[f'{comp}_low_db'], row[f'{comp}_high_db'] = low, high
    for row in rows:
        for key in ('parent', 'test', 'direct'):
            row[key + '_weighted'] = weighted([row[f'{key}_{c}'] for c in 'YUV'])
        row['delta_weighted_pp'] = row['test_weighted'] - row['parent_weighted']
    return rows


def distribution(values):
    rng = random.Random(20260918)
    boot = sorted(st.mean(rng.choices(values, k=len(values))) for _ in range(10000))
    percentiles = st.quantiles(values, n=100, method='inclusive')
    return dict(mean=st.mean(values), median=st.median(values), stddev=st.stdev(values),
                p10=percentiles[9], p90=percentiles[89], ci95_low=boot[249], ci95_high=boot[9749],
                improved=sum(v < 0 for v in values), best=min(values), worst=max(values))


def canonical_rows(path, sheet):
    # Auxiliary E_.xlsm uses .jvet10. labels; audit, NEVER merge its Reference.
    cells = sheet_values(path, sheet)
    return {key.replace('.jvet10.', '.ecm.'): [cells.get(col + addr[1:]) for col in 'BCDE']
            for addr, key in cells.items() if addr.startswith('A') and isinstance(key, str)
            and ('.ecm.' in key or '.jvet10.' in key) and cells.get('B' + addr[1:]) is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('experiments/ts_predictor_r3'))
    parser.add_argument('--anchor', type=Path, default=Path('scripts/JVET-hhi.xlsm'))
    parser.add_argument('--out', type=Path, default=Path('runs/ts_r3_results_20260920/detail'))
    args = parser.parse_args()
    self_test()
    source_hashes, sources = {}, []

    def record(path, **meta):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        source_hashes[path] = digest
        sources.append(dict(path=str(path), sha256=digest, **meta))

    record(args.anchor, role='Current Reference')
    anchor = points(args.anchor, 'Reference')
    keys = [f'{s}.Q{q}.ecm.lb' for s in SEQUENCES for q in QPS]
    acurves = {s: [anchor[f'{s}.Q{q}.ecm.lb'][0] for q in QPS] for s in SEQUENCES}
    paths = {m: args.root / m / 'JVET-hhi.xlsm' for m in R3_MODES}
    paths.update({m: Path('experiments/ts_predictor_r2') / m / 'LB_CE/JVET-hhi.xlsm'
                  for m in dict.fromkeys(PARENTS.values())})
    paths.update({m: Path('runs/ts_fixed_LB_CE_half') / m / 'JVET-hhi.xlsm'
                  for m in ('nopred', 'directional')})
    curves, raw, results, bands, csv_audit = {}, [], [], [], []
    tests = {}
    max_vba_difference = 0.0
    for mode, path in paths.items():
        record(path, mode=mode, role='result workbook')
        if points(path, 'Reference') != anchor:
            raise ValueError(f'Non-Current Reference: {path}')
        test = points(path, 'Test')
        tests[mode] = test
        for key in keys:
            if key not in test or test[key][1] != 'pass' or anchor[key][1] != 'pass':
                raise ValueError(f'Missing/failed required point (not imputed): {mode} {key}')
        if mode in R3_MODES:
            csv_path = args.root / mode / f'R3_{R3_MODES.index(mode)+1}.csv'
            record(csv_path, mode=mode, role='RD CSV cross-check')
            csv_points = {}
            with csv_path.open(encoding='utf-8-sig') as f:
                for row in csv.reader(f):
                    if len(row) < 5 or '.ecm.' not in row[0]:
                        continue
                    if row[0] in csv_points:
                        raise ValueError(f'Duplicate CSV point: {csv_path} {row[0]}')
                    csv_points[row[0]] = list(map(float, row[1:5]))
                    if csv_points[row[0]] != test[row[0]][0] or row[9] != test[row[0]][1]:
                        raise ValueError(f'CSV/workbook mismatch: {csv_path} {row[0]}')
            if set(csv_points) != set(test):
                raise ValueError(f'CSV/workbook key mismatch: {csv_path}')
            csv_audit.append(dict(mode=mode, points=len(csv_points), equal=True))
        for seq in SEQUENCES:
            a = acurves[seq]
            t = [test[f'{seq}.Q{qp}.ecm.lb'][0] for qp in QPS]
            curves[mode, seq] = t
            meta = dict(mode=mode, sequence=seq, **{'class': CLASSES[seq]})
            r = dict(**meta, **compare(a, t), cubic=compare(a, t, 'cubic')['weighted'])
            results.append(r)
            bands.extend({**meta, **b} for b in quality_bands(a, t))
            for i, comp in enumerate('YUV', 1):
                max_vba_difference = max(max_vba_difference, abs(r[comp] - workbook_bdrate(
                    [(p[i], p[0]) for p in a], [(p[i], p[0]) for p in t])))
            for qp, aa, tt in zip(QPS, a, t):
                raw.append(dict(**meta, qp=qp, rate_delta_pct=100*(tt[0]/aa[0]-1),
                                **{f'{c}_delta_db': tt[i]-aa[i] for i, c in enumerate('YUV', 1)},
                                identical=aa == tt,
                                **dict(zip(('anchor_rate','anchor_Y','anchor_U','anchor_V'), aa)),
                                **dict(zip(('test_rate','test_Y','test_U','test_V'), tt))))
    auxiliary = []
    for path in sorted(args.root.rglob('*.xlsm')):
        if path in source_hashes:
            continue
        record(path, role='excluded auxiliary, audit only')
        ref, test = canonical_rows(path, 'Reference'), canonical_rows(path, 'Test')
        parent_test = tests.get(path.parent.name, {})
        auxiliary.append(dict(path=str(path), test_points=len(test),
            test_matches_primary=bool(test) and all(k in parent_test and v == parent_test[k][0] for k, v in test.items()),
            reference_lb_ce_equal=all(k in ref and ref[k] == anchor[k][0] for k in keys),
            reference_differences=[k for k,v in ref.items() if k not in anchor or v != anchor[k][0]],
            action='Excluded from primary computation; no Reference replacement.'))

    summaries, band_summaries, qp_summaries, loo = [], [], [], []
    for mode in paths:
        for group in ('C', 'E', 'CE'):
            rr = [r for r in results if r['mode'] == mode and r['class'] in group]
            meta = dict(mode=mode, group=group, sequences=len(rr))
            summaries.append(dict(**meta, **distribution([r['weighted'] for r in rr]),
                **{c: st.mean(r[c] for r in rr) for c in ('Y','U','V','cubic')},
                without_PartyScene=st.mean(r['weighted'] for r in rr if r['sequence'] != 'PartyScene'),
                gain_mass_pp=-sum(min(r['weighted'],0) for r in rr),
                loss_mass_pp=sum(max(r['weighted'],0) for r in rr)))
            for band in BANDS:
                bb = [r for r in bands if r['mode'] == mode and r['class'] in group and r['band'] == band]
                band_summaries.append(dict(**meta, band=band,
                    **{c: st.mean(r[c] for r in bb) for c in COMPONENTS},
                    improved=sum(r['weighted']<0 for r in bb)))
            for qp in QPS:
                pp = [r for r in raw if r['mode'] == mode and r['class'] in group and r['qp'] == qp]
                qp_summaries.append(dict(**meta, qp=qp,
                    **{k: st.mean(r[k] for r in pp) for k in ('rate_delta_pct','Y_delta_db','U_delta_db','V_delta_db')},
                    identical_points=sum(r['identical'] for r in pp)))
        ce = [r for r in results if r['mode'] == mode]
        for removed in SEQUENCES:
            loo.append(dict(mode=mode, removed=removed,
                mean_remaining=st.mean(r['weighted'] for r in ce if r['sequence'] != removed)))

    pairs = list(PARENTS.items()) + [('r3_risk_guard_y','r3_risk_guard'), ('r3_cn_guard_y','r3_cn_guard')]
    pairs += [(m,f) for m in R3_MODES for f in ('nopred','directional')]
    pair_rows, pair_summary, identities = [], [], []
    for mode, reference in pairs:
        rr = [dict(mode=mode, reference=reference, sequence=seq, **{'class':CLASSES[seq]},
                   **compare(curves[reference,seq],curves[mode,seq])) for seq in SEQUENCES]
        pair_rows.extend(rr)
        for group in ('C','E','CE'):
            group_rows = [r for r in rr if r['class'] in group]
            pair_summary.append(dict(mode=mode, reference=reference, group=group,
                **distribution([r['weighted'] for r in group_rows]),
                **{c:st.mean(r[c] for r in group_rows) for c in 'YUV'}))
    for m1, m2 in [('r3_risk_guard','r3_risk_guard_y'), ('r3_cn_guard','r3_cn_guard_y')]:
        for seq in SEQUENCES:
            identities.append(dict(mode=m1, other=m2, sequence=seq,
                same_qps=';'.join(str(qp) for qp, a, b in zip(QPS, curves[m1,seq],curves[m2,seq]) if a == b),
                same_count=sum(a == b for a,b in zip(curves[m1,seq],curves[m2,seq]))))

    common, common_summary = [], []
    for mode, parent in PARENTS.items():
        for seq in SEQUENCES:
            common.extend(dict(mode=mode, parent=parent, sequence=seq, **{'class': CLASSES[seq]}, **r)
                for r in common_bands(acurves[seq],curves[parent,seq],curves[mode,seq]))
        for group in ('C','E','CE'):
            for band in BANDS:
                rr = [r for r in common if r['mode']==mode and r['class'] in group and r['band']==band]
                common_summary.append(dict(mode=mode,parent=parent,group=group,band=band,
                    **{key:st.mean(r[key] for r in rr) for key in rr[0] if key.startswith(('parent_','test_','direct_','delta_'))},
                    direct_improved=sum(r['direct_weighted']<0 for r in rr)))
    decisions = []
    for mode in R3_MODES:
        s = next(r for r in summaries if r['mode']==mode and r['group']=='CE')
        low = next(r for r in common_summary if r['mode']==mode and r['group']=='CE' and r['band']==BANDS[0])
        high = next(r for r in common_summary if r['mode']==mode and r['group']=='CE' and r['band']==BANDS[2])
        decisions.append(dict(mode=mode, numeric_gate=s['mean']<0 and s['median']<=0 and
            s['without_PartyScene']<=0 and low['delta_weighted_pp']<0 and high['test_weighted']<0,
            high_quality_retention=high['test_weighted']/high['parent_weighted'] if high['parent_weighted']<0 else None,
            low_quality_change_pp=low['delta_weighted_pp'], activity_gate='not auditable without remote logs',
            **{f'B_required_for_BCE_{abs(t):.2f}': (12*t-7*s['mean'])/5 for t in (-.05,-.08,-.10)}))
    args.out.mkdir(parents=True,exist_ok=True)
    outputs = dict(points=raw, by_sequence=results, summary=summaries, quality_bands=bands,
        quality_band_summary=band_summaries, qp_summary=qp_summaries, leave_one_out=loo,
        pairwise_by_sequence=pair_rows, pairwise_summary=pair_summary, identical_points=identities,
        common_parent_bands=common, common_parent_band_summary=common_summary, protocol_decisions=decisions)
    for name,rows in outputs.items():
        write_csv(args.out/(name+'.csv'),rows)
    for path,digest in source_hashes.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest, path
    audit=dict(primary='Current; component-first PCHIP BD-rate, 6:1:1; CE seven sequences equal weight',
        R3_measured_points=len(keys)*len(R3_MODES), imputed_points=0, sources=sources, csv_audit=csv_audit, auxiliary=auxiliary,
        vba_max_difference_pp=max_vba_difference, bootstrap='10000 equal-sequence resamples, seed 20260918; descriptive only',
        no_remote_build_config_frame_hash_verification=True, no_CG_activity_or_size_data=True)
    (args.out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    for r in summaries:
        if r['group']=='CE':
            print(f"{r['mode']:18} CE={r['mean']:+.6f}% median={r['median']:+.6f}% "
                  f"wins={r['improved']}/7 withoutParty={r['without_PartyScene']:+.6f}%")
    print(json.dumps(decisions,indent=2))


if __name__=='__main__':
    main()
