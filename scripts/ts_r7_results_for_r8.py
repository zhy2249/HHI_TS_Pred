#!/usr/bin/env python3
"""Audit the received R7 CE tables for the R8 design; never impute or encode.

Derived files only. Spreadsheet pass is not a remote binary/hash identity check.
Uses the project's component-first PCHIP and equal-sequence aggregation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics as st

from ts_fixed_analyze import QPS, SEQUENCES, self_test, workbook_bdrate, write_csv
from ts_fixed_workbook_analysis import CLASSES, points
from ts_predictor_cross_round_analysis import compare
from ts_r3_results_analysis import distribution
from ts_r6_results_analysis import check_columns, required_points


def audit(root):
    root = Path(root)
    sources = {}

    def remember(path):
        sources[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    anchor = points(remember(root / 'scripts/JVET-hhi.xlsm'), 'Reference')
    keys = required_points(anchor, SEQUENCES)
    paths = {
        'R2-2': 'experiments/ts_predictor_r2/r2_risk/LB_CE/JVET-hhi.xlsm',
        'R3-1': 'experiments/ts_predictor_r3/r3_risk_guard/JVET-hhi.xlsm',
        'R7-1': 'experiments/ts_predictor_r7/R7_1_JVET-hhi.xlsm',
        'R7-2': 'experiments/ts_predictor_r7/R7_2_JVET-hhi.xlsm',
    }
    tables, checks = {'Current': anchor}, []
    for mode, name in paths.items():
        path = remember(root / name)
        reference, test = points(path, 'Reference'), points(path, 'Test')
        if any(reference.get(k) != anchor[k] for k in keys):
            raise ValueError(f'CE Current Reference mismatch: {mode}')
        required_points(test, SEQUENCES)
        if mode.startswith('R7'):
            csv_path = remember(path.with_name(path.name.replace('_JVET-hhi.xlsm', '.csv')))
            check_columns(path, [csv_path], keys)
        tables[mode] = test
        checks.append(dict(mode=mode, measured_CE_points=28, imputed=0,
                           reference_CE_equal=True,
                           csv_B_J_equal=True if mode.startswith('R7') else None,
                           excluded_other_points=len(set(test) - keys)))

    pairs = [('R2-2', 'Current'), ('R3-1', 'Current'),
             ('R7-1', 'Current'), ('R7-2', 'Current'),
             ('R7-1', 'R2-2'), ('R7-2', 'R3-1'),
             ('R7-1', 'R3-1'), ('R7-2', 'R7-1')]
    rows, summaries = [], []
    vba_gap = 0.0
    for mode, parent in pairs:
        rr = []
        for seq in SEQUENCES:
            a, t = [[tables[m][f'{seq}.Q{q}.ecm.lb'][0] for q in QPS]
                    for m in (parent, mode)]
            r = dict(mode=mode, reference=parent, sequence=seq,
                     **{'class': CLASSES[seq]}, **compare(a, t))
            rr.append(r)
            for i, comp in enumerate('YUV', 1):
                vba_gap = max(vba_gap, abs(r[comp] - workbook_bdrate(
                    [(p[i], p[0]) for p in a], [(p[i], p[0]) for p in t])))
        rows.extend(rr)
        for group in ('C', 'E', 'CE'):
            selected = [r for r in rr if r['class'] in group]
            summaries.append(dict(mode=mode, reference=parent, group=group,
                sequences=len(selected), **distribution([r['weighted'] for r in selected]),
                **{c: st.mean(r[c] for r in selected) for c in 'YUV'}))
    for path, digest in sources.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Source changed while reading: {path}')
    return rows, summaries, dict(
        inputs=[dict(path=str(p.relative_to(root)), sha256=h) for p, h in sources.items()],
        checks=checks, input_hashes_unchanged=True, max_vba_difference_pp=vba_gap,
        remote_identity_verified=False, analysis_scope='LB CE only; no imputation',
        warning='No remote mode/config/frame/hash proof; other configurations excluded.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--out', type=Path, default=Path('runs/ts_r8_design/r7_evidence'))
    args = p.parse_args()
    # This narrowly scoped helper may only create ignored, derived run outputs.
    if not args.out.resolve().is_relative_to((args.root / 'runs').resolve()):
        p.error('--out must be below the project runs directory')
    self_test()
    rows, summaries, report = audit(args.root)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / 'by_sequence.csv', rows)
    write_csv(args.out / 'summary.csv', summaries)
    (args.out / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    for r in summaries:
        if r['group'] == 'CE':
            print(f"{r['mode']} vs {r['reference']}: {r['mean']:+.9f}% "
                  f"median={r['median']:+.6f}% improved={r['improved']}/7")


if __name__ == '__main__':
    main()
