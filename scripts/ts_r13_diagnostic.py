#!/usr/bin/env python3
"""Extract R13 final-Writer same-CG fixed-q diagnosis; never launch encoding.

Each branch starts at the trajectory's real CG-entry context and budget.
Fractional-bit totals are conditional on final selected TS blocks, not BD-rate.
The three coefficient shadow populations must never be pooled as one population.
"""
import argparse
import csv
from collections import defaultdict
import math
from pathlib import Path
import re

KEYS = {
    'CG': ('trajectory_policy', 'poc', 'component', 'width', 'height', 'cu_qp',
           'intra', 'bdpcm', 'cg_count_in_tu', 'entry_budget_bucket'),
    'COEFF': ('trajectory_policy', 'poc', 'component', 'width', 'height', 'cu_qp',
              'intra', 'bdpcm', 'shadow_mode', 'cutoff', 'n', 'target_bucket'),
    'RDOQ': ('trajectory_policy', 'poc', 'component', 'width', 'height', 'cu_qp',
             'intra', 'budget_band', 'n', 'probe_mode', 'rice', 'trial_cg_zero'),
}

RDOQ_COUNTS = ('position_count', 'actual_nonzero', 'predictor_changed', 'actual_extra_up',
               'probe_extra_up', 'extra_up_changed', 'quant_level_changed', 'quant_level_increased',
               'quant_level_decreased', 'to_zero', 'from_zero', 'fixed_candidates_quant_changed',
               'native_vs_fixed_quant_changed', 'actual_pre_cg_level_hit', 'probe_local_level_hit',
               'actual_round_minus_one', 'actual_round_plus_one', 'probe_round_minus_one', 'probe_round_plus_one')


def identity(text):
    scopes = re.findall(r'^TS R13 ablation=R13-COMPONENT-v1; scope=([^;]+);', text, re.MULTILINE)
    if len(scopes) > 1 or (scopes and scopes[0] not in ('all', 'luma', 'chroma')):
        raise ValueError('Invalid or duplicate R13 component-ablation identity')
    return dict(diagnostic_scope=scopes[0] if scopes else 'all',
                changes_coding=int(bool(scopes and scopes[0] != 'all')))


def close(a, b, scale=1):
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-8 * max(1, scale))


def validate_rdoq(row, scope):
    if row['probe_mode'] not in (0, 1, 2) or row['trial_cg_zero'] not in (0, 1):
        raise ValueError('Invalid RDOQ probe mode or trial CG flag')
    if any(not math.isfinite(v) for v in row.values()):
        raise ValueError('Non-finite RDOQ diagnostic value')
    for field in RDOQ_COUNTS:
        if row[field] < 0 or row[field] != round(row[field]):
            raise ValueError(f'Invalid RDOQ count: {field}')
    if row['quant_level_changed'] != row['quant_level_increased'] + row['quant_level_decreased']:
        raise ValueError('RDOQ level-change categories do not conserve population')
    if any(row[f] > row['position_count'] for f in RDOQ_COUNTS):
        raise ValueError('RDOQ subpopulation exceeds trial positions')
    d, r, j = (row[k] for k in ('delta_distortion_over_lambda', 'delta_rate_est_bits', 'delta_rd_over_lambda'))
    if not close(d + r, j, abs(d) + abs(r)):
        raise ValueError('RDOQ delta D/lambda + delta R != delta J/lambda')
    if not close(row['probe_rate_est_bits'] - row['actual_rate_est_bits'], r,
                 abs(row['probe_rate_est_bits']) + abs(row['actual_rate_est_bits'])):
        raise ValueError('RDOQ rate-estimate delta does not reconcile')
    actual = {1: 0, 98: 1, 99: 2}.get(row['trajectory_policy'])
    if actual in (1, 2) and ((scope == 'luma' and row['component'] != 0)
                            or (scope == 'chroma' and row['component'] == 0)):
        actual = 0
    if actual == row['probe_mode']:
        fields = ('predictor_changed', 'extra_up_changed', 'quant_level_changed',
                  'fixed_candidates_quant_changed', 'native_vs_fixed_quant_changed',
                  'delta_distortion_over_lambda', 'delta_rate_est_bits', 'delta_rd_over_lambda',
                  'fixed_candidates_delta_rd_over_lambda')
        if any(abs(row[k]) > 1e-9 for k in fields):
            raise ValueError('RDOQ probe matching actual scoped trajectory changed predictor, q or cost')


