#!/usr/bin/env python3
"""Reproduce R13 LB CE analysis from the read-only results ledger.

Current remains the primary anchor. Mechanism comparisons directly integrate
the two actual four-point curves, never subtract their Current BD percentages.
Quality halves retain the four-point PCHIP fit; QP deltas are not BD-rate.
Only explicitly named, complete, measured LB CE records are accepted.
"""
import argparse
import csv
from functools import lru_cache
import hashlib
import io
import json
import math
from pathlib import Path
import random
import statistics as st

from ts_fixed_analyze import QPS, SEQUENCES, pchip_integral, self_test, write_csv
from ts_predictor_cross_round_analysis import compare, weighted

MODES = {
    'R2-2': 'r2_risk', 'R3-1': 'r3_risk_guard',
    'R6-2': 'r6_reject_nopred', 'R12-11': 'r12_c_distance_softtrim',
    'R13-1': 'r13_keep_hit_uniform', 'R13-2': 'r13_keep_hit_spatial',
}
SEQS = tuple(sorted(SEQUENCES))
COMPONENTS = ('Y', 'U', 'V', 'weighted')
PRIMARY = tuple(('Current', mode) for mode in MODES)
PAIRED = tuple((reference, mode) for mode in ('R13-1', 'R13-2')
               for reference in ('R2-2', 'R3-1', 'R6-2', 'R12-11')) + (
    ('R13-1', 'R13-2'),)
GROUPS = {
    'CE': SEQS,
    'C': tuple(s for s in SEQS if SEQUENCES[s][0] == 'C'),
    'E': tuple(s for s in SEQS if SEQUENCES[s][0] == 'E'),
    'CE_without_PartyScene': tuple(s for s in SEQS if s != 'PartyScene'),
    'CE_without_KristenAndSara': tuple(s for s in SEQS if s != 'KristenAndSara'),
    'CE_without_PartyScene_and_KristenAndSara': tuple(
        s for s in SEQS if s not in ('PartyScene', 'KristenAndSara')),
}
SEED = 20261023


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def values(row, prefix):
    result = tuple(float(row[prefix + name]) for name in (
        'rate_kbps', 'psnr_y_db', 'psnr_u_db', 'psnr_v_db'))
    if result[0] <= 0 or not all(map(math.isfinite, result)):
        raise ValueError('Invalid RD values: ' + repr(row))
    return result


def select_rows(rows):
    """Whitelist six experiments, exact seven CE sequences, four QPs; no fill."""
    selected = {}
    for row in rows:
        experiment, sequence = row['experiment'], row['sequence']
        if experiment not in MODES or row['configuration'] != 'LB':
            continue
        if sequence not in SEQS:
            if row['class_name'] in ('C', 'E'):
                raise ValueError('Unexpected CE sequence: ' + sequence)
            continue  # B and any other configuration/population are out of scope.
        if row['class_name'] != SEQUENCES[sequence][0]:
            raise ValueError('Sequence/class mismatch: ' + sequence)
        if row['mode'] != MODES[experiment]:
            raise ValueError('Experiment/mode mismatch: ' + experiment)
        if row['status'] != 'measured' or any(row[k] != 'pass' for k in (
                'anchor_record_status', 'test_record_status')):
            raise ValueError('Unmeasured or failed required point: ' + repr(row))
        qp = int(row['qp'])
        key = experiment, sequence, qp
        if qp not in QPS or key in selected:
            raise ValueError('Unexpected QP or duplicate point: ' + repr(key))
        values(row, 'anchor_'); values(row, 'test_')
        selected[key] = row
    expected = {(e, s, q) for e in MODES for s in SEQS for q in QPS}
    if set(selected) != expected:
        raise ValueError('Missing required measured points: ' + repr(sorted(expected - set(selected))))
    for (experiment, sequence, qp), row in selected.items():
        if values(row, 'anchor_') != values(selected['R13-1', sequence, qp], 'anchor_'):
            raise ValueError(f'Current reference mismatch: {experiment} {sequence} QP{qp}')
    # Validate every curve through the shared authoritative implementation.
    for experiment in MODES:
        for sequence in SEQS:
            aa = [values(selected[experiment, sequence, q], 'anchor_') for q in QPS]
            tt = [values(selected[experiment, sequence, q], 'test_') for q in QPS]
            compare(aa, tt)
    return selected


