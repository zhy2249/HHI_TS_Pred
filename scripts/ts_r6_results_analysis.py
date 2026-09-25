#!/usr/bin/env python3
"""Audit received R6 LB CE workbooks, without editing inputs or imputing points.

Current is the sole anchor; R3-1 is an incremental comparator. Component-first
PCHIP BD-rate, (6Y+U+V)/8, equal sequence weights. No external dependencies.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics as st

from ts_fixed_analyze import ALL_SEQUENCES, QPS, SEQUENCES, self_test, sheet_values, workbook_bdrate, write_csv
from ts_fixed_workbook_analysis import CLASSES, points
from ts_predictor_cross_round_analysis import BANDS, compare
from ts_r3_results_analysis import common_bands, distribution

MODES = ('dense_nopred', 'reject_nopred', 'trim_cost', 'trim_saving',
         'sparse_max', 'sparse_mean', 'sparse_min')
COMPONENTS = ('Y', 'U', 'V', 'weighted')


def required_points(data, sequences):
    keys = {f'{s}.Q{q}.ecm.lb' for s in sequences for q in QPS}
    for key in keys:
        if key not in data:
            raise ValueError(f'Missing point, imputation forbidden: {key}')
        values, status = data[key]
        if status != 'pass' or len(values) != 4 or values[0] <= 0 or not all(map(math.isfinite, values)):
            raise ValueError(f'Invalid/failed point: {key}')
    return keys


def csv_columns(path):
    """Read complete B:J including timings/memory, not timestamps in K."""
    result, seen = {}, set()
    with path.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.reader(f):
            if not row or '.ecm.' not in row[0]:
                continue
            key = row[0]
            if key in seen:
                raise ValueError(f'Duplicate CSV key: {path} {key}')
            seen.add(key)
            if not any(v.strip() for v in row[1:]):
                continue
            if len(row) < 10 or row[9].strip() != 'pass':
                raise ValueError(f'Partial/failed CSV row: {path} {key}')
            values = list(map(float, row[1:9]))
            if not all(map(math.isfinite, values)) or values[0] <= 0:
                raise ValueError(f'Invalid CSV values: {path} {key}')
            result[key] = values + [row[9].strip()]
    return result


def check_columns(workbook, csv_paths, keys):
    cells = sheet_values(workbook, 'Test')
    wb = {key: [cells.get(col + address[1:]) for col in 'BCDEFGHIJ']
          for address, key in cells.items() if address.startswith('A') and isinstance(key, str) and key in keys}
    combined = {}
    for path in csv_paths:
        rows = csv_columns(path)
        if combined.keys() & rows.keys():
            raise ValueError(f'Overlapping CSV points: {path}')
        combined.update(rows)
    if set(combined) != keys or combined != wb:
        raise ValueError(f'CSV/workbook B:J or scope mismatch: {workbook}')


def summarize(rows):
    """One row per sequence; never average class means or RD points."""
    if len({r['sequence'] for r in rows}) != len(rows):
        raise ValueError('Duplicate sequence in aggregate')
    return dict(sequences=len(rows), **distribution([r['weighted'] for r in rows]),
                **{c: st.mean(r[c] for r in rows) for c in 'YUV'},
                without_PartyScene=st.mean(r['weighted'] for r in rows if r['sequence'] != 'PartyScene'),
                without_KristenAndSara=st.mean(r['weighted'] for r in rows if r['sequence'] != 'KristenAndSara'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('experiments/ts_predictor_r6'))
    p.add_argument('--parent', type=Path, default=Path('experiments/ts_predictor_r3/r3_risk_guard'))
    p.add_argument('--anchor', type=Path, default=Path('scripts/JVET-hhi.xlsm'))
    p.add_argument('--out', type=Path, default=Path('runs/ts_r6_results_20260924'))
    args = p.parse_args()
    # Derived output must not overwrite the input collection.
    if any(args.out.resolve().is_relative_to(x.resolve()) for x in (args.root, args.parent)):
        p.error('--out must be outside the input result directories')
    self_test()
    hashes, audits = {}, []

    def record(path):
        hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()

    record(args.anchor)
    anchor = points(args.anchor, 'Reference')
    required_points(anchor, ALL_SEQUENCES)
    curves = {('Current', s): [anchor[f'{s}.Q{q}.ecm.lb'][0] for q in QPS] for s in ALL_SEQUENCES}
    specifications = [('R3_1', args.parent / 'JVET-hhi.xlsm',
                       [args.parent / 'R3_1.csv', args.parent / 'R3_1_B.csv'], ALL_SEQUENCES)]
    specifications += [(f'R6_{i}', args.root / f'R6_{i}_JVET-hhi.xlsm',
                         [args.root / f'R6_{i}.csv'], SEQUENCES) for i in range(1, 8)]
    raw, results, summaries, bands, band_summary, component_stats, jackknife = [], [], [], [], [], [], []
    max_vba_gap = 0.0
    for mode, path, csv_paths, sequences in specifications:
        for source in (path, *csv_paths):
            record(source)
        if points(path, 'Reference') != anchor:
            raise ValueError(f'Non-Current Reference: {path}')
        test = points(path, 'Test')
        keys = required_points(test, sequences)
        extra_lb = {k for k in test if k.endswith('.lb')} - keys
        if extra_lb or (mode.startswith('R6') and set(test) != keys):
            raise ValueError(f'Unexpected result scope: {path}')
        check_columns(path, csv_paths, keys)
        audits.append(dict(mode=mode, measured_lb_points=len(keys), imputed=0,
                           csv_B_to_J_equal=True, Current_reference_equal=True,
                           excluded_other_config_points=len(set(test)-keys)))
        for seq in sequences:
            t = curves[mode, seq] = [test[f'{seq}.Q{q}.ecm.lb'][0] for q in QPS]
            for reference in (('Current',) if mode == 'R3_1' else ('Current', 'R3_1')):
                a = curves[reference, seq]
                meta = dict(mode=mode, reference=reference, sequence=seq, **{'class': CLASSES[seq]})
                result = dict(**meta, **compare(a, t))
                results.append(result)
                for i, c in enumerate('YUV', 1):
                    vba = workbook_bdrate([(x[i], x[0]) for x in a], [(x[i], x[0]) for x in t])
                    max_vba_gap = max(max_vba_gap, abs(result[c] - vba))
                for q, aa, tt in zip(QPS, a, t):
                    raw.append(dict(**meta, qp=q, rate_delta_pct=100*(tt[0]/aa[0]-1),
                                    **{f'{c}_delta_db': tt[i]-aa[i] for i, c in enumerate('YUV', 1)},
                                    identical_at_table_precision=aa == tt,
                                    **dict(zip(('reference_rate','reference_Y','reference_U','reference_V'), aa)),
                                    **dict(zip(('test_rate','test_Y','test_U','test_V'), tt))))
            if mode.startswith('R6'):
                bands.extend(dict(mode=mode, sequence=seq, **{'class': CLASSES[seq]}, **r)
                             for r in common_bands(curves['Current', seq], curves['R3_1', seq], t))
    for mode, _, _, sequences in specifications:
        for reference in (('Current',) if mode == 'R3_1' else ('Current', 'R3_1')):
            for group in (('B','C','E','CE','BCE') if mode == 'R3_1' else ('C','E','CE')):
                rr = [r for r in results if r['mode']==mode and r['reference']==reference and r['class'] in group]
                summaries.append(dict(mode=mode, reference=reference, group=group, **summarize(rr)))
            rr = [r for r in results if r['mode']==mode and r['reference']==reference and r['sequence'] in SEQUENCES]
            for c in COMPONENTS:
                component_stats.append(dict(mode=mode, reference=reference, group='CE', component=c,
                                            **distribution([r[c] for r in rr])))
            for removed in SEQUENCES:
                jackknife.append(dict(mode=mode, reference=reference, removed=removed,
                                      mean_remaining=st.mean(r['weighted'] for r in rr if r['sequence']!=removed)))
        if mode.startswith('R6'):
            for group in ('C', 'E', 'CE'):
                for band in BANDS:
                    rr = [r for r in bands if r['mode']==mode and r['class'] in group and r['band']==band]
                    band_summary.append(dict(mode=mode, group=group, band=band,
                        **{f'{prefix}_{c}': st.mean(r[f'{prefix}_{c}'] for r in rr)
                           for prefix in ('parent','test','direct') for c in COMPONENTS},
                        direct_improved=sum(r['direct_weighted'] < 0 for r in rr),
                        direct_Y_improved=sum(r['direct_Y'] < 0 for r in rr)))
    pair_rows, pair_summary, identities = [], [], []
    for mode, reference in [('R6_1','R6_2'), ('R6_3','R6_4'), ('R6_6','R6_5'), ('R6_7','R6_5')]:
        rr = [dict(mode=mode, reference=reference, sequence=s, **{'class':CLASSES[s]},
                   **compare(curves[reference,s], curves[mode,s])) for s in SEQUENCES]
        pair_rows.extend(rr)
        pair_summary.append(dict(mode=mode, reference=reference, **summarize(rr)))
        for s in SEQUENCES:
            same = [q for q, a, b in zip(QPS,curves[reference,s],curves[mode,s]) if a==b]
            identities.append(dict(mode=mode, reference=reference, sequence=s,
                                   same_qps=';'.join(map(str,same)), same_count=len(same)))
    decisions = []
    for i in range(1, 8):
        mode = f'R6_{i}'
        d = next(r for r in summaries if r['mode']==mode and r['reference']=='R3_1' and r['group']=='CE')
        a = next(r for r in summaries if r['mode']==mode and r['reference']=='Current' and r['group']=='CE')
        low = next(r for r in band_summary if r['mode']==mode and r['group']=='CE' and r['band']==BANDS[0])
        core = a['mean']<0 and d['mean']<0 and d['median']<=0 and d['without_PartyScene']<=0
        decisions.append(dict(mode=mode, name=MODES[i-1], anchor_mean_pass=a['mean']<0,
                              direct_mean_pass=d['mean']<0, direct_median_pass=d['median']<=0,
                              without_Party_pass=d['without_PartyScene']<=0,
                              necessary_numeric_gate=core, low_quality_direct_mean=low['direct_weighted'],
                              remote_identity_activity='unverified; no run logs supplied',
                              expand_B=False if not core else 'pending quality/activity review'))
    qp_summary = []
    for mode, _, _, _ in specifications:
        for reference in (('Current',) if mode=='R3_1' else ('Current','R3_1')):
            for q in QPS:
                rr = [r for r in raw if r['mode']==mode and r['reference']==reference
                      and r['sequence'] in SEQUENCES and r['qp']==q]
                qp_summary.append(dict(mode=mode, reference=reference, group='CE', qp=q,
                    **{k:st.mean(r[k] for r in rr) for k in ('rate_delta_pct','Y_delta_db','U_delta_db','V_delta_db')},
                    identical_points=sum(r['identical_at_table_precision'] for r in rr)))
    outputs = dict(by_sequence=results, summary=summaries, component_distribution=component_stats,
                   points=raw, common_quality_bands=bands, common_quality_band_summary=band_summary,
                   qp_summary=qp_summary,
                   leave_one_out=jackknife, pairwise_by_sequence=pair_rows, pairwise_summary=pair_summary,
                   identical_points=identities, protocol_decisions=decisions)
    # Fail before publishing outputs if an open spreadsheet changed during the audit.
    for path, digest in hashes.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Input changed during analysis: {path}')
    audit = dict(method='PCHIP; component BD first, (6Y+U+V)/8; equal sequences',
                 Current_anchor=str(args.anchor), incremental_reference='R3_1',
                 scope='R6 LB CE only; R3_1 LB BCE completeness update; no imputation',
                 bootstrap='10000 paired sequence resamples, seed 20260918; descriptive, CE repeatedly reused',
                 max_difference_from_workbook_VBA_translation_pp=max_vba_gap,
                 remote_build_config_frames_hash_activity_verified=False,
                 limitations=['No R6 B/RA data', 'No R6 logs or actual run metadata',
                              'No TU size/support counters available', 'Table identity is not bit-exact identity'],
                 ignored_lock_files=[str(x) for x in args.root.glob('~$*')],
                 sources=[dict(path=str(path), sha256=d) for path,d in hashes.items()],
                 checks=audits, sources_unchanged=True)
    if max_vba_gap > 1e-8:
        raise ValueError(f'Workbook formula cross-check failed: {max_vba_gap}')
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in outputs.items():
        write_csv(args.out / (name+'.csv'), rows)
    (args.out / 'audit.json').write_text(json.dumps(audit, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    for r in summaries:
        if r['group'] in ('CE','BCE'):
            print(f"{r['mode']:5} vs {r['reference']:7} {r['group']:3}: {r['mean']:+.9f}%")
    print(f'Read-only audit complete: {args.out}; formula maximum gap={max_vba_gap:.3g} pp')


if __name__ == '__main__':
    main()