def parse(text):
    columns, reports = {}, defaultdict(list)
    scope = identity(text)['diagnostic_scope']
    scale = None
    for line in text.splitlines():
        if line.startswith('TS R13 diagnosis='):
            if scale is not None:
                raise ValueError('Multiple diagnosis identities in one log')
            match = re.search(r'\bfrac-scale=(\d+)', line)
            if not match or int(match[1]) <= 0:
                raise ValueError('Missing fractional-bit scale')
            scale = int(match[1])
        for table in KEYS:
            header, prefix = f'TS_R13_DIAG_{table}_HEADER ', f'TS_R13_DIAG_{table} '
            if line.startswith(header):
                fields = tuple(line[len(header):].split(','))
                if table in columns or fields[:len(KEYS[table])] != KEYS[table] or len(set(fields)) != len(fields):
                    raise ValueError(f'Duplicate or incompatible {table} header')
                columns[table] = fields
            elif line.startswith(prefix):
                values = line[len(prefix):].split(',')
                if table not in columns or len(values) != len(columns[table]):
                    raise ValueError(f'{table} row before header or truncated')
                typed = [int(v) if i < len(KEYS[table]) or table != 'RDOQ' else float(v)
                         for i, v in enumerate(values)]
                reports[table].append(dict(zip(columns[table], typed)))
    if scale is None or not any(reports.values()):
        raise ValueError('Missing R13 diagnosis identity or tables; diagnostic defaults OFF')
    if bool(reports.get('CG')) != bool(reports.get('COEFF')):
        raise ValueError('Missing paired final-Writer CG/coefficient table')
    for table, rows in reports.items():
        seen = set()
        for row in rows:
            key = tuple(row[k] for k in KEYS[table])
            if key in seen:
                raise ValueError(f'Duplicate {table} aggregate key')
            seen.add(key)
            if table == 'CG':
                for ref in ('current', 'uniform'):
                    counts = sum(row[f'spatial_vs_{ref}_{s}'] for s in ('better', 'tie', 'worse'))
                    if counts != row['cg_count']:
                        raise ValueError('CG paired outcome counts do not conserve population')
                    net = row[f'spatial_vs_{ref}_loss_fracbits'] - row[f'spatial_vs_{ref}_gain_fracbits']
                    if net != row['spatial_fracbits'] - row[f'{ref}_fracbits']:
                        raise ValueError('CG positive/negative rate differences do not reconcile')
            elif table == 'COEFF':
                if row['shadow_mode'] not in (0, 1, 2) or row['cutoff'] not in (0, 2, 10):
                    raise ValueError('Invalid shadow or syntax cutoff')
                if sum(row[f'target_{s}_count'] for s in ('hit', 'under', 'over')) != row['nonzero_count']:
                    raise ValueError('Target prediction categories do not conserve nonzeros')
                if sum(row[s] for s in ('actual_map1_count', 'actual_map2_count', 'actual_map_gt2_count')) != row['nonzero_count']:
                    raise ValueError('Actual modified levels do not conserve nonzeros')
            else:
                validate_rdoq(row, scope)
    probes = defaultdict(dict)
    for row in reports.get('RDOQ', []):
        key = tuple(row[k] for k in KEYS['RDOQ'] if k != 'probe_mode')
        probes[key][row['probe_mode']] = row
    for variants in probes.values():
        if set(variants) != {0, 1, 2}:
            raise ValueError('Incomplete RDOQ three-probe population')
        for field in ('position_count', 'actual_nonzero', 'actual_extra_up', 'actual_distortion',
                      'actual_rate_est_bits', 'lambda_sum'):
            if any(not close(r[field], variants[0][field]) for r in variants.values()):
                raise ValueError('RDOQ probes do not share the same actual trial population')
    return dict(reports), scale


