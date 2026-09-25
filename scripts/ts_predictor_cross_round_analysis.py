#!/usr/bin/env python3
"""Read-only cross-round RD analysis; Current is always the primary anchor.

Output files are new derived data only. Previously authorized missing QP22
substitution is explicit; no other missing point is filled. Quality bands are
integrals of the original four-point PCHIP, not two-point fits or QP policies.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics as st

from ts_fixed_analyze import QPS, SEQUENCES, bd_rate, pchip_integral, self_test, write_csv
from ts_fixed_workbook_analysis import CLASSES, points

FIXED = ('nopred', 'gradient', 'directional')
V1 = ('q32', 'conf2', 'prev', 'ewma', 'q32_ewma')
R2 = ('r2_modal', 'r2_risk', 'r2_cn_log', 'r2_cn_frac')
BANDS = ('QP32-37', 'QP27-32', 'QP22-27')


def weighted(values):
    return (6 * values[0] + values[1] + values[2]) / 8


def compare(a, b, method='pchip'):
    values = [bd_rate([(p[i], p[0]) for p in a],
                      [(p[i], p[0]) for p in b], method)[0] for i in range(1, 4)]
    return dict(zip(('Y', 'U', 'V', 'weighted'), (*values, weighted(values))))


def quality_bands(a, b):
    rows = [dict(band=label) for label in BANDS]
    expected = compare(a, b)
    for i, c in enumerate('YUV', 1):
        ac, tc = sorted((p[i], p[0]) for p in a), sorted((p[i], p[0]) for p in b)
        lo, hi = max(ac[0][0], tc[0][0]), min(ac[-1][0], tc[-1][0])
        cuts = (lo, a[2][i], a[1][i], hi)
        assert all(x < y for x, y in zip(cuts, cuts[1:])), cuts
        total_area = 0.0
        for row, low, high in zip(rows, cuts, cuts[1:]):
            def integrate(curve):
                return pchip_integral([q for q, r in curve],
                                      [math.log(r) for q, r in curve], low, high)
            area = integrate(tc) - integrate(ac)
            row[c] = 100 * math.expm1(area / (high - low))
            row[c + '_low_db'], row[c + '_high_db'] = low, high
            row[c + '_log_area'] = area
            total_area += area
        assert abs(100 * math.expm1(total_area / (hi - lo)) - expected[c]) < 1e-9
    for row in rows:
        row['weighted'] = weighted([row[c] for c in 'YUV'])
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--anchor', type=Path, default=Path('scripts/JVET-hhi.xlsm'))
    parser.add_argument('--out', type=Path, default=Path('runs/ts_cross_round_20260919'))
    args = parser.parse_args()
    self_test()
    anchor = points(args.anchor, 'Reference')
    sources = []
    curves, raw, missing, results, bands = {}, [], [], [], []
    for mode in (*FIXED, *V1, *R2):
        if mode in FIXED:
            path = Path('runs/ts_fixed_LB_CE_half') / mode / 'JVET-hhi.xlsm'
            groups = [('lb', 'CE' if mode == 'gradient' else 'BCE'), ('ra', 'CD')]
        else:
            root, phase = ('ts_conditional_v1', 'LB_BCE') if mode in V1 else ('ts_predictor_r2', 'LB_CE')
            path = Path('experiments') / root / mode / phase / 'JVET-hhi.xlsm'
            groups = [('lb', 'CE')]
        assert points(path, 'Reference') == anchor, (mode, 'Reference mismatch')
        test = points(path, 'Test')
        sources.append(dict(mode=mode, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for config, classes in groups:
            for seq, cls in CLASSES.items():
                if cls not in classes:
                    continue
                aa, tt, origins = [], [], []
                for qp in QPS:
                    key = f'{seq}.Q{qp}.ecm.{config}'
                    a, status = anchor[key]
                    assert status == 'pass'
                    if key in test:
                        t, status = test[key]
                        assert status == 'pass', (mode, key)
                        origin = 'measured'
                    elif qp == 22 and mode not in FIXED:
                        t, origin = a, 'anchor_imputed_QP22'
                    else:
                        t, origin = None, 'missing_not_imputed'
                    meta = dict(mode=mode, config=config, sequence=seq, **{'class': cls}, qp=qp, origin=origin)
                    if origin != 'measured':
                        missing.append(meta.copy())
                    row = {**meta, **dict(zip(('anchor_rate', 'anchor_Y', 'anchor_U', 'anchor_V'), a))}
                    if t is not None:
                        row.update(zip(('test_rate', 'test_Y', 'test_U', 'test_V'), t))
                        row['rate_delta_pct'] = 100 * (t[0] / a[0] - 1)
                        row.update({c + '_delta_db': t[i] - a[i] for i, c in enumerate('YUV', 1)})
                        if t == a:
                            row['dominance'] = 'identical_table_values'
                        elif t[0] <= a[0] and all(t[i] >= a[i] for i in range(1, 4)):
                            row['dominance'] = 'test_dominates_all_YUV'
                        elif t[0] >= a[0] and all(t[i] <= a[i] for i in range(1, 4)):
                            row['dominance'] = 'anchor_dominates_all_YUV'
                        else:
                            row['dominance'] = 'tradeoff'
                    raw.append(row)
                    aa.append(a); tt.append(t); origins.append(origin)
                if any(t is None for t in tt):
                    continue
                provenance = 'fully_measured' if all(o == 'measured' for o in origins) else 'includes_anchor_QP22'
                meta = dict(mode=mode, config=config, sequence=seq, **{'class': cls}, provenance=provenance)
                curves[mode, config, seq] = (tt, provenance)
                result = {**meta, **compare(aa, tt)}
                result['weighted_cubic'] = compare(aa, tt, 'cubic')['weighted']
                results.append(result)
                bands.extend({**meta, **b} for b in quality_bands(aa, tt))

    summaries, band_summaries, qp_summaries = [], [], []
    for mode in (*FIXED, *V1, *R2):
        for config, groups in [('lb', ('B', 'C', 'E', 'CE', 'BCE')), ('ra', ('C', 'D', 'CD'))]:
            for group in groups:
                rr = [r for r in results if r['mode'] == mode and r['config'] == config and r['class'] in group]
                if {r['class'] for r in rr} != set(group):
                    continue
                vals = [r['weighted'] for r in rr]
                meta = dict(mode=mode, config=config, group=group, sequences=len(rr),
                            filled_curves=sum(r['provenance'] != 'fully_measured' for r in rr))
                summary = {**meta, **{c: st.mean(r[c] for r in rr) for c in ('Y', 'U', 'V', 'weighted')},
                           'median': st.median(vals), 'stdev': st.stdev(vals),
                           'wins': sum(v < 0 for v in vals), 'wins_gt_005': sum(v < -.05 for v in vals),
                           'losses_gt_005': sum(v > .05 for v in vals),
                           'gain_mass_pp': -sum(min(v, 0) for v in vals),
                           'loss_mass_pp': sum(max(v, 0) for v in vals),
                           'best': min(vals), 'worst': max(vals),
                           'without_best': (sum(vals) - min(vals)) / (len(vals) - 1),
                           'weighted_cubic': st.mean(r['weighted_cubic'] for r in rr)}
                for seq in ('PartyScene', 'BQMall', 'KristenAndSara', 'Cactus', 'BQSquare'):
                    rem = [r['weighted'] for r in rr if r['sequence'] != seq]
                    summary['without_' + seq] = st.mean(rem) if len(rem) < len(rr) else ''
                summaries.append(summary)
                for band in BANDS:
                    bb = [r for r in bands if r['mode'] == mode and r['config'] == config
                          and r['class'] in group and r['band'] == band]
                    band_summaries.append({**meta, 'band': band,
                        **{c: st.mean(r[c] for r in bb) for c in ('Y', 'U', 'V', 'weighted')},
                        'wins': sum(r['weighted'] < 0 for r in bb)})
                for qp in QPS:
                    pp = [r for r in raw if r['mode'] == mode and r['config'] == config
                          and r['class'] in group and r['qp'] == qp and r['origin'] == 'measured']
                    if not pp:
                        continue
                    qp_summaries.append(dict(mode=mode, config=config, group=group, qp=qp, measured=len(pp),
                        **{k: st.mean(r[k] for r in pp) for k in ('rate_delta_pct', 'Y_delta_db', 'U_delta_db', 'V_delta_db')},
                        **{key: sum(r['dominance'] == key for r in pp) for key in (
                            'identical_table_values', 'test_dominates_all_YUV', 'anchor_dominates_all_YUV', 'tradeoff')}))

    # Directly reintegrated pairwise curves; no primary anchor change, no BD subtraction.
    pairs = [('nopred', 'r2_cn_log'), ('nopred', 'r2_cn_frac'), ('nopred', 'r2_risk'),
             ('directional', 'r2_risk'), ('r2_modal', 'r2_risk'), ('r2_cn_log', 'r2_cn_frac'),
             ('ewma', 'r2_cn_log'), ('directional', 'prev'), ('directional', 'q32'),
             ('directional', 'conf2')]
    pair_rows, pair_summary = [], []
    for reference, mode in pairs:
        rows = []
        for seq in SEQUENCES:
            if (reference, 'lb', seq) not in curves or (mode, 'lb', seq) not in curves:
                continue
            a, pa = curves[reference, 'lb', seq]
            b, pb = curves[mode, 'lb', seq]
            row = dict(reference=reference, mode=mode, sequence=seq,
                       provenance='fully_measured' if pa == pb == 'fully_measured' else 'includes_anchor_QP22',
                       **compare(a, b))
            rows.append(row)
        pair_rows.extend(rows)
        for subset in ('available', 'paired_fully_measured'):
            rr = [r for r in rows if subset == 'available' or r['provenance'] == 'fully_measured']
            if rr:
                pair_summary.append(dict(reference=reference, mode=mode, subset=subset, sequences=len(rr),
                    included_sequences=';'.join(r['sequence'] for r in rr), wins=sum(r['weighted'] < 0 for r in rr),
                    **{c: st.mean(r[c] for r in rr) for c in ('Y', 'U', 'V', 'weighted')}))

    args.out.mkdir(parents=True, exist_ok=True)
    outputs = dict(points=raw, missing=missing, by_sequence=results, summary=summaries,
                   quality_bands=bands, quality_band_summary=band_summaries,
                   qp_summary=qp_summaries, pairwise_by_sequence=pair_rows, pairwise_summary=pair_summary)
    for name, rows in outputs.items():
        # Some missing points have no RD keys; write_csv takes fieldnames from row 0.
        fields = list(dict.fromkeys(k for r in rows for k in r))
        write_csv(args.out / (name + '.csv'), [{k: r.get(k, '') for k in fields} for r in rows])
    audit = dict(sources=sources, anchor_sha256=hashlib.sha256(args.anchor.read_bytes()).hexdigest(),
                 measured_points=sum(r['origin'] == 'measured' for r in raw),
                 filled_points=sum(r['origin'] == 'anchor_imputed_QP22' for r in raw),
                 missing_points=sum(r['origin'] == 'missing_not_imputed' for r in raw),
                 calculated_curves=len(results), filled_curves=sum(r['provenance'] != 'fully_measured' for r in results),
                 primary='Current; component BD first, (6Y+U+V)/8; sequence equal weighting',
                 limitations=['Read-only workbook numerical audit, not external executable/frame/config identity.',
                              'Missing QP22 = Current is temporary and neither conservative nor a bound.',
                              'Bands integrate original PCHIP on component-specific anchor quality intervals; not nominal-QP tool results.',
                              'Pairwise comparisons use their own overlapping ranges, and are auxiliary.',
                              'No TS usage, TU-size or CG-state inference from RD tables.',
                              'Cross-round repeated sequences are not independent replications.'])
    # Ensure analysis has not changed any source workbook.
    for source in sources:
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == source['sha256']
    (args.out / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    for row in summaries:
        if row['config'] == 'lb' and row['group'] == 'CE':
            leave_party = row['without_PartyScene']
            leave_party_text = f'{leave_party:+.6f}%' if leave_party != '' else 'already excluded'
            print(f"{row['mode']:14} n={row['sequences']} filled={row['filled_curves']} "
                  f"CE={row['weighted']:+.6f}% median={row['median']:+.6f}% "
                  f"wins={row['wins']} withoutParty={leave_party_text}")


if __name__ == '__main__':
    main()
