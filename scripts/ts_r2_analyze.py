#!/usr/bin/env python3
"""R2/R3/R4/R5/R6 workbook audit: Current only; component BD-rates first, then YUV 6:1:1.

Missing points are reported, never imputed. Workbook checks do not certify remote
binary/config/frame identity; retain run_metadata.json and encoder/decoder logs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics as st

from ts_fixed_analyze import QPS, bd_rate, self_test, workbook_bdrate, write_csv
from ts_fixed_workbook_analysis import CLASSES, points
from ts_predictor_naming import experiment_directory, R6_MODE_NUMBERS

MODES = ('r2_modal', 'r2_risk', 'r2_cn_log', 'r2_cn_frac')
R3_MODES = ('r3_risk_guard', 'r3_risk_guard_y', 'r3_cn_guard', 'r3_cn_guard_y')
R4_MODES = ('r4_identity_only', 'r4_magnitude_only', 'r4_guard_rescue',
            'r4_directional_risk', 'r4_causal_models', 'r4_signed_plane')
R5_MODES = ('r5_margin_first', 'r5_current_veto')
R6_MODES = tuple(R6_MODE_NUMBERS)
PHASES = {'LB_CE': ('lb', 'CE', ['LB_CE']), 'RA_CD': ('ra', 'CD', ['RA_CD']),
          'LB_B': ('lb', 'B', ['LB_B']), 'LB_BCE': ('lb', 'BCE', ['LB_CE', 'LB_B'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=('r2', 'r3', 'r4', 'r5', 'r6'), default='r2')
    parser.add_argument('--run', type=Path)
    parser.add_argument('--phase', choices=PHASES, default='LB_CE')
    parser.add_argument('--modes')
    parser.add_argument('--anchor', type=Path, default=Path('scripts/JVET-hhi.xlsm'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    self_test()
    supported = {'r2': MODES, 'r3': R3_MODES, 'r4': R4_MODES, 'r5': R5_MODES, 'r6': R6_MODES}[args.revision]
    args.run = args.run or Path('experiments/ts_predictor_' + args.revision)
    modes = args.modes.split(',') if args.modes else list(supported)
    if len(set(modes)) != len(modes) or any(m not in supported for m in modes):
        parser.error('Specify distinct modes belonging to the selected revision')
    config, classes, folders = PHASES[args.phase]
    anchor = points(args.anchor, 'Reference')
    results, raw, missing, sources = [], [], [], []
    max_vba_gap = 0.0
    for mode in modes:
        test = {}
        mode_dir = experiment_directory(args.run, mode)
        paths = [mode_dir / folder / 'JVET-hhi.xlsm' for folder in folders]
        flat = mode_dir / 'JVET-hhi.xlsm'
        if flat.exists():
            paths = [flat]  # Existing batch layout; Reference is still Current.
        for path in paths:
            if not path.exists():
                continue
            if points(path, 'Reference') != anchor:
                raise ValueError(f'Reference is not the Current anchor: {path}')
            for key, value in points(path, 'Test').items():
                if key in test and test[key] != value:
                    raise ValueError(f'Conflicting measured points: {mode} {key}')
                test[key] = value
            sources.append(dict(mode=mode, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for seq, cls in CLASSES.items():
            if cls not in classes:
                continue
            a, t = [], []
            for qp in QPS:
                key = f'{seq}.Q{qp}.ecm.{config}'
                if key not in anchor or anchor[key][1] != 'pass':
                    raise ValueError(f'Current anchor missing/invalid: {key}')
                if key not in test or test[key][1] != 'pass':
                    missing.append(dict(mode=mode, sequence=seq, qp=qp, reason='missing' if key not in test else 'not_pass'))
                    continue
                av, tv = anchor[key][0], test[key][0]
                a.append(av); t.append(tv)
                raw.append(dict(mode=mode, configuration=config, sequence=seq, qp=qp,
                    current_rate=av[0], test_rate=tv[0], current_Y=av[1], current_U=av[2], current_V=av[3],
                    test_Y=tv[1], test_U=tv[2], test_V=tv[3]))
            if len(t) != 4:
                continue
            result = dict(mode=mode, configuration=config, sequence=seq, **{'class': cls}, anchor='current')
            for method in ('pchip', 'cubic'):
                v = []
                for i, comp in enumerate('YUV', 1):
                    ac, tc = [(p[i], p[0]) for p in a], [(p[i], p[0]) for p in t]
                    value, lo, hi = bd_rate(ac, tc, method)
                    result[f'{comp}_{method}'] = value
                    if method == 'pchip':
                        result[f'{comp}_quality_low'] = lo
                        result[f'{comp}_quality_high'] = hi
                        max_vba_gap = max(max_vba_gap, abs(value - workbook_bdrate(ac, tc)))
                    v.append(value)
                result[f'weighted_{method}'] = (6 * v[0] + v[1] + v[2]) / 8
            results.append(result)
    summaries = []
    for mode in modes:
        for group in dict.fromkeys([*classes, classes]):
            expected = {s for s, c in CLASSES.items() if c in group}
            selected = [r for r in results if r['mode'] == mode and r['class'] in group]
            if not selected or {r['sequence'] for r in selected} != expected:
                continue  # Never label a favourable subset as a full class/BCE.
            values = [r['weighted_pchip'] for r in selected]
            rng = random.Random(20260918)
            bootstrap = sorted(st.mean(rng.choices(values, k=len(values))) for _ in range(10000))
            percentiles = st.quantiles(values, n=100, method='inclusive')
            mean = st.mean(values)
            summaries.append(dict(mode=mode, configuration=config, group=group, anchor='current',
                sequences=len(values), mean=mean, median=st.median(values), stddev=st.stdev(values),
                p10=percentiles[9], p90=percentiles[89], ci95_low=bootstrap[249], ci95_high=bootstrap[9749],
                improved=sum(v < 0 for v in values), worst=max(values), best=min(values),
                loo_min=min((sum(values)-v)/(len(values)-1) for v in values),
                loo_max=max((sum(values)-v)/(len(values)-1) for v in values),
                Y=st.mean(r['Y_pchip'] for r in selected), U=st.mean(r['U_pchip'] for r in selected),
                V=st.mean(r['V_pchip'] for r in selected), cubic=st.mean(r['weighted_cubic'] for r in selected),
                bce_effect_tier=('substantial' if mean <= -.10 else 'good' if mean <= -.08 else 'target' if mean <= -.05 else 'below_target') if group == 'BCE' else 'not_BCE'))
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in [('rd_points', raw), ('by_sequence', results), ('summary', summaries), ('missing', missing)]:
        path = args.out / (name + '.csv')
        if rows:
            write_csv(path, rows)
        else:
            path.write_text('mode,sequence,qp,reason\n' if name == 'missing' else 'mode,configuration\n')
    audit = dict(anchor_predictor='current', anchor_sha256=hashlib.sha256(args.anchor.read_bytes()).hexdigest(),
                 sources=sources, revision=args.revision, phase=args.phase, measured_points=len(raw), missing_points=len(missing),
                 imputed_points=0, vba_max_difference_pp=max_vba_gap,
                 provenance='Workbook-only checks, not a verification of remote build/config/frames/hash.',
                 bootstrap='10000 equal-sequence resamples; descriptive content variation, not repeated trials.')
    (args.out/'audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    for row in summaries:
        print(f"{row['mode']:12} {row['group']:3} vs Current: {row['mean']:+.6f}% CI[{row['ci95_low']:+.6f},{row['ci95_high']:+.6f}]")
    if missing:
        raise SystemExit(f'{len(missing)} missing/failed points; no imputation or complete-group claims for incomplete groups')


if __name__ == '__main__':
    main()
