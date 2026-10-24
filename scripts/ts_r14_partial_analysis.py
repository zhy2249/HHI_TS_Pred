#!/usr/bin/env python3
"""Audit partial R14 CSVs without filling QP22 or claiming four-point CTC BD-rate.

All reported equality is equality of the printed RD tuple, NOT bitstream equality.
Mode 2 is retained in the source audit and excluded from every effect comparison.
Three-point diagnostics use only measured 27/32/37 and weight component BD-rates.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from ts_fixed_analyze import SEQUENCES, pchip_integral

MODE_NAMES = {
    1: 'g2_none_equal', 2: 'g4_none_equal', 3: 'g2_none_half', 4: 'g4_none_half',
    5: 'g2_none_zero', 6: 'g4_none_zero', 7: 'fixed_near_only',
    8: 'fixed_quarter', 9: 'fixed_threequarter', 10: 'g2_pair2_equal',
    11: 'g4_pair2_equal', 12: 'g2_pair2_half', 13: 'g4_pair2_half',
    14: 'g2_pair2_zero', 15: 'g4_pair2_zero',
}
INITIAL = {1: 'R13-1', 3: 'R13-2', 4: 'R13-2', 5: 'R14-7', 6: 'R14-7',
           10: 'R13-1', 11: 'R13-1', 12: 'R13-2', 13: 'R13-2',
           14: 'R14-7', 15: 'R14-7'}
KEY = re.compile(r'^(.+)\.Q(\d+)\.ecm\.(\w+)$')
DIAG_QPS = (27, 32, 37)


def read_results(path):
    points, issues, sources = {}, [], {}
    with path.open(newline='', encoding='utf-8-sig') as stream:
        for line, row in enumerate(csv.reader(stream), 1):
            if not row or not KEY.fullmatch(row[0].strip()):
                continue
            match = KEY.fullmatch(row[0].strip())
            sequence, qp, config = match.group(1), int(match.group(2)), match.group(3)
            if not any(s.strip() for s in row[1:5]):
                continue
            key = (sequence, qp)
            if sequence not in SEQUENCES or qp not in (22, 27, 32, 37) or config != 'lb':
                issues.append(f'line {line}: unexpected sequence/QP/config {row[0]}')
                continue
            if key in sources:
                issues.append(f'line {line}: duplicate numeric key {key}')
                continue
            sources[key] = line
            try:
                rd = tuple(float(s) for s in row[1:5])
                if len(rd) != 4 or not all(math.isfinite(x) for x in rd) or rd[0] <= 0:
                    raise ValueError('invalid RD value')
                if len(row) < 10 or row[9].strip().lower() != 'pass':
                    raise ValueError('record status is not pass')
            except ValueError as error:
                issues.append(f'line {line}: {error}')
                continue
            points[key] = rd
    return points, issues, sources


def read_controls(path):
    controls = {'Current': {}, 'R13-1': {}, 'R13-2': {}}
    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['round'] != 'r13' or row['configuration'] != 'LB':
                continue
            if row['sequence'] not in SEQUENCES or row['status'] != 'measured':
                continue
            key = row['sequence'], int(row['qp'])
            anchor = tuple(float(row[f'anchor_{column}']) for column in
                           ('rate_kbps', 'psnr_y_db', 'psnr_u_db', 'psnr_v_db'))
            if key in controls['Current'] and controls['Current'][key] != anchor:
                raise ValueError(f'Conflicting Current points: {key}')
            controls['Current'][key] = anchor
            controls[row['experiment']][key] = tuple(float(row[f'test_{column}']) for column in
                                                    ('rate_kbps', 'psnr_y_db', 'psnr_u_db', 'psnr_v_db'))
    for name, curve in controls.items():
        if len(curve) != 28:
            raise ValueError(f'Expected complete LB CE control {name}: {len(curve)} points')
    return controls


def bd3(anchor, test):
    """Diagnostic only: exactly three observed QPs per component, no extrapolation."""
    if set(anchor) != set(DIAG_QPS) or set(test) != set(DIAG_QPS):
        raise ValueError('Three-point diagnostic requires measured QP27/32/37')
    result = []
    for component in (1, 2, 3):
        curves = [sorted((rd[component], rd[0]) for rd in points.values())
                  for points in (anchor, test)]
        for curve in curves:
            if not all(math.isfinite(q + r) and r > 0 for q, r in curve):
                raise ValueError('Nonfinite/invalid curve')
            if not all(q < qq and r < rr for (q, r), (qq, rr) in zip(curve, curve[1:])):
                raise ValueError('Nonmonotonic curve')
        lo = max(curve[0][0] for curve in curves)
        hi = min(curve[-1][0] for curve in curves)
        if hi <= lo:
            raise ValueError('No overlapping quality range')
        areas = [pchip_integral([q for q, _ in curve], [math.log(r) for _, r in curve], lo, hi)
                 for curve in curves]
        result.append(100 * math.expm1((areas[1] - areas[0]) / (hi - lo)))
    return (*result, (6 * result[0] + result[1] + result[2]) / 8)


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def compare(test, reference, test_name, reference_name, relation):
    rows = []
    for sequence, qp in sorted(set(test) & set(reference)):
        a, b = reference[sequence, qp], test[sequence, qp]
        rows.append(dict(test=test_name, reference=reference_name, relation=relation,
                         sequence=sequence, class_name=SEQUENCES[sequence][0], qp=qp,
                         rd_tuple_equal=int(a == b), rate_change_pct=100*(b[0]/a[0]-1),
                         rate_change_kbps=b[0]-a[0], y_change_db=b[1]-a[1],
                         u_change_db=b[2]-a[2], v_change_db=b[3]-a[3]))
    return rows


def summarize(rows, dimension='all'):
    groups = {}
    for row in rows:
        key = row['test'], row['reference'], row['relation'], str(row.get(dimension, 'all'))
        groups.setdefault(key, []).append(row)
    out = []
    for (test, reference, relation, group), points in sorted(groups.items()):
        result = dict(test=test, reference=reference, relation=relation, dimension=dimension,
                      group=group, common_points=len(points),
                      rd_tuple_equal=sum(p['rd_tuple_equal'] for p in points))
        result['rd_tuple_equal_pct'] = 100*result['rd_tuple_equal']/len(points)
        for field in ('rate_change_pct', 'y_change_db', 'u_change_db', 'v_change_db'):
            values = [p[field] for p in points]
            result[f'{field}_mean'] = statistics.mean(values)
            result[f'{field}_median'] = statistics.median(values)
            result[f'{field}_max_abs'] = max(map(abs, values))
        out.append(result)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=Path('experiments/ts_predictor_r14'))
    parser.add_argument('--ledger-points', type=Path, default=Path('docs/experiments/results/rd_points.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('runs/ts_r14_partial_20261024'))
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    controls = read_controls(args.ledger_points)
    inputs, audit, availability, datasets = [], [], [], dict(controls)
    for mode, name in MODE_NAMES.items():
        path = args.input_dir / f'{mode}.csv'
        points, issues, sources = read_results(path)
        inputs.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        if issues:
            raise ValueError(f'{path}: {issues}')
        audit.append(dict(mode=mode, mode_name=name, measured=len(points), issues=issues,
                          excluded=mode == 2, exclusion_reason='user-reported inaccurate result' if mode == 2 else ''))
        for sequence in SEQUENCES:
            qps = sorted(qp for seq, qp in points if seq == sequence)
            availability.append(dict(mode=mode, mode_name=name, sequence=sequence,
                                     class_name=SEQUENCES[sequence][0], measured_qps=' '.join(map(str, qps)),
                                     missing_qps=' '.join(str(qp) for qp in (22, 27, 32, 37) if qp not in qps),
                                     measured_count=len(qps), diagnostic3_available=int(set(DIAG_QPS) <= set(qps)),
                                     usable_for_effects=int(mode != 2)))
        if mode != 2:
            datasets[f'R14-{mode}'] = points
    inputs.append(dict(path=str(args.ledger_points), sha256=hashlib.sha256(args.ledger_points.read_bytes()).hexdigest()))
    comparisons = []
    for mode in MODE_NAMES:
        if mode == 2:
            continue
        comparisons.append((f'R14-{mode}', 'Current', 'versus_current'))
        if mode in INITIAL:
            comparisons.append((f'R14-{mode}', INITIAL[mode], 'versus_fixed_initial'))
    for test, reference in ((10, 1), (12, 3), (13, 4), (14, 5), (15, 6)):
        comparisons.append((f'R14-{test}', f'R14-{reference}', 'pair2_versus_none'))
    for test, reference in ((11, 10), (4, 3), (6, 5), (13, 12), (15, 14)):
        comparisons.append((f'R14-{test}', f'R14-{reference}', 'grid4_versus_grid2'))
    for mode in INITIAL:
        for fixed in (8, 9):
            comparisons.append((f'R14-{mode}', f'R14-{fixed}', 'versus_other_fixed'))
    points, diagnostics = [], []
    complete_sets = [{sequence for sequence in SEQUENCES if all((sequence, qp) in data for qp in DIAG_QPS)}
                     for name, data in datasets.items() if name.startswith('R14-')]
    common_sequences = sorted(set.intersection(*complete_sets))
    for test, reference, relation in comparisons:
        points.extend(compare(datasets[test], datasets[reference], test, reference, relation))
        for sequence in SEQUENCES:
            if not all((sequence, qp) in datasets[test] and (sequence, qp) in datasets[reference] for qp in DIAG_QPS):
                continue
            a = {qp: datasets[reference][sequence, qp] for qp in DIAG_QPS}
            b = {qp: datasets[test][sequence, qp] for qp in DIAG_QPS}
            y, u, v, weighted = bd3(a, b)
            diagnostics.append(dict(test=test, reference=reference, relation=relation, sequence=sequence,
                                    class_name=SEQUENCES[sequence][0], qps='27 32 37',
                                    bd_y_pct=y, bd_u_pct=u, bd_v_pct=v, bd_611_pct=weighted,
                                    in_all_modes_common_subset=int(sequence in common_sequences),
                                    status='diagnostic_3point_not_CTC_no_QP22_imputation'))
    diagnostic_summary = []
    for test, reference, relation in comparisons:
        for scope in ('available_sequences', 'all_modes_common_sequences'):
            selected = [row for row in diagnostics if row['test'] == test and row['reference'] == reference
                        and (scope == 'available_sequences' or row['in_all_modes_common_subset'])]
            if not selected:
                continue
            record = dict(test=test, reference=reference, relation=relation, scope=scope,
                          sequences=' '.join(row['sequence'] for row in selected), sequence_count=len(selected))
            for field in ('bd_y_pct', 'bd_u_pct', 'bd_v_pct', 'bd_611_pct'):
                record[field] = statistics.mean(row[field] for row in selected)
            diagnostic_summary.append(record)
    summaries = [row for dimension in ('all', 'sequence', 'qp', 'class_name') for row in summarize(points, dimension)]
    matched = []
    for pair_mode, none_mode in ((10, 1), (12, 3), (13, 4), (14, 5), (15, 6)):
        fixed = INITIAL[pair_mode]
        views = [{(row['sequence'], row['qp']): row for row in points
                  if row['test'] == f'R14-{mode}' and row['reference'] == fixed
                  and row['relation'] == 'versus_fixed_initial'} for mode in (pair_mode, none_mode)]
        common = set(views[0]) & set(views[1])
        for dimension, values in (('all', ('all',)), ('class_name', ('C', 'E')), ('qp', DIAG_QPS)):
            for value in values:
                selected = [key for key in common if dimension == 'all' or views[0][key][dimension] == value]
                if not selected:
                    continue
                matched.append(dict(pair2=f'R14-{pair_mode}', none=f'R14-{none_mode}', fixed_initial=fixed,
                                    dimension=dimension, group=value, common_points=len(selected),
                                    pair2_rd_equal=sum(views[0][key]['rd_tuple_equal'] for key in selected),
                                    none_rd_equal=sum(views[1][key]['rd_tuple_equal'] for key in selected)))
    write_csv(args.output_dir / 'availability.csv', availability)
    write_csv(args.output_dir / 'point_effects.csv', points)
    write_csv(args.output_dir / 'comparisons.csv', summaries)
    write_csv(args.output_dir / 'matched_initial_comparisons.csv', matched)
    write_csv(args.output_dir / 'diagnostic_3point.csv', diagnostics)
    write_csv(args.output_dir / 'diagnostic_3point_summary.csv', diagnostic_summary)
    metadata = dict(numbering='compact-15-v1', inputs=inputs, audit=audit,
                    measured_points=sum(row['measured'] for row in audit),
                    usable_measured_points=sum(row['measured'] for row in audit if not row['excluded']),
                    missing_qp22_imputed=False, diagnostic_common_sequences=common_sequences,
                    caveats=['RD-tuple equality is at reported precision, not bitstream equality or state evidence.',
                             'Every R14 QP22 is missing. Three-point diagnostics are not complete CTC BD-rate.',
                             'All-sequence summary is equal sequence weighting; incomplete subsets are named.',
                             'No matched-binary/configuration provenance or R14 transition counters in these inputs.'])
    (args.output_dir / 'audit.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({k: metadata[k] for k in ('measured_points', 'usable_measured_points', 'diagnostic_common_sequences')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
