#!/usr/bin/env python3
"""Workbook-only audit for externally encoded LB B and RA CD experiments.

Does not assert binary/config/frame/hash identity from spreadsheet 'pass' alone.
Reuses tested component PCHIP integration; never edits input workbooks.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import statistics as st

from ts_fixed_analyze import (ALL_SEQUENCES, QPS, bd_rate, sheet_values,
                             self_test, workbook_bdrate, write_csv)

CLASSES = {s: c for s, (c, _) in ALL_SEQUENCES.items()}
CLASSES.update(dict.fromkeys(('BasketballPass', 'BQSquare', 'BlowingBubbles', 'RaceHorses'), 'D'))


def points(path, sheet):
    cells = sheet_values(path, sheet)
    rows = {}
    for cell, key in cells.items():
        if not cell.startswith('A') or not isinstance(key, str) or '.ecm.' not in key:
            continue
        row = cell[1:]
        values = [cells.get(c + row) for c in 'BCDE']
        if all(v is None for v in values):
            continue
        assert all(isinstance(v, (float, int)) and math.isfinite(v) for v in values), (path, key)
        assert key not in rows, (path, key, 'duplicate')
        rows[key] = (values, cells.get('J' + row))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=Path('runs/ts_fixed_LB_CE_half'))
    parser.add_argument('--anchor', type=Path, default=Path('scripts/JVET-hhi.xlsm'))
    parser.add_argument('--out', type=Path, default=Path('runs/ts_fixed_LB_CE_half/external_analysis_611'))
    args = parser.parse_args()
    self_test()
    anchor = points(args.anchor, 'Reference')
    results, raw, sources = [], [], []
    max_vba_gap = 0.0
    for mode in ('nopred', 'gradient', 'directional'):
        path = args.run / mode / 'JVET-hhi.xlsm'
        reference, test = points(path, 'Reference'), points(path, 'Test')
        assert reference == anchor, (mode, 'Reference differs from anchor')
        sources.append({'mode': mode, 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'numeric_test_points': len(test)})
        for config, classes in [('lb', 'CE' if mode == 'gradient' else 'BCE'), ('ra', 'CD')]:
            for seq, cls in CLASSES.items():
                if cls not in classes:
                    continue
                a, t = [], []
                for qp in QPS:
                    key = f'{seq}.Q{qp}.ecm.{config}'
                    assert key in test and key in anchor, (mode, key, 'missing')
                    assert test[key][1] == anchor[key][1] == 'pass', (mode, key, 'status')
                    a.append(anchor[key][0]); t.append(test[key][0])
                    raw.append(dict(mode=mode, config=config, sequence=seq, qp=qp,
                                    anchor_rate=a[-1][0], anchor_Y=a[-1][1], anchor_U=a[-1][2], anchor_V=a[-1][3],
                                    test_rate=t[-1][0], test_Y=t[-1][1], test_U=t[-1][2], test_V=t[-1][3]))
                variants = [(mode, t)]
                if config == 'lb' and mode == 'directional':
                    variants.append(('directional_lowQP_policy', t[:2] + a[2:]))
                for label, curve in variants:
                    result = dict(mode=label, config=config, sequence=seq, **{'class': cls})
                    for method in ('pchip', 'cubic'):
                        values = []
                        for i, component in enumerate('YUV', 1):
                            ac = [(p[i], p[0]) for p in a]
                            tc = [(p[i], p[0]) for p in curve]
                            value, lo, hi = bd_rate(ac, tc, method)
                            result[f'{component}_{method}'] = value
                            values.append(value)
                            if method == 'pchip':
                                max_vba_gap = max(max_vba_gap, abs(value - workbook_bdrate(ac, tc)))
                        result[f'weighted_{method}'] = (6 * values[0] + values[1] + values[2]) / 8
                    results.append(result)
    summaries = []
    for config in ('lb', 'ra'):
        for mode in sorted({r['mode'] for r in results if r['config'] == config}):
            available = [r for r in results if r['config'] == config and r['mode'] == mode]
            groups = ['B', 'C', 'E', 'CE', 'BCE'] if config == 'lb' else ['C', 'D', 'CD']
            for group in groups:
                selected = [r for r in available if r['class'] in group]
                if set(r['class'] for r in selected) != set(group):
                    continue
                v = [r['weighted_pchip'] for r in selected]
                rng = random.Random(20260916)
                boot = sorted(st.mean(rng.choices(v, k=len(v))) for _ in range(10000))
                q = st.quantiles(v, n=100, method='inclusive')
                summary = dict(config=config, mode=mode, group=group, sequences=len(v),
                    mean=st.mean(v), median=st.median(v), stddev=st.stdev(v),
                    p10=q[9], p90=q[89], improved=sum(x < 0 for x in v),
                    ci95_low=boot[249], ci95_high=boot[9749],
                    worst=max(v), best=min(v),
                    loo_min=min((sum(v)-x)/(len(v)-1) for x in v),
                    loo_max=max((sum(v)-x)/(len(v)-1) for x in v),
                    cubic=st.mean(r['weighted_cubic'] for r in selected))
                summary.update({c: st.mean(r[f'{c}_pchip'] for r in selected) for c in 'YUV'})
                summaries.append(summary)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out/'rd_points.csv', raw)
    write_csv(args.out/'by_sequence.csv', results)
    write_csv(args.out/'summary.csv', summaries)
    audit = dict(sources=sources, anchor_sha256=hashlib.sha256(args.anchor.read_bytes()).hexdigest(),
                 vba_max_difference_pp=max_vba_gap, points=len(raw),
                 validation='Workbook numeric points, reference equality, status cells, monotonicity and overlap only; no external logs/binaries/config/frame/hash audit.',
                 policy='Previously proposed nominal QP 22/27 directional, QP 32/37 anchor; offline curve, NOT implemented slice/TU gating.',
                 bootstrap='10000 sequence resamples, descriptive uncertainty; not independent repeated encoding trials.')
    (args.out/'audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    for r in summaries:
        print(f"{r['config']} {r['mode']:27} {r['group']:3} {r['mean']:+.6f}% CI[{r['ci95_low']:+.6f},{r['ci95_high']:+.6f}] {r['improved']}/{r['sequences']}")


if __name__ == '__main__':
    main()
