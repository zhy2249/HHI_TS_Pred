#!/usr/bin/env python3
"""Read-only R14 LB CE analysis of registered results.

Uses complete measured curves only for full BD-rate. Relative-Current
differences are percentage points; direct pair BD-rates are separately
reintegrated with the second method as reference. QP columns retain the
ledger's target-only replacement definition and never fill a full curve.
Requires NumPy for deterministic sequence-cluster bootstrap sampling.
"""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from ts_fixed_analyze import QPS, bd_rate, workbook_bdrate


SEQUENCES = ('BasketballDrill', 'BQMall', 'PartyScene', 'RaceHorsesC',
             'FourPeople', 'Johnny', 'KristenAndSara')
GROUPS = {'C': SEQUENCES[:4], 'E': SEQUENCES[4:], 'CE': SEQUENCES}
EXPERIMENTS = tuple(f'R14-{i}' for i in range(1, 16)) + ('R13-1', 'R13-2', 'R3-1', 'R6-2')
COMPONENTS = ('y', 'u', 'v', '611')
TIE_EPSILON = 1e-10
PAIRS = (
    ('R14-10', 'R14-1'), ('R14-11', 'R14-2'),
    ('R14-12', 'R14-3'), ('R14-13', 'R14-4'),
    ('R14-14', 'R14-5'), ('R14-15', 'R14-6'),
    ('R14-4', 'R14-3'), ('R14-6', 'R14-5'),
    ('R14-11', 'R14-10'), ('R14-13', 'R14-12'), ('R14-15', 'R14-14'),
    ('R14-10', 'R13-1'), ('R14-11', 'R13-1'), ('R14-1', 'R13-1'),
    ('R14-3', 'R13-2'), ('R14-4', 'R13-2'),
    ('R14-12', 'R13-2'), ('R14-13', 'R13-2'),
    ('R14-10', 'R3-1'), ('R14-10', 'R6-2'),
    ('R14-9', 'R13-1'), ('R14-10', 'R14-9'), ('R14-10', 'R14-11'),
)
BOOTSTRAP_PAIRS = (
    ('R14-10', 'Current'), ('R14-9', 'Current'), ('R14-11', 'Current'),
    ('R14-10', 'R13-1'), ('R14-10', 'R3-1'), ('R14-10', 'R6-2'),
    ('R14-10', 'R14-9'), ('R14-10', 'R14-1'), ('R14-10', 'R14-11'),
)
INPUT_NAMES = ('sequence_bdrate.csv', 'group_summary.csv', 'qp_bdrate.csv',
               'qp_group_summary.csv', 'rd_points.csv')


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    if not rows:
        raise ValueError(f'No rows for {path}')
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def index(rows, fields):
    result = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in result:
            raise ValueError(f'Duplicate key: {key}')
        result[key] = row
    return result


def number(value):
    if value == '':
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'Non-finite value: {value}')
    return result


def mean(values):
    return float(np.mean(values)) if values else ''


def signs(values):
    return dict(win=sum(v < -TIE_EPSILON for v in values),
                tie=sum(abs(v) <= TIE_EPSILON for v in values),
                loss=sum(v > TIE_EPSILON for v in values))


def describe(values):
    return dict(n=len(values), mean=mean(values),
                median=float(np.median(values)) if values else '',
                sample_sd=float(np.std(values, ddof=1)) if len(values) > 1 else '',
                min=min(values) if values else '', max=max(values) if values else '',
                p10=float(np.percentile(values, 10)) if values else '',
                p90=float(np.percentile(values, 90)) if values else '', **signs(values))