def quality_halves(a, b):
    """Integrate existing four-point PCHIPs over each component's common halves."""
    expected = compare(a, b)
    result = [dict(band='low_quality_half'), dict(band='high_quality_half')]
    for i, component in enumerate('YUV', 1):
        curves = [sorted((p[i], p[0]) for p in c) for c in (a, b)]
        low, high = max(c[0][0] for c in curves), min(c[-1][0] for c in curves)
        middle = (low + high) / 2
        total_area = 0.0
        for row, lo, hi in zip(result, (low, middle), (middle, high)):
            integrals = [pchip_integral([q for q, r in c], [math.log(r) for q, r in c], lo, hi)
                         for c in curves]
            area = integrals[1] - integrals[0]
            row[component] = 100 * math.expm1(area / (hi - lo))
            row[component + '_low_db'], row[component + '_high_db'] = lo, hi
            row[component + '_log_area'] = area
            total_area += area
        if abs(100 * math.expm1(total_area / (high - low)) - expected[component]) > 1e-9:
            raise ValueError('Quality-half integration does not reconstruct full BD-rate')
    for row in result:
        row['weighted'] = weighted([row[c] for c in 'YUV'])
    return result


def percentile(values, probability):
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lo = math.floor(index)
    fraction = index - lo
    return ordered[lo] * (1 - fraction) + ordered[min(lo + 1, len(ordered) - 1)] * fraction


@lru_cache(maxsize=8)
def bootstrap_indices(n, count, seed):
    rng = random.Random(seed)
    return tuple(tuple(rng.choices(range(n), k=n)) for _ in range(count))


def distribution(values_, count=10000, seed=SEED):
    """Sequence-cluster percentile CI; shared index draws preserve paired rows."""
    n = len(values_)
    if n < 2 or count < 1:
        raise ValueError('At least two sequences and one bootstrap sample required')
    mean = st.mean(values_)
    boot = [sum(values_[i] for i in indices) / n
            for indices in bootstrap_indices(n, count, seed)]
    loo = [(sum(values_) - v) / (n - 1) for v in values_]
    return dict(mean=mean, median=st.median(values_), stddev=st.stdev(values_),
                p10=percentile(values_, .1), p90=percentile(values_, .9),
                ci95_low=percentile(boot, .025), ci95_high=percentile(boot, .975),
                improved=sum(v < 0 for v in values_), best=min(values_), worst=max(values_),
                loo_mean_min=min(loo), loo_mean_max=max(loo))


def summarize(rows, count):
    summaries = []
    for group, sequences in GROUPS.items():
        by_name = {r['sequence']: r for r in rows}
        summary = dict(reference=rows[0]['reference'], experiment=rows[0]['experiment'],
                       configuration='LB', group=group, sequences=len(sequences))
        for component in COMPONENTS:
            summary.update({component + '_' + key: val for key, val in distribution(
                [by_name[s][component] for s in sequences], count).items()})
        summaries.append(summary)
    return summaries


def qp_deltas(a, b):
    return dict(rate_delta_pct=100 * (b[0] / a[0] - 1),
                **{c + '_delta_db': b[i] - a[i] for i, c in enumerate('YUV', 1)})