def write(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def export(logs, output_dir, sequence='', nominal_qp=''):
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = defaultdict(list)
    summaries = []
    trial_summaries = []
    for log in logs:
        text = log.read_text(errors='replace')
        reports, scale = parse(text)
        labels = dict(source_log=str(log), sequence=sequence, nominal_qp=nominal_qp, frac_scale=scale, **identity(text))
        for table, rows in reports.items():
            outputs[table].extend({**labels, **row} for row in rows)
        group_keys = ('trajectory_policy', 'poc', 'component', 'bdpcm')
        groups = defaultdict(dict)
        for row in reports.get('CG', []):
            key = tuple(row[k] for k in group_keys)
            totals = groups[key]
            for field, value in row.items():
                if field not in KEYS['CG']:
                    totals[field] = totals.get(field, 0) + value
        shadows = defaultdict(lambda: defaultdict(int))
        for row in reports.get('COEFF', []):
            key = tuple(row[k] for k in group_keys) + (row['shadow_mode'],)
            for field, value in row.items():
                if field not in KEYS['COEFF']:
                    shadows[key][field] += value
        for key, totals in sorted(groups.items()):
            result = {**labels, **dict(zip(group_keys, key)), **totals}
            for field, value in totals.items():
                if field.endswith('_fracbits'):
                    result[field.replace('_fracbits', '_bits')] = value / scale
            for m, name in enumerate(('current', 'uniform', 'spatial')):
                sh = shadows[key + (m,)]
                if sh['coeff_count'] != totals['coeff_count'] or sh['nonzero_count'] != totals['nonzero_count']:
                    raise ValueError('Shadow and CG populations differ')
                for field in ('nonzero_count', 'regular_nonzero_count', 'target_hit_count', 'target_under_count',
                              'target_over_count', 'target_p_eq_a_minus1_count', 'target_p_eq_a_plus1_count',
                              'actual_map_vs_current_count', 'actual_map_vs_uniform_count', 'actual_map1_count',
                              'all_nz_full_regular_proxy_sum', 'exact_near_support', 'exact_far_support',
                              'down_near_support', 'down_far_support', 'up_near_support', 'up_far_support'):
                    result[f'{name}_{field}'] = sh[field]
                for cat in ('hit', 'under', 'over'):
                    result[f'{name}_{cat}_rate'] = sh[f'target_{cat}_count'] / sh['nonzero_count'] if sh['nonzero_count'] else ''
            result['spatial_minus_current_bits'] = (totals['spatial_fracbits'] - totals['current_fracbits']) / scale
            result['spatial_minus_uniform_bits'] = (totals['spatial_fracbits'] - totals['uniform_fracbits']) / scale
            summaries.append(result)
        trial_keys = ('trajectory_policy', 'poc', 'component', 'probe_mode', 'trial_cg_zero')
        trials = defaultdict(lambda: defaultdict(float))
        for row in reports.get('RDOQ', []):
            key = tuple(row[k] for k in trial_keys)
            for field, value in row.items():
                if field not in KEYS['RDOQ']:
                    trials[key][field] += value
        for key, totals in sorted(trials.items()):
            record = {**labels, 'population': 'TS_RDOQ_search_trials_not_final_selected_TUs',
                      **dict(zip(trial_keys, key)), **totals}
            # Lambda varies across search trials; do not divide aggregate D by
            # average lambda. The code records a sum of per-position D/lambda.
            record['rd_identity_residual'] = (totals['delta_distortion_over_lambda']
                                               + totals['delta_rate_est_bits'] - totals['delta_rd_over_lambda'])
            trial_summaries.append(record)
    for table, rows in outputs.items():
        path = output_dir / ('rdoq_trials.csv' if table == 'RDOQ' else f'writer_{table.lower()}.csv')
        if any(path.resolve() == log.resolve() for log in logs):
            raise ValueError('Output would overwrite an input log')
        write(path, rows)
    if not summaries and not trial_summaries:
        raise ValueError('No usable diagnosis records')
    if summaries:
        write(output_dir / 'writer_by_poc_component.csv', summaries)
    if trial_summaries:
        write(output_dir / 'rdoq_by_poc_component_probe_cg.csv', trial_summaries)
    return len(summaries) + len(trial_summaries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', nargs='+', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--sequence', default='')
    parser.add_argument('--nominal-qp', default='')
    args = parser.parse_args()
    count = export(args.logs, args.output_dir, args.sequence, args.nominal_qp)
    print(f'{count} POC/component summaries; final selected-TS and RDOQ search-trial populations remain separate; not BD-rate')


if __name__ == '__main__':
    main()