def bootstrap(values, sequence_names, seed, resamples):
    """Paired sequence clusters; preserve each sequence's four-QP curve."""
    if len(values) < 2:
        return {}, []
    vals = np.asarray(values)
    indices = np.random.default_rng(seed).integers(0, len(vals), size=(resamples, len(vals)))
    sampled = vals[indices].mean(axis=1)
    low, high = np.percentile(sampled, (2.5, 97.5))
    loo = [float(np.delete(vals, i).mean()) for i in range(len(vals))]
    summary = dict(mean=float(vals.mean()), bootstrap_low_95=float(low),
                   bootstrap_high_95=float(high), leave_one_out_min=min(loo),
                   leave_one_out_max=max(loo), seed=seed, resamples=resamples,
                   method='paired sequence resampling; percentile; unadjusted exploratory')
    return summary, [dict(removed_sequence=s, remaining_mean=v) for s, v in zip(sequence_names, loo)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', type=Path, default=Path('docs/experiments/results'))
    parser.add_argument('--output-dir', type=Path, default=Path('runs/r14_analysis_20261024'))
    parser.add_argument('--seed', type=int, default=20261024)
    parser.add_argument('--bootstrap-samples', type=int, default=200000)
    args = parser.parse_args()
    if args.bootstrap_samples < 1:
        parser.error('--bootstrap-samples must be positive')
    if args.output_dir.resolve() == args.results_dir.resolve():
        parser.error('Output must not overwrite the registered results directory')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    inputs = {name: read_csv(args.results_dir / name) for name in INPUT_NAMES}

    def selected(rows):
        return [r for r in rows if r['configuration'] == 'LB' and r['experiment'] in EXPERIMENTS
                and ('sequence' not in r or r['sequence'] in SEQUENCES)]

    seq = index(selected(inputs['sequence_bdrate.csv']), ('experiment', 'sequence'))
    qp = index(selected(inputs['qp_bdrate.csv']), ('experiment', 'sequence', 'qp'))
    group = index(selected(inputs['group_summary.csv']), ('experiment', 'group'))
    qp_group = index(selected(inputs['qp_group_summary.csv']), ('experiment', 'group', 'qp'))
    points = index(selected(inputs['rd_points.csv']), ('experiment', 'sequence', 'qp'))

    def value(experiment, sequence, component='611'):
        row = seq[experiment, sequence]
        result = number(row[f'bd_{component}_pct'])
        if result is not None and row['status'] != 'complete':
            raise ValueError(f'Full measured curve required: {experiment}/{sequence}')
        return result

    def curve(experiment, sequence):
        rows = [points[experiment, sequence, str(q)] for q in QPS]
        return rows if all(r['status'] == 'measured' and r['test_record_status'] == 'pass'
                           and r['anchor_record_status'] == 'pass' for r in rows) else None

    # Reject mixed anchors, partial tuples, non-finite entries, and inconsistent
    # registered full/QP results before producing any interpretation.
    reference = {}
    for e in EXPERIMENTS:
        for s in SEQUENCES:
            complete = curve(e, s)
            if (value(e, s) is not None) != (complete is not None):
                raise ValueError(f'Curve completeness mismatch: {e}/{s}')
            for q in QPS:
                r = points[e, s, str(q)]
                anchor = tuple(number(r['anchor_' + c]) for c in
                               ('rate_kbps', 'psnr_y_db', 'psnr_u_db', 'psnr_v_db'))
                if None in anchor or anchor[0] <= 0 or r['anchor_record_status'] != 'pass':
                    raise ValueError(f'Invalid anchor: {e}/{s}/{q}')
                if (s, q) in reference and reference[s, q] != anchor:
                    raise ValueError(f'Mixed anchor: {e}/{s}/{q}')
                reference[s, q] = anchor
                target = tuple(number(r['test_' + c]) for c in
                               ('rate_kbps', 'psnr_y_db', 'psnr_u_db', 'psnr_v_db'))
                if r['status'] == 'measured' and (None in target or target[0] <= 0):
                    raise ValueError(f'Invalid measured target: {e}/{s}/{q}')
                if r['status'] == 'missing' and any(v is not None for v in target):
                    raise ValueError(f'Missing target has numeric values: {e}/{s}/{q}')
                qr = qp[e, s, str(q)]
                if number(qr['bd_611_pct']) is not None and (
                        qr['status'] != 'calculated' or r['status'] != 'measured'
                        or r['test_record_status'] != 'pass'):
                    raise ValueError(f'Unmeasured QP entered calculation: {e}/{s}/{q}')

    def direct(a, b, s):
        ar = curve(a, s)
        br = curve(b, s) if b != 'Current' else ar
        row = dict(experiment=a, reference=b, sequence=s, class_name='C' if s in GROUPS['C'] else 'E',
                   status='incomplete', **{f'bd_{c}_pct': '' for c in COMPONENTS})
        for c in 'yuv':
            row[f'{c}_overlap_low_db'] = row[f'{c}_overlap_high_db'] = ''
        row['max_vba_gap_pp'] = ''
        if ar is None or br is None:
            return row
        prefix = 'anchor_' if b == 'Current' else 'test_'
        gap = 0.0
        for c in 'yuv':
            ac = [(number(r[f'test_psnr_{c}_db']), number(r['test_rate_kbps'])) for r in ar]
            bc = [(number(r[f'{prefix}psnr_{c}_db']), number(r[f'{prefix}rate_kbps'])) for r in br]
            v, low, high = bd_rate(bc, ac)
            gap = max(gap, abs(v - workbook_bdrate(bc, ac)))
            row[f'bd_{c}_pct'] = v
            row[f'{c}_overlap_low_db'], row[f'{c}_overlap_high_db'] = low, high
        row['bd_611_pct'] = (6 * row['bd_y_pct'] + row['bd_u_pct'] + row['bd_v_pct']) / 8
        if gap > 1e-8:
            raise ValueError(f'PCHIP/VBA mismatch: {a}/{b}/{s}: {gap}')
        row.update(status='complete', max_vba_gap_pp=gap)
        if b == 'Current' and any(abs(row[f'bd_{c}_pct'] - value(a, s, c)) > 1e-8 for c in COMPONENTS):
            raise ValueError(f'Registered BD mismatch: {a}/{s}')
        return row

    summaries, matrices, qsummary, qsigns = [], [], [], []
    for e in EXPERIMENTS:
        vs = [value(e, s) for s in SEQUENCES]
        row = dict(experiment=e, **describe([v for v in vs if v is not None]))
        matrices.append(dict(experiment=e, **{s: v if v is not None else '' for s, v in zip(SEQUENCES, vs)}))
        for name, ss in GROUPS.items():
            for c in COMPONENTS:
                gv = number(group[e, name][f'bd_{c}_pct'])
                usable = [value(e, s, c) for s in ss if value(e, s, c) is not None]
                if (gv is not None) != bool(usable) or (usable and abs(gv - mean(usable)) > 1e-8):
                    raise ValueError(f'Group mismatch: {e}/{name}/{c}')
                row[f'{name}_{c}'] = gv if gv is not None else ''
            qr = dict(experiment=e, group=name)
            for q in QPS:
                gs = qp_group[e, name, str(q)]
                actual = [s for s in ss if number(qp[e, s, str(q)]['bd_611_pct']) is not None]
                if set(actual) != set(filter(None, gs['valid_sequence_names'].split(';'))):
                    raise ValueError(f'QP group coverage mismatch: {e}/{name}/{q}')
                for c in COMPONENTS:
                    qv = [number(qp[e, s, str(q)][f'bd_{c}_pct']) for s in actual]
                    registered = number(gs[f'bd_{c}_pct'])
                    if (registered is not None) != bool(qv) or (qv and abs(mean(qv) - registered) > 1e-8):
                        raise ValueError(f'QP group mean mismatch: {e}/{name}/{q}/{c}')
                    qr[f'qp{q}_{c}'] = registered if registered is not None else ''
                qr[f'qp{q}_n'] = len(actual)
            qsummary.append(qr)
        summaries.append(row)
        for q in QPS:
            vals = [number(qp[e, s, str(q)]['bd_611_pct']) for s in SEQUENCES]
            qsigns.append(dict(experiment=e, qp=q, **describe([v for v in vals if v is not None])))

    pair_rows = []
    for a, b in PAIRS:
        ds = {s: value(a, s) - value(b, s) for s in SEQUENCES
              if value(a, s) is not None and value(b, s) is not None}
        row = dict(a=a, b=b, n=len(ds), mean_difference_pp=mean(list(ds.values())), **signs(list(ds.values())))
        for name, ss in GROUPS.items():
            row[name] = mean([ds[s] for s in ss if s in ds])
        row.update({s: ds.get(s, '') for s in SEQUENCES})
        pair_rows.append(row)

    direct_pairs = list(dict.fromkeys([(e, 'Current') for e in EXPERIMENTS] + list(PAIRS)))
    direct_rows = [direct(a, b, s) for a, b in direct_pairs for s in SEQUENCES]
    direct_index = {(r['experiment'], r['reference'], r['sequence']): r for r in direct_rows}
    direct_summary = []
    for a, b in direct_pairs:
        for name, ss in GROUPS.items():
            rs = [direct_index[a, b, s] for s in ss if direct_index[a, b, s]['status'] == 'complete']
            row = dict(experiment=a, reference=b, group=name, expected_sequences=len(ss), valid_sequences=len(rs),
                       sequence_names=';'.join(r['sequence'] for r in rs),
                       scope_status='full' if len(rs) == len(ss) else 'subset' if rs else 'unavailable')
            row.update({f'bd_{c}_pct': mean([r[f'bd_{c}_pct'] for r in rs]) for c in COMPONENTS})
            row.update(signs([r['bd_611_pct'] for r in rs]))
            direct_summary.append(row)

    ci_rows, loo_rows = [], []
    for a, b in BOOTSTRAP_PAIRS:
        ss = [s for s in SEQUENCES if direct_index[a, b, s]['status'] == 'complete']
        for kind in ('direct_pair_bd_percent', 'relative_current_difference_pp'):
            vals = [direct_index[a, b, s]['bd_611_pct'] if kind == 'direct_pair_bd_percent'
                    else value(a, s) - (value(b, s) if b != 'Current' else 0) for s in ss]
            summary, loo = bootstrap(vals, ss, args.seed, args.bootstrap_samples)
            identity = dict(experiment=a, reference=b, metric=kind, n=len(vals))
            if summary:
                ci_rows.append({**identity, **summary})
                loo_rows.extend({**identity, **r} for r in loo)

    matched = []
    for e in ('R14-1', 'R14-10', 'R14-11', 'R13-1', 'R3-1', 'R6-2'):
        for q in QPS:
            ss = [s for s in SEQUENCES if number(qp['R14-2', s, str(q)]['bd_611_pct']) is not None
                  and number(qp[e, s, str(q)]['bd_611_pct']) is not None]
            av = [number(qp['R14-2', s, str(q)]['bd_611_pct']) for s in ss]
            bv = [number(qp[e, s, str(q)]['bd_611_pct']) for s in ss]
            matched.append(dict(experiment='R14-2', reference=e, qp=q, n=len(ss), sequences=';'.join(ss),
                                experiment_mean=mean(av), reference_mean=mean(bv),
                                difference_pp=mean([a-b for a, b in zip(av, bv)]),
                                **signs([a-b for a, b in zip(av, bv)])))

    outputs = dict(summaries=summaries, sequence_matrix=matrices, pair_differences=pair_rows,
                   direct_pair_sequences=direct_rows, direct_pair_summary=direct_summary,
                   bootstrap=ci_rows, leave_one_out=loo_rows, r14_2_matched_qp=matched,
                   qp_summary=qsummary, qp_signs=qsigns)
    for name, rows in outputs.items():
        write_csv(args.output_dir / f'numeric_{name}.csv', rows)
    metadata = dict(seed=args.seed, bootstrap_resamples=args.bootstrap_samples,
                    source_hashes={name: hashlib.sha256((args.results_dir / name).read_bytes()).hexdigest()
                                   for name in INPUT_NAMES},
                    sequence_order=SEQUENCES,
                    full_curve_policy='LB CE; all four actual measured points; no imputation',
                    qp_policy='Target QP only; remaining three points Current; common coverage comparisons',
                    difference_unit='relative-Current BD differences in percentage points, not direct BD',
                    direct_unit='Reintegrated pair BD-rate in percent; reference column defines anchor',
                    bootstrap_limit='Seven fixed CTC sequences; unstratified; not multiplicity-adjusted; exploratory content sensitivity, not repeated-run noise',
                    max_direct_vba_gap_pp=max(r['max_vba_gap_pp'] for r in direct_rows if r['status'] == 'complete'))
    (args.output_dir / 'numeric_meta.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(outputs)} CSVs and metadata to {args.output_dir}; '
          f'PCHIP/VBA maximum difference {metadata["max_direct_vba_gap_pp"]:.3g} percentage points.')


if __name__ == '__main__':
    main()