def analyze(selected, count):
    tables = {name: [] for name in ('by_sequence', 'summary', 'paired_by_sequence',
              'paired_summary', 'leave_one_out', 'quality_halves_by_sequence',
              'quality_halves_summary', 'qp_delta_by_sequence', 'qp_delta_summary')}
    def curve(experiment, sequence):
        source = 'R13-1' if experiment == 'Current' else experiment
        prefix = 'anchor_' if experiment == 'Current' else 'test_'
        return [values(selected[source, sequence, q], prefix) for q in QPS]
    for reference, experiment in PRIMARY + PAIRED:
        rows, bands, deltas = [], [], []
        for sequence in SEQS:
            a, b = curve(reference, sequence), curve(experiment, sequence)
            meta = dict(reference=reference, experiment=experiment, configuration='LB',
                        sequence=sequence, class_name=SEQUENCES[sequence][0])
            rows.append({**meta, **compare(a, b)})
            bands.extend({**meta, **band} for band in quality_halves(a, b))
            deltas.extend({**meta, 'qp': qp, **qp_deltas(aa, bb)}
                          for qp, aa, bb in zip(QPS, a, b))
        prefix = '' if reference == 'Current' else 'paired_'
        tables[prefix + 'by_sequence'].extend(rows)
        tables[prefix + 'summary'].extend(summarize(rows, count))
        tables['quality_halves_by_sequence'].extend(bands)
        tables['qp_delta_by_sequence'].extend(deltas)
        for excluded in SEQS:
            retained = [r for r in rows if r['sequence'] != excluded]
            tables['leave_one_out'].append(dict(reference=reference, experiment=experiment,
                configuration='LB', excluded_sequence=excluded, sequences=len(retained),
                **{c: st.mean(r[c] for r in retained) for c in COMPONENTS}))
        for group in ('CE', 'C', 'E'):
            base = dict(reference=reference, experiment=experiment, configuration='LB',
                        group=group, sequences=len(GROUPS[group]))
            for band in ('low_quality_half', 'high_quality_half'):
                rr = [r for r in bands if r['sequence'] in GROUPS[group] and r['band'] == band]
                tables['quality_halves_summary'].append({**base, 'band': band,
                    **{c: st.mean(r[c] for r in rr) for c in COMPONENTS}})
            for qp in QPS:
                rr = [r for r in deltas if r['sequence'] in GROUPS[group] and r['qp'] == qp]
                tables['qp_delta_summary'].append({**base, 'qp': qp,
                    **{c: st.mean(r[c] for r in rr) for c in (
                        'rate_delta_pct', 'Y_delta_db', 'U_delta_db', 'V_delta_db')},
                    'lower_rate_count': sum(r['rate_delta_pct'] < 0 for r in rr)})
    return tables


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('docs/experiments/results/rd_points.csv'))
    parser.add_argument('--sources', type=Path, default=Path('docs/experiments/results/sources.json'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1],
                        help='Repository root for provenance paths recorded in the ledger')
    parser.add_argument('--out', type=Path, default=Path('runs/ts_r13_results_20261023'))
    parser.add_argument('--bootstrap', type=int, default=10000)
    args = parser.parse_args(argv)
    if args.bootstrap < 1:
        parser.error('--bootstrap must be positive')
    self_test()
    raw = args.input.read_bytes()
    provenance_raw = args.sources.read_bytes()
    selected = select_rows(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    provenance = json.loads(provenance_raw)
    expected_hashes = {r['path']: r['sha256'] for r in provenance['sources']}
    paths = sorted({r[k] for r in selected.values() for k in ('source_file', 'anchor_file')})
    checked = []
    protected = {args.input.resolve(), args.sources.resolve()}
    for path in paths:
        source = (args.root / path).resolve()
        protected.add(source)
        actual = digest(source)
        if expected_hashes.get(path) != actual:
            raise ValueError('Missing or stale source fingerprint: ' + path)
        checked.append(dict(path=path, sha256=actual))
    tables = analyze(selected, args.bootstrap)
    outputs = {key: args.out / (key + '.csv') for key in tables}
    outputs['audit'] = args.out / 'audit.json'
    if any(path.resolve() in protected for path in outputs.values()):
        raise ValueError('Output would overwrite a protected input')
    if args.input.read_bytes() != raw or args.sources.read_bytes() != provenance_raw:
        raise ValueError('Input ledger changed while analyzing; regenerate after registration completes')
    if any(digest(args.root / row['path']) != row['sha256'] for row in checked):
        raise ValueError('Source file changed while analyzing')
    audit = dict(
        protocol='R13-LB-CE-analysis-v1', configuration='LB', classes='CE',
        experiments=list(MODES), points_per_experiment=28, selected_points=len(selected),
        measured_only=True, imputed_points=0, common_current_verified=True,
        current_anchor='Current', formula='PCHIP component BD-rate; (6Y+U+V)/8; equal sequence means',
        primary_and_pairwise_units='percent; negative means test better than stated reference',
        pairwise_method='Direct integration of test versus comparison curves, not Current BD subtraction',
        quality_halves='Original four-point PCHIP, each component common quality midpoint; not two-point fits',
        qp_deltas='Same-QP total rate percentage and separate Y/U/V dB changes; not BD-rate',
        bootstrap=dict(unit='sequence', replacement=True, samples=args.bootstrap, seed=SEED,
                       interval='2.5/97.5 percentile, inclusive linear interpolation',
                       limitation='Only 7 CE sequences (4 C, 3 E); exploratory stability, not universal inference'),
        inputs=[dict(path=str(args.input), sha256=hashlib.sha256(raw).hexdigest()),
                dict(path=str(args.sources), sha256=hashlib.sha256(provenance_raw).hexdigest())],
        sources=checked, sources_unchanged=True,
        remote_build_config_frames_decode_hash_verified=False,
        output_rows={key: len(rows) for key, rows in tables.items()},
    )
    args.out.mkdir(parents=True, exist_ok=True)
    for key, rows in tables.items():
        write_csv(outputs[key], rows)
    outputs['audit'].write_text(json.dumps(audit, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(out=str(args.out), selected_points=len(selected),
                          outputs=audit['output_rows'], sources_unchanged=True), ensure_ascii=False))


if __name__ == '__main__':
    main()
