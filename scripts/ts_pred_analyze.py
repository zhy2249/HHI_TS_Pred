#!/usr/bin/env python3
"""Streaming TS predictor analysis. Python standard library only; all input rates are 2^-15 bits."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import random
import statistics

SCALE = 1 << 15
SELECTORS = ['previous_winner', 'cumulative', 'recency', 'confidence', 'simple']
MODES = ['NoPred', 'Current', 'Left', 'Above', 'Min', 'Mean']
RNG = random.Random(20260910)


def ratio(a, b):
    return a / b if b else None


def quantile(values, p):
    if not values:
        return None
    x = sorted(values)
    z = (len(x) - 1) * p
    lo = int(z)
    return x[lo] + (x[min(lo + 1, len(x) - 1)] - x[lo]) * (z - lo)


class Moments:
    def __init__(self):
        self.n = 0
        self.mean = self.m2 = 0.0
        self.sample = []

    def add(self, x):
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)
        if len(self.sample) < 2048:
            self.sample.append(x)
        else:
            i = RNG.randrange(self.n)
            if i < len(self.sample):
                self.sample[i] = x

    def fields(self, prefix):
        return {f'{prefix}_{k}': v for k, v in dict(mean=self.mean,
                std=math.sqrt(self.m2 / (self.n - 1)) if self.n > 1 else None,
                median=quantile(self.sample, .5), p05=quantile(self.sample, .05),
                p95=quantile(self.sample, .95), p99=quantile(self.sample, .99)).items()}


class Aggregate:
    def __init__(self):
        self.total = Counter()
        self.delta = [Moments() for _ in SELECTORS]
        self.margin = Moments()
        self.history_nonzero = Moments()
        self.history_cg = Moments()
        self.transitions = {k: Counter() for k in [1, 2, 3, 4]}
        self.unique_transitions = {k: Counter() for k in [1, 2, 3, 4]}
        # Whole POC clusters: retain dependence between coefficients, CGs, and TUs.
        self.clusters = defaultdict(lambda: [0] * 7)

    def add(self, r, history):
        t = self.total
        t['cg_count'] += 1
        t['ts_tu_count'] += r['CG_index'] == 0
        t['coefficient_count'] += r['num_coeff']
        t['nonzero_count'] += r['num_nonzero']
        t['history_available_cg'] += r['CG_index'] > 0
        t['multiway_tie_cg'] += r['oracle_tie_mask'].bit_count() > 1
        t['single_cg_tu'] += r['CG_index'] == 0 and r['CG_count_in_TU'] == 1
        t['oracle_rate'] += r['oracle_rate']
        t[f'oracle_mode{r["oracle_mode"]}_count'] += 1
        t['simple_cabac_agreement'] += r['simple_mode'] == r['recency_mode']
        t['simple_oracle_agreement'] += bool(r['oracle_tie_mask'] & (1 << r['simple_mode']))
        self.margin.add(r['confidence_margin'] / SCALE)
        self.history_nonzero.add(r['history_nonzero'])
        self.history_cg.add(r['history_cg'])
        for k, v in r.items():
            if (k.startswith('pred') and k != 'prediction_type') or k.startswith('selector'):
                t[k] += v
        frame = self.clusters[(r['sequence'], r['configuration'], r['QP'], r['POC'])]
        frame[0] += r['pred1_rate']
        frame[1] += r['oracle_rate']
        for s in range(5):
            d = r[f'selector{s}_rate'] - r['pred1_rate']
            self.delta[s].add(d / SCALE)
            frame[s + 2] += d
        for lag in self.transitions:
            if len(history) >= lag:
                prev = history[-lag]
                pair = (prev['oracle_mode'], r['oracle_mode'])
                self.transitions[lag][pair] += 1
                if prev['oracle_tie_mask'].bit_count() == r['oracle_tie_mask'].bit_count() == 1:
                    self.unique_transitions[lag][pair] += 1

    def summary(self, bootstrap):
        t = self.total
        a, oracle = t['pred1_rate'], t['oracle_rate']
        out = dict(t)
        for key in list(out):
            if key.endswith('_rate') or (key.endswith('_gain') and not key.endswith('_simple_gain')):
                out[key] /= SCALE
        out.update(average_cg_per_tu=ratio(t['cg_count'], t['ts_tu_count']),
                   oracle_gain=ratio(a - oracle, a), oracle_delta_bits=(oracle - a) / SCALE,
                   simple_cabac_agreement=ratio(t['simple_cabac_agreement'], t['cg_count']),
                   simple_cabac_rate_gap_bits=(t['selector4_rate'] - t['selector2_rate']) / SCALE,
                   tie_fraction=ratio(t['multiway_tie_cg'], t['cg_count']))
        for m in range(6):
            p = f'pred{m}'
            out[f'{p}_fixed_gain'] = ratio(a - t[f'{p}_rate'], a)
            out[f'{p}_path_gain'] = ratio(a - t[f'{p}_path_rate'], a)
            for k in ['hit', 'under', 'over']:
                out[f'{p}_{k}_prob'] = ratio(t[f'{p}_{k}_count'], t['coefficient_count'])
                out[f'{p}_nz_{k}_prob'] = ratio(t[f'{p}_nz_{k}_count'], t['nonzero_count'])
            out[f'{p}_mae'] = ratio(t[f'{p}_abs_error_sum'], t['coefficient_count'])
            for k in ['0', '1', '2', '3_4', '5_9', '10plus']:
                out[f'{p}_modified_{k}_prob'] = ratio(t[f'{p}_modified_level_{k}_count'], t['coefficient_count'])
        for s, name in enumerate(SELECTORS):
            d = t[f'selector{s}_rate'] - a
            out.update({f'{name}_gain': ratio(-d, a), f'{name}_capture_ratio': ratio(-d, a - oracle),
                        f'{name}_path_gain': ratio(a - t[f'selector{s}_path_rate'], a),
                        f'{name}_delta_bits_per_tu': ratio(d / SCALE, t['ts_tu_count'])})
            out.update(self.delta[s].fields(f'{name}_cg_delta_bits'))
        out.update(self.margin.fields('confidence_margin_bits'))
        out.update(self.history_nonzero.fields('history_nonzero'))
        out.update(self.history_cg.fields('history_cg'))
        for lag, pairs in self.transitions.items():
            for label, matrix in [('all', pairs), ('unique', self.unique_transitions[lag])]:
                n = sum(matrix.values())
                left, right = Counter(), Counter()
                for (i, j), v in matrix.items():
                    left[i] += v
                    right[j] += v
                out[f'lag{lag}_{label}_pairs'] = n
                out[f'lag{lag}_{label}_persistence'] = ratio(sum(v for (i, j), v in matrix.items() if i == j), n)
                out[f'lag{lag}_{label}_independent_baseline'] = ratio(sum(left[i] * right[i] for i in range(6)), n * n)
        blocks = list(self.clusters.values())
        out['bootstrap_frame_clusters'] = len(blocks)
        if bootstrap and len(blocks) >= 2:
            draws = [[] for _ in SELECTORS]
            for _ in range(bootstrap):
                sample = RNG.choices(blocks, k=len(blocks))
                denom = sum(x[0] for x in sample)
                for s in range(5):
                    if denom:
                        draws[s].append(sum(x[s + 2] for x in sample) / denom)
            for s, name in enumerate(SELECTORS):
                out[f'{name}_relative_delta_ci025'] = quantile(draws[s], .025)
                out[f'{name}_relative_delta_ci975'] = quantile(draws[s], .975)
        return out


def write_csv(path, rows):
    rows = list(rows)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def groups(r):
    yield 'overall', ()
    for dims in [('sequence',), ('QP',), ('configuration',), ('component',), ('TU_width',), ('TU_height',),
                 ('TU_width', 'TU_height'), ('CG_count_in_TU',), ('prediction_type',), ('bdpcm',),
                 ('sequence', 'configuration', 'QP', 'TU_width', 'TU_height', 'component'),
                 ('configuration', 'TU_width', 'TU_height', 'bdpcm')]:
        yield '/'.join(dims), tuple(r[d] for d in dims)


def choose(scores, maximum=False):
    optimum = max(scores) if maximum else min(scores)
    return 1 if scores[1] == optimum else scores.index(optimum)


def verify_debug(file):
    """Independent mathematical check of actual native/alternative remapping output."""
    checked = 0
    with file.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or 'modified' not in reader.fieldnames:
            return 0
        for row in reader:
            r = {k: int(v) for k, v in row.items()}
            a, l, u = abs(r['q']), abs(r['L']), abs(r['U'])
            p = [0, max(l, u), l, u, min(l, u), (l + u) // 2][r['mode']]
            expected = 0 if a == 0 else 1 if a == p else a + 1 if a < p else a
            if not r['active']:
                expected = a
            assert p == r['p'] and expected == r['modified'], (file, r)
            if r['active']:
                v = r['modified']
                inverse = 0 if not v else p if v == 1 and p else v - int(v <= p)
                assert inverse == a, (file, r)
            assert r['frac_bits'] >= 0
            checked += 1
    return checked


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs', nargs='+', type=Path)
    p.add_argument('--out', type=Path, default=Path('runs/ts_analysis'))
    p.add_argument('--bootstrap', type=int, default=500)
    p.add_argument('--allow-unmarked', action='store_true', help='Allow direct smoke CSVs without batch success markers')
    p.add_argument('--smoke', action='store_true', help='Label output as validation only')
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    files = sorted({f.resolve() for x in args.inputs for f in (x.rglob('*.csv') if x.is_dir() else [x])})
    aggs = defaultdict(Aggregate)
    sweep = defaultdict(lambda: [0, 0, 0])
    census = Counter()
    accepted, rejected, sizes = [], [], set()
    jobs = []
    debug_checked = 0
    text_fields = {'sequence', 'configuration', 'prediction_type'}
    for file in files:
        with file.open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or 'oracle_tie_mask' not in reader.fieldnames:
                if args.smoke and reader.fieldnames and 'modified' in reader.fieldnames:
                    debug_checked += verify_debug(file)
                continue
            if not args.allow_unmarked and not file.with_suffix('.done.json').is_file():
                rejected.append(str(file))
                continue
            if not args.allow_unmarked:
                marker = json.loads(file.with_suffix('.done.json').read_text(encoding='utf-8'))
                assert marker.get('stats_bytes') == file.stat().st_size, f'Statistics changed after completion: {file}'
                assert marker.get('census_bytes') == Path(str(file) + '.tu.csv').stat().st_size, f'Census changed: {file}'
            accepted.append(str(file))
            marker_path = file.with_suffix('.done.json')
            marker = json.loads(marker_path.read_text(encoding='utf-8')) if marker_path.is_file() else {}
            job = dict(file=str(file), sequence=marker.get('sequence'), configuration=marker.get('configuration'),
                       QP=marker.get('QP'), cg_count=0, ts_tu_count=0, coefficient_count=0,
                       current_bits=0, oracle_bits=0, total_bitstream_bits=marker.get('bitstream_bytes', 0) * 8)
            pocs = set()
            history = []
            last_tu, expected_count = None, None
            for line in reader:
                r = {k: v if k in text_fields else int(v) for k, v in line.items()}
                job.update(sequence=r['sequence'], configuration=r['configuration'], QP=r['QP'])
                job['cg_count'] += 1
                job['ts_tu_count'] += r['CG_index'] == 0
                job['coefficient_count'] += r['num_coeff']
                job['current_bits'] += r['pred1_rate'] / SCALE
                job['oracle_bits'] += r['oracle_rate'] / SCALE
                pocs.add(r['POC'])
                if r['TU_id'] != last_tu:
                    if last_tu is not None:
                        assert len(history) == expected_count, f'Incomplete TU in {file}'
                    assert r['CG_index'] == 0, f'Missing CG0 in {file}'
                    history = []
                    cumulative, recency, simple = [0] * 6, [0] * 6, [0] * 6
                    last_tu, expected_count = r['TU_id'], r['CG_count_in_TU']
                assert r['CG_index'] == len(history), f'CG order/duplicate error in {file}'
                rates = [r[f'pred{m}_rate'] for m in range(6)]
                assert r['oracle_rate'] == min(rates) and r['pred1_path_rate'] == rates[1]
                assert r['history_nonzero'] == sum(x['num_nonzero'] for x in history)
                # Replay from prior rows only; catches accidental current-CG score updates.
                expected_modes = [choose([history[-1][f'pred{m}_rate'] for m in range(6)]) if history else 1,
                                  choose(cumulative, True), choose(recency, True), 1, choose(simple, True)]
                ranked = sorted(recency, reverse=True)
                assert r['confidence_margin'] == ranked[0] - ranked[1]
                if len(history) >= 2 and r['history_nonzero'] >= 8 and ranked[0] - ranked[1] >= SCALE:
                    expected_modes[3] = expected_modes[2]
                for s, name in enumerate(SELECTORS):
                    assert r[f'{name}_mode'] == expected_modes[s], (file, r['TU_id'], r['CG_index'], name)
                    assert r[f'selector{s}_rate'] == rates[expected_modes[s]]
                for m in range(6):
                    gain = rates[1] - rates[m]
                    cumulative[m] += gain
                    recency[m] += gain - (recency[m] >> 3)
                    simple[m] += r[f'pred{m}_simple_gain'] - (simple[m] >> 3)
                for m in range(6):
                    assert sum(r[f'pred{m}_{c}_count'] for c in ['hit', 'under', 'over']) == r['num_coeff']
                    assert sum(r[f'pred{m}_modified_level_{c}_count'] for c in ['0', '1', '2', '3_4', '5_9', '10plus']) == r['num_coeff']
                sizes.add((r['TU_width'], r['TU_height'], r['CG_count_in_TU']))
                for key in groups(r):
                    aggs[key].add(r, history)
                # Exploratory grid only: no selection of an optimum on this dataset.
                for cg in [1, 2, 4]:
                    for nz in [4, 8, 16]:
                        for margin in [0, SCALE // 4, SCALE, 4 * SCALE]:
                            mode = r['recency_mode'] if r['history_cg'] >= cg and r['history_nonzero'] >= nz and r['confidence_margin'] >= margin else 1
                            acc = sweep[(r['sequence'], r['configuration'], r['QP'], cg, nz, margin)]
                            acc[0] += rates[1]
                            acc[1] += rates[mode]
                            acc[2] += r['oracle_rate']
                history.append(r)
            if last_tu is not None:
                assert len(history) == expected_count, f'Incomplete last TU in {file}'
            job['pocs_with_tsrc'] = len(pocs)
            job['zero_tsrc_job'] = job['cg_count'] == 0
            job['oracle_savings_over_bitstream_bits'] = ratio(job['current_bits'] - job['oracle_bits'], job['total_bitstream_bits'])
            jobs.append(job)
        census_file = Path(str(file) + '.tu.csv')
        if census_file.is_file():
            with census_file.open(encoding='utf-8', newline='') as f:
                for r in csv.DictReader(f):
                    census[tuple(r[k] for k in ['sequence', 'configuration', 'QP', 'component', 'TU_width', 'TU_height', 'tsrc_enabled', 'bdpcm'])] += 1
    summaries, transitions = [], []
    for (dimension, value), agg in sorted(aggs.items(), key=lambda x: str(x[0])):
        label = dict(dimension=dimension, group=json.dumps(value, ensure_ascii=False))
        summaries.append({**label, **agg.summary(args.bootstrap)})
        for lag in [1, 2, 3, 4]:
            for kind, pairs in [('all', agg.transitions[lag]), ('unique', agg.unique_transitions[lag])]:
                for i in range(6):
                    n = sum(v for (a, b), v in pairs.items() if a == i)
                    for j in range(6):
                        transitions.append({**label, 'lag': lag, 'ties': kind, 'previous': i, 'current': j,
                                            'count': pairs[i, j], 'probability': ratio(pairs[i, j], n)})
    write_csv(args.out / 'ts_pred_summary.csv', summaries)
    write_csv(args.out / 'ts_pred_jobs.csv', jobs)
    write_csv(args.out / 'ts_pred_transitions.csv', transitions)
    write_csv(args.out / 'ts_pred_confidence_exploratory.csv',
              [dict(sequence=k[0], configuration=k[1], QP=k[2], min_cg=k[3], min_nonzero=k[4], margin_bits=k[5] / SCALE,
                    current_bits=v[0] / SCALE, selected_bits=v[1] / SCALE, gain=ratio(v[0] - v[1], v[0]),
                    capture_ratio=ratio(v[0] - v[1], v[0] - v[2])) for k, v in sorted(sweep.items())])
    write_csv(args.out / 'ts_pred_size_census.csv', [dict(zip(
        ['sequence', 'configuration', 'QP', 'component', 'TU_width', 'TU_height', 'tsrc_enabled', 'bdpcm', 'ts_tu_count'],
        [*k, v])) for k, v in sorted(census.items())])
    sequence_rows = [r for r in summaries if r['dimension'] == 'sequence']
    stability = []
    for metric in ['oracle_gain', *[name + '_gain' for name in SELECTORS],
                   *[f'pred{m}_fixed_gain' for m in range(6)]]:
        values = [r[metric] for r in sequence_rows if r.get(metric) is not None]
        draws = [statistics.mean(RNG.choices(values, k=len(values))) for _ in range(args.bootstrap)] if len(values) >= 2 else []
        stability.append(dict(metric=metric, sequences=len(values), positive_sequences=sum(x > 0 for x in values),
                              equal_sequence_mean=statistics.mean(values) if values else None,
                              median=quantile(values, .5), std=statistics.stdev(values) if len(values) > 1 else None,
                              p05=quantile(values, .05), p95=quantile(values, .95),
                              sequence_bootstrap_ci025=quantile(draws, .025), sequence_bootstrap_ci975=quantile(draws, .975)))
    write_csv(args.out / 'ts_pred_sequence_stability.csv', stability)
    overall = next((r for r in summaries if r['dimension'] == 'overall'), {})
    manifest = dict(files=accepted, rejected_unmarked=rejected, observed_sizes=sorted(sizes), debug_coefficients_checked=debug_checked,
                    bootstrap=args.bootstrap, seed=20260910, units='CSV input: fractional integer bits / 32768; summary: bits',
                    interpretation='validation only' if args.smoke else 'fixed-anchor-q predictor-side coding potential; not BD-rate',
                    conclusion='Pending representative results and held-out stability review', overall=overall)
    (args.out / 'analysis.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# TS predictor analysis', '', manifest['interpretation'], '',
             f'Accepted files: {len(accepted)}; rejected unmarked: {len(rejected)}.',
             f'Observed (W,H,CG/TU): {sorted(sizes)}.', '',
             f'Oracle gain: {overall.get("oracle_gain")}; ties: {overall.get("tie_fraction")}.']
    for name in SELECTORS:
        lines.append(f'{name}: gain={overall.get(name + "_gain")}, capture={overall.get(name + "_capture_ratio")}, path gain={overall.get(name + "_path_gain")}.')
    lines += ['', 'Q1–Q10 remain subject to sequence/QP/size stability and the preregistered decision criteria.',
              'Conditional CG Oracle is not a full-TU global optimum. Path rates propagate contexts and budgets across CGs.',
              'Frame bootstrap intervals are conditional on sampled sequences; adjacent frames can remain correlated.',
              'Quantiles use a bounded reservoir (2048 observations per group); means and standard deviations are exact streaming estimates.',
              'Confidence grid is exploratory. Do not choose thresholds and claim validation on the same sequences.',
              'No statistical or engineering conclusion should be drawn from synthetic smoke inputs.']
    (args.out / 'TS_Adaptive_Predictor_Results.md').write_text('\n\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(dict(files=len(accepted), groups=len(summaries), oracle_gain=overall.get('oracle_gain'),
                          recency_capture=overall.get('recency_capture_ratio')), indent=2))
    if not accepted:
        raise SystemExit('No completed statistics inputs accepted')


if __name__ == '__main__':
    main()
