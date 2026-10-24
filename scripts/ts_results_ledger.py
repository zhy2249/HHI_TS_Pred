#!/usr/bin/env python3
"""Export read-only workbook/explicit CSV data to a results-only TS ledger.

No encoding, workbook writes, Excel macro execution, or inferred measurements.
Only the explicitly recorded historical missing points may use Current data.
"""
import argparse
from collections import Counter
import csv
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics

from ts_fixed_analyze import QPS, bd_rate, self_test, sheet_values, workbook_bdrate
from ts_fixed_workbook_analysis import CLASSES
from ts_predictor_naming import R14_MODE_NUMBERS

KEY = re.compile(r'^(.+)\.Q(\d+)\.ecm\.(lb|ra|ai|lp)$')
METRICS = ('rate_kbps', 'psnr_y_db', 'psnr_u_db', 'psnr_v_db')
BD = ('bd_y_pct', 'bd_u_pct', 'bd_v_pct', 'bd_611_pct')
R9_MODES = ('r9_p10', 'r9_p12', 'r9_axis_sparse', 'r9_half_penalty',
            'r9_feature_penalty', 'r9_unit_risk', 'r9_protect_one', 'r9_joint_mapping',
            'r9_expert_integer', 'r9_expert_fractional', 'r9_quant_down',
            'r9_quant_down_up', 'r9_axis_feature')
R10_MODES = ('r10_expert_axis_A', 'r10_expert_p1_A', 'r10_integer_then_fractional',
             'r10_matched_state_weights', 'r10_delete_one_validation',
             'r10_protected_mapping_expert')  # Uploaded results only; R10-7 pending.
R11_MODES = ('r11_no_evidence_r3', 'r11_query_context_tie', 'r11_same_cg_local8',
             'r11_same_tu_local8', 'r11_add_native_current', 'r11_add_identity',
             'r11_no_evidence_query', 'r11_no_evidence_tu8')
R12_MODES = ('r12_ci_near1', 'r12_r3_near1', 'r12_current_near1', 'r12_loo_unstable_cf',
             'r12_direct_first', 'r12_r3_near1_loo', 'r12_c_distance_raw',
             'r12_c_distance_fulltrim', 'r12_validation_distance', 'r12_validation_distance_tie',
             'r12_c_distance_softtrim', 'r12_c_and_validation_distance')  # R12-POS-01 public numbering.
R13_MODES = ('r13_keep_hit_uniform', 'r13_keep_hit_spatial')  # R13-KH-168-v1 public numbering.
R14_MODES = tuple(sorted(R14_MODE_NUMBERS, key=R14_MODE_NUMBERS.get))  # compact-15-v1.
QP_ANALYSIS_ROUNDS = ('r3', 'r6', 'r13', 'r14')  # Explicitly requested result scope.
# R14-2's replacement upload was confirmed correct by the user on 2026-10-24.
# Exclude only the previously rejected file, not every future R14-2 result.
REJECTED_CSV_SOURCES = {
    'R14-2': {
        '5437fb0e450889be13d638c3e4ec0d1abcb3779f01438058371295ad2019a5b4':
            '用户此前确认本版 R14-2 结果不准确；仅保留原值，不用于 BD-rate。'
    }
}
STATUS = {'measured': '实测', 'anchor_imputed': 'anchor 补点',
          'missing': '缺失', 'complete': '完整实测',
          'imputed': '含补点', 'incomplete': '不完整，不计算', 'invalid': '无有效公共曲线',
          'invalid_anchor': '参考点未通过，不计算',
          'excluded_unreliable': '用户确认不准确，仅留原值，不计算'}
QP_STATUS = dict(STATUS, calculated='已计算', invalid_target='目标点未通过，不计算',
                 anchor_imputed='未实测（历史anchor补点）')


def catalog(root):
    """Explicit experiment identities; never infer a mode from arbitrary uploads."""
    specs = []

    def add(group, experiment, mode, path, expected='CE', extra_csv=()):
        specs.append(dict(round=group, experiment=experiment, mode=mode,
                          path=path, expected_lb=expected, extra_csv=extra_csv))
        if group in QP_ANALYSIS_ROUNDS:
            specs[-1]['qp_analysis'] = True

    for name in ('nopred', 'gradient', 'directional'):
        add('fixed', 'Fixed-' + {'nopred': 'NoPred', 'gradient': 'Gradient', 'directional': 'Directional'}[name],
            name, f'runs/ts_fixed_LB_CE_half/{name}/JVET-hhi.xlsm', 'CE' if name == 'gradient' else 'BCE')
    for experiment, mode in zip(('N1', 'N2', 'A1', 'A2', 'A3'), ('q32', 'conf2', 'prev', 'ewma', 'q32_ewma')):
        add('conditional', experiment, mode, f'experiments/ts_conditional_v1/{mode}/LB_BCE/JVET-hhi.xlsm')
    for i, mode in enumerate(('r2_modal', 'r2_risk', 'r2_cn_log', 'r2_cn_frac'), 1):
        add('r2', f'R2-{i}', mode, f'experiments/ts_predictor_r2/{mode}/LB_CE/JVET-hhi.xlsm')
    for i, mode in enumerate(('r3_risk_guard', 'r3_risk_guard_y', 'r3_cn_guard', 'r3_cn_guard_y'), 1):
        add('r3', f'R3-{i}', mode, f'experiments/ts_predictor_r3/{mode}/JVET-hhi.xlsm', 'BCE' if i <= 2 else 'CE')
    for i, name in enumerate(('identity_only', 'magnitude_only', 'guard_rescue', 'directional_risk', 'causal_models', 'signed_plane'), 1):
        add('r4', f'R4-{i}', 'r4_' + name, f'experiments/ts_predictor_r4/r4_{i}_{name}/R4_{i}_JVET-hhi.xlsm')
    add('r5', 'R5-1', 'r5_margin_first', 'experiments/ts_predictor_r5/r5_1_margin_first/JVET-hhi.xlsm')
    add('r5', 'R5-2', 'r5_current_veto', 'experiments/ts_predictor_r5/JVET-hhi.xlsm')
    for i, name in enumerate(('dense_nopred', 'reject_nopred', 'trim_cost', 'trim_saving', 'sparse_max', 'sparse_mean', 'sparse_min'), 1):
        add('r6', f'R6-{i}', 'r6_' + name, f'experiments/ts_predictor_r6/R6_{i}_JVET-hhi.xlsm')
    for i, mode in enumerate(('rate_raw', 'rate_guard'), 1):
        add('r7', f'R7-{i}', mode, f'experiments/ts_predictor_r7/R7_{i}_JVET-hhi.xlsm')
    for i in range(1, 25):
        choices = [p for p in (root / 'experiments/ts_predictor_r8').glob('*_JVET-hhi.xlsm')
                   if p.name.lower() == f'r8_{i}_jvet-hhi.xlsm']
        if len(choices) != 1:
            raise ValueError(f'R8-{i}: expected exactly one source workbook, got {choices}')
        add('r8', f'R8-{i}', f'R8_MODE={i}', choices[0].relative_to(root).as_posix())
    for i, mode in enumerate(R9_MODES, 1):
        add('r9', f'R9-{i}', mode, f'experiments/ts_predictor_r9/R9_{i}_JVET-hhi.xlsm',
            'BCE' if i == 9 else 'CE')
    for i, mode in enumerate(R10_MODES, 1):
        add('r10', f'R10-{i}', mode, f'experiments/ts_predictor_r10/R10_{i}_JVET-hhi.xlsm',
            'BCE' if i == 3 else 'CE', ('3_B.csv',) if i == 3 else ())
    for i, mode in enumerate(R11_MODES, 1):
        add('r11', f'R11-{i}', mode, f'experiments/ts_predictor_r11/R11_{i}_JVET-hhi.xlsm',
            'BCE' if i == 2 else 'CE')
    for i, mode in enumerate(R12_MODES, 1):
        add('r12', f'R12-{i}', mode, f'experiments/ts_predictor_r12/R12_{i}_JVET-hhi.xlsm')
    for i, mode in enumerate(R13_MODES, 1):
        add('r13', f'R13-{i}', mode, f'experiments/ts_predictor_r13/R13_{i}_JVET-hhi.xlsm')
    for i, mode in enumerate(R14_MODES, 1):
        add('r14', f'R14-{i}', mode, f'experiments/ts_predictor_r14/{i}.csv')
        specs[-1]['source_format'] = 'csv'
        specs[-1]['numbering_revision'] = 'compact-15-v1'
        rejected = REJECTED_CSV_SOURCES.get(specs[-1]['experiment'], {})
        source = root / specs[-1]['path']
        if rejected and source.is_file():
            reason = rejected.get(hashlib.sha256(source.read_bytes()).hexdigest())
            if reason:
                specs[-1]['excluded_reason'] = reason
    return specs


def imputation_allowed(experiment, config, seq, qp):
    # Frozen historical exceptions, NOT a general "fill missing QP22" rule.
    allowed = {
        'A1': {'PartyScene'}, 'A2': {'BQMall', 'PartyScene', 'FourPeople'},
        'A3': {'BQMall', 'PartyScene', 'FourPeople', 'Johnny', 'KristenAndSara'},
        'R2-4': {'PartyScene'}, 'R3-2': {'MarketPlace', 'BasketballDrive', 'BQTerrace'},
        'R8-23': {'PartyScene'}, 'R8-24': {'PartyScene'},
        # 2026-09-29: explicit permission for the presently missing QP22 points.
        # Do not extend to other sequences, rounds, configurations or QPs.
        'R9-9': {'MarketPlace', 'Cactus', 'BasketballDrive', 'BQTerrace'},
        'R10-6': {'PartyScene', 'RaceHorsesC'},
    }
    return config == 'lb' and qp == 22 and seq in allowed.get(experiment, ())


def csv_sources(spec, path):
    """Shared result folders contain other experiments: pair by exact ID."""
    if spec.get('source_format') == 'csv':
        return []  # This CSV is the explicit primary source, not a workbook supplement.
    if spec['round'] == 'r13':
        # Server exports use R13_1.csv, not 1.csv; accept only the exact name.
        source = path.parent / (spec['experiment'].replace('-', '_') + '.csv')
        return [source] if source.exists() else []
    if spec['round'] in ('r8', 'r9', 'r10', 'r11', 'r12'):
        names = [spec['experiment'].split('-')[1] + '.csv', *spec.get('extra_csv', ())]
        return [path.parent / name for name in names if (path.parent / name).exists()]
    if re.fullmatch(r'R[2-7]-\d+', spec['experiment']):
        prefix = spec['experiment'].replace('-', '_')
        return sorted(p for p in path.parent.glob('*.csv')
                      if p.stem == prefix or p.stem.startswith(prefix + '_'))
    return sorted(path.parent.glob('*.csv'))


def read_sheet(path, sheet):
    cells = sheet_values(path, sheet)
    values, locations, statuses = {}, {}, {}
    for address, key in cells.items():
        if not re.fullmatch(r'A\d+', address) or not isinstance(key, str) or not KEY.fullmatch(key):
            continue
        if key in locations:
            raise ValueError(f'Duplicate {path}:{sheet}:{key}')
        row = address[1:]
        locations[key] = f'{sheet}!B{row}:E{row}'
        statuses[key] = cells.get('J' + row) or ''
        data = [cells.get(col + row) for col in 'BCDE']
        if all(v is None or v == '' for v in data):
            continue
        if not all(type(v) in (int, float) and math.isfinite(v) for v in data) or data[0] <= 0:
            raise ValueError(f'Invalid RD tuple: {path}:{key}: {data}')
        values[key] = data
    return values, locations, statuses


def read_primary_csv(path):
    """Read one explicitly registered flat export; retain original physical lines.

    Columns B:E contain RD values and J the exporter status. Empty template rows
    remain missing. No workbook or CSV in the shared directory is inferred.
    """
    values, locations, statuses = {}, {}, {}
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row or not KEY.fullmatch(row[0]):
                continue
            key = row[0]
            if key in locations:
                raise ValueError(f'Duplicate CSV row: {path}:{key}')
            line = reader.line_num
            locations[key] = f'CSV!B{line}:E{line}'
            statuses[key] = row[9].strip() if len(row) > 9 else ''
            fields = row[1:5]
            if not any(v.strip() for v in fields):
                continue
            try:
                data = [float(v) for v in fields]
            except ValueError as error:
                raise ValueError(f'Invalid RD tuple: {path}:{key}: {fields}') from error
            if len(data) != 4 or not all(math.isfinite(v) for v in data) or data[0] <= 0:
                raise ValueError(f'Invalid RD tuple: {path}:{key}: {fields}')
            values[key] = data
    return values, locations, statuses


def point_values(experiment, config, seq, qp, actual, anchor):
    if actual is not None:
        return actual, 'measured'
    if imputation_allowed(experiment, config, seq, qp):
        return anchor[:], 'anchor_imputed'
    return [''] * 4, 'missing'


def sequence_result(rows, excluded_reason=''):
    """A missing point never becomes zero BD-rate or a three-point fit."""
    if sorted(r['qp'] for r in rows) != list(QPS):
        raise ValueError('Expected one row for each of QP22/27/32/37')
    # measured_points counts received numeric tuples, including explicitly
    # excluded ones. Inclusion in any BD calculation is controlled by status.
    result = dict(measured_points=sum(r['status'] in ('measured', 'excluded_unreliable') for r in rows),
                  imputed_points=sum(r['status'] == 'anchor_imputed' for r in rows),
                  missing_points=sum(r['status'] == 'missing' for r in rows),
                  **dict.fromkeys(BD, ''), calculation_error='')
    for c in 'yuv':
        result[f'{c}_overlap_low_db'] = result[f'{c}_overlap_high_db'] = ''
    result['max_vba_gap_pp'] = ''
    if excluded_reason or any(r['status'] == 'excluded_unreliable' for r in rows):
        return dict(result, status='excluded_unreliable',
                    calculation_error=excluded_reason or 'Unreliable result excluded from BD-rate')
    if any(r['anchor_record_status'] != 'pass' for r in rows):
        return dict(result, status='invalid_anchor')
    if result['missing_points']:
        return dict(result, status='incomplete')
    vals, gap, bounds = [], 0.0, {}
    try:
        for c in 'yuv':
            a = [(r[f'anchor_psnr_{c}_db'], r['anchor_rate_kbps']) for r in rows]
            t = [(r[f'test_psnr_{c}_db'], r['test_rate_kbps']) for r in rows]
            value, low, high = bd_rate(a, t)
            gap = max(gap, abs(value - workbook_bdrate(a, t)))
            vals.append(value)
            bounds.update({f'{c}_overlap_low_db': low, f'{c}_overlap_high_db': high})
    except (AssertionError, ValueError, ZeroDivisionError) as e:
        return dict(result, status='invalid', calculation_error=str(e) or 'Invalid monotonic/overlap curve')
    if gap > 1e-8:
        raise ValueError(f'Workbook formula cross-check failed: {gap}')
    vals.append((6 * vals[0] + vals[1] + vals[2]) / 8)
    return dict(result, **dict(zip(BD, vals)), **bounds, max_vba_gap_pp=gap,
                status='imputed' if result['imputed_points'] else 'complete')


def qp_result(rows, target_qp, excluded_reason=''):
    """Replace only one measured target tuple; the other three are always anchor.

    This does not turn historical imputation into a measured target or modify the
    original whole-experiment curve. Every reference point must be valid.
    """
    if sorted(r['qp'] for r in rows) != list(QPS) or target_qp not in QPS:
        raise ValueError('QP analysis requires exactly one row per configured QP')
    rows = sorted(rows, key=lambda r: r['qp'])
    target = next(r for r in rows if r['qp'] == target_qp)
    result = dict(qp=target_qp, target_status=target['status'],
                  target_record_status=target.get('test_record_status', ''),
                  **dict.fromkeys(BD, ''), calculation_error='', max_vba_gap_pp='')
    for c in 'yuv':
        result[f'{c}_overlap_low_db'] = result[f'{c}_overlap_high_db'] = ''
    if excluded_reason or target['status'] == 'excluded_unreliable':
        return dict(result, status='excluded_unreliable',
                    calculation_error=excluded_reason or 'Unreliable target excluded')
    if any(r['anchor_record_status'] != 'pass' for r in rows):
        return dict(result, status='invalid_anchor', calculation_error='A reference point is not pass')
    try:
        for c in 'yuv':
            anchor = [(r[f'anchor_psnr_{c}_db'], r['anchor_rate_kbps']) for r in rows]
            bd_rate(anchor, anchor)  # Check all four anchor tuples even if target is missing.
    except (AssertionError, ValueError, ZeroDivisionError, TypeError) as error:
        return dict(result, status='invalid_anchor',
                    calculation_error=str(error) or 'Invalid four-point anchor')
    if target['status'] in ('missing', 'anchor_imputed'):
        return dict(result, status=target['status'],
                    calculation_error='Target has no reliable measured experiment tuple')
    if target['status'] != 'measured' or target.get('test_record_status') != 'pass':
        return dict(result, status='invalid_target', calculation_error='Target is not a passing measured point')
    vals, bounds, gap = [], {}, 0.0
    try:
        for c in 'yuv':
            anchor = [(r[f'anchor_psnr_{c}_db'], r['anchor_rate_kbps']) for r in rows]
            mixed = [(r[f'{"test" if r["qp"] == target_qp else "anchor"}_psnr_{c}_db'],
                      r[f'{"test" if r["qp"] == target_qp else "anchor"}_rate_kbps']) for r in rows]
            value, low, high = bd_rate(anchor, mixed)
            gap = max(gap, abs(value - workbook_bdrate(anchor, mixed)))
            vals.append(value)
            bounds.update({f'{c}_overlap_low_db': low, f'{c}_overlap_high_db': high})
    except (AssertionError, ValueError, ZeroDivisionError, TypeError) as error:
        return dict(result, status='invalid',
                    calculation_error=str(error) or 'Invalid mixed monotonic/overlap curve')
    if gap > 1e-8:
        raise ValueError(f'QP workbook formula cross-check failed: {gap}')
    vals.append((6 * vals[0] + vals[1] + vals[2]) / 8)
    return dict(result, status='calculated', **dict(zip(BD, vals)), **bounds, max_vba_gap_pp=gap)


def build_qp_analysis(specs, points):
    """Build only catalog-selected rounds, keeping original result rows untouched."""
    selected_specs = [s for s in specs if s.get('qp_analysis')]
    qp_rows, summaries = [], []
    meta_keys = ('round', 'experiment', 'mode', 'configuration', 'sequence', 'class_name')
    for spec in selected_specs:
        groups = {}
        for point in points:
            if point['experiment'] == spec['experiment']:
                groups.setdefault((point['configuration'], point['sequence']), []).append(point)
        for _, rows in sorted(groups.items(), key=lambda item: (item[0][0], item[1][0]['class_name'], item[0][1])):
            by_qp = {r['qp']: r for r in rows}
            source_map = json.dumps([dict(qp=r['qp'], file=r['anchor_file'], cell=r['anchor_cell'],
                                         record_status=r['anchor_record_status'])
                                     for r in sorted(rows, key=lambda r: r['qp'])],
                                    ensure_ascii=False, separators=(',', ':'))
            for qp in QPS:
                target = by_qp[qp]
                qp_rows.append(dict({k: target[k] for k in meta_keys},
                    **qp_result(rows, qp, spec.get('excluded_reason', '')),
                    source_file=target['source_file'], source_cell=target['source_cell'],
                    anchor_file=target['anchor_file'], anchor_sources=source_map,
                    construction='Target QP measured tuple; all other QPs use Current Reference'))
    for spec in selected_specs:
        for config in sorted({r['configuration'] for r in qp_rows if r['experiment'] == spec['experiment']}):
            pool = [r for r in qp_rows if r['experiment'] == spec['experiment'] and r['configuration'] == config]
            available = {r['class_name'] for r in pool}
            for group in ('B', 'C', 'D', 'E', 'CE', 'BC', 'BCE', 'CD'):
                if not set(group) <= available:
                    continue
                expected = sum(c in group for c in CLASSES.values())
                for qp in QPS:
                    rows = [r for r in pool if r['class_name'] in group and r['qp'] == qp]
                    valid = [r for r in rows if r['status'] == 'calculated']
                    summaries.append(dict(round=spec['round'], experiment=spec['experiment'], configuration=config,
                        group=group, qp=qp, expected_sequences=expected, recorded_sequences=len(rows),
                        valid_sequences=len(valid), valid_sequence_names=';'.join(r['sequence'] for r in valid),
                        scope_status='excluded_unreliable' if spec.get('excluded_reason') else (
                            'full' if len(valid) == expected else 'available_subset'),
                        **{c: statistics.mean(r[c] for r in valid) if valid else '' for c in BD},
                        unavailable_sequences=';'.join(f'{r["sequence"]}:{r["status"]}' for r in rows
                                                       if r['status'] != 'calculated')))
    return qp_rows, summaries


def csv_text(rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def build(root):
    anchor_name = 'scripts/JVET-hhi.xlsm'
    hashes, csv_checks = {}, []

    def remember(path):
        rel = path.relative_to(root).as_posix()
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    remember(root / anchor_name)
    anchor, anchor_locations, anchor_status = read_sheet(root / anchor_name, 'Reference')
    all_points, sequences = [], []
    specs = catalog(root)
    for spec in specs:
        path = root / spec['path']
        remember(path)
        primary_csv = spec.get('source_format') == 'csv'
        if primary_csv:
            actual, locations, test_status = read_primary_csv(path)
            # CSV exports have no embedded Reference. Use only the declared
            # Current workbook, and do not claim an independent reference check.
            reference, reference_status = anchor, anchor_status
        else:
            actual, locations, test_status = read_sheet(path, 'Test')
            reference, _, reference_status = read_sheet(path, 'Reference')
        scope = {(s, 'lb') for s, cls in CLASSES.items() if cls in spec['expected_lb']}
        for key in actual:
            if test_status[key] != 'pass':
                raise ValueError(f'Non-pass numeric Test point: {path}:{key}')
            seq, qp, config = KEY.fullmatch(key).groups()
            if seq not in CLASSES or int(qp) not in QPS:
                raise ValueError(f'Unregistered sequence/QP: {spec["experiment"]}:{key}')
            scope.add((seq, config))
        if spec['round'] == 'fixed':
            scope.update((s, 'ra') for s, cls in CLASSES.items() if cls in 'CD')
        # Check any supplied flat CSV against the governing workbook. Duplicated
        # identical exports are allowed, but conflicting RD tuples stop publication.
        checked = set()
        for cp in csv_sources(spec, path):
            count, seen = 0, set()
            with cp.open(encoding='utf-8-sig', newline='') as f:
                for row in csv.reader(f):
                    if not row or not KEY.fullmatch(row[0]) or not any(v.strip() for v in row[1:5]):
                        continue
                    if row[0] in seen:
                        raise ValueError(f'Duplicate CSV row: {cp}:{row[0]}')
                    seen.add(row[0])
                    if len(row) < 5 or [float(v) for v in row[1:5]] != actual.get(row[0]):
                        raise ValueError(f'CSV/workbook RD mismatch: {cp}:{row[0]}')
                    checked.add(row[0])
                    count += 1
            if count:
                remember(cp)
                csv_checks.append(dict(experiment=spec['experiment'], source=cp.relative_to(root).as_posix(), matched_points=count))
        for seq, config in sorted(scope, key=lambda s: (s[1], CLASSES[s[0]], s[0])):
            meta = {k: spec[k] for k in ('round', 'experiment', 'mode')}
            meta.update(configuration=config.upper(), sequence=seq, class_name=CLASSES[seq])
            raw = []
            for qp in QPS:
                key = f'{seq}.Q{qp}.ecm.{config}'
                if key not in anchor or reference.get(key) != anchor[key] or reference_status.get(key) != anchor_status[key]:
                    raise ValueError(f'Missing/non-Current Reference: {path}:{key}')
                test, status = point_values(spec['experiment'], config, seq, qp, actual.get(key), anchor[key])
                if status == 'measured' and spec.get('excluded_reason'):
                    status = 'excluded_unreliable'
                raw.append(dict(meta, qp=qp, **dict(zip(('anchor_' + k for k in METRICS), anchor[key])),
                                **dict(zip(('test_' + k for k in METRICS), test)), status=status,
                                source_file=spec['path'], source_cell=locations.get(key, ''),
                                anchor_file=anchor_name, anchor_cell=anchor_locations[key],
                                anchor_record_status=anchor_status[key], test_record_status=test_status.get(key, ''),
                                value_source='Current Reference' if status == 'anchor_imputed' else (
                                    ('CSV' if primary_csv else 'Test') if status in ('measured', 'excluded_unreliable') else ''),
                                csv_rd_checked=key in checked if status == 'measured' else False))
            all_points.extend(raw)
            sequences.append(dict(meta, **sequence_result(raw, spec.get('excluded_reason', ''))))
    # Aggregate only the declared class set. An incomplete curve yields an
    # explicitly labelled available-subset mean, never a full-class average.
    summaries = []
    for spec in specs:
        for config in sorted({r['configuration'] for r in sequences if r['experiment'] == spec['experiment']}):
            pool = [r for r in sequences if r['experiment'] == spec['experiment'] and r['configuration'] == config]
            available = {r['class_name'] for r in pool}
            for group in ('B', 'C', 'D', 'E', 'CE', 'BC', 'BCE', 'CD'):
                if not set(group) <= available:
                    continue
                selected = [r for r in pool if r['class_name'] in group]
                valid = [r for r in selected if r['status'] in ('complete', 'imputed')]
                expected = sum(c in group for c in CLASSES.values())
                summaries.append(dict(round=spec['round'], experiment=spec['experiment'], configuration=config,
                    group=group, expected_sequences=expected, recorded_sequences=len(selected), valid_sequences=len(valid),
                    measured_points=sum(r['measured_points'] for r in selected),
                    imputed_points=sum(r['imputed_points'] for r in selected),
                    missing_points=sum(r['missing_points'] for r in selected),
                    scope_status='excluded_unreliable' if spec.get('excluded_reason') else (
                        'full' if len(valid) == expected else 'available_subset'),
                    **{c: statistics.mean(r[c] for r in valid) if valid else '' for c in BD}))
    for rel, digest in hashes.items():
        if hashlib.sha256((root / rel).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Input changed during extraction: {rel}')
    audit = dict(method='PCHIP per component, then (6Y+U+V)/8; equal sequence means',
                 experiments=len(specs), sequence_records=len(sequences), point_records=len(all_points),
                 point_status=dict(Counter(r['status'] for r in all_points)),
                 sequence_status=dict(Counter(r['status'] for r in sequences)),
                 invalid_anchor_points=[dict(experiment=r['experiment'], configuration=r['configuration'],
                     sequence=r['sequence'], qp=r['qp'], record_status=r['anchor_record_status'])
                     for r in all_points if r['anchor_record_status'] != 'pass'],
                 max_vba_gap_pp=max((r['max_vba_gap_pp'] for r in sequences if r['max_vba_gap_pp'] != ''), default=0.0),
                 sources_unchanged=True, remote_build_config_frames_decode_hash_verified=False,
                 sources=[dict(path=k, sha256=v) for k, v in sorted(hashes.items())], csv_checks=csv_checks,
                 primary_csv_sources=[dict(experiment=s['experiment'], source=s['path'],
                     numbering_revision=s['numbering_revision'], independent_reference_crosscheck=False,
                     excluded_reason=s.get('excluded_reason', '')) for s in specs if s.get('source_format') == 'csv'])
    return specs, all_points, sequences, summaries, audit


def fmt(value, digits=6, signed=False):
    if value == '':
        return '—'
    return format(value, f'{"+" if signed else ""}.{digits}f')


def markdown_table(headers, rows):
    return ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |',
            *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows], '']


def qp_markdown(name, config, qp_rows, qp_summaries):
    """QP column labels stay simple; unavailable numeric cells remain blank."""
    rows = [r for r in qp_rows if r['experiment'] == name and r['configuration'] == config]
    if not rows:
        return []
    selected = [r for r in qp_summaries if r['experiment'] == name and r['configuration'] == config]
    lines = [f'### {config}：QP 分析（%）', '',
             '每列仅将该QP的完整实验RD点替换到Current四点曲线，其余三个点均为Current；'
             'Y/U/V分别PCHIP后6:1:1加权，不将四列相加解释为整体BD-rate。',
             '缺失、历史anchor补点、用户排除或无效参考不计算，对应数值单元格留空。'
             '各QP按有效序列等权；有效数不足时为可用子集，具体集合与来源见QP CSV。', '']
    cells = []
    for group in dict.fromkeys(r['group'] for r in selected):
        by_qp = {r['qp']: r for r in selected if r['group'] == group}
        for metric, label in zip(BD, ('Y', 'U', 'V', '6:1:1')):
            cells.append([group, label, *[fmt(by_qp[q][metric], signed=True)
                                         if by_qp[q][metric] != '' else '' for q in QPS]])
        cells.append([group, '有效/应有序列数', *[f'{by_qp[q]["valid_sequences"]}/{by_qp[q]["expected_sequences"]}'
                                                for q in QPS]])
    lines += markdown_table(['范围', '分量', *[f'QP{q}' for q in QPS]], cells)
    cells = []
    for sequence in dict.fromkeys(r['sequence'] for r in rows):
        by_qp = {r['qp']: r for r in rows if r['sequence'] == sequence}
        for metric, label in zip(BD, ('Y', 'U', 'V', '6:1:1')):
            cells.append([sequence, label, *[fmt(by_qp[q][metric], signed=True)
                                            if by_qp[q][metric] != '' else '' for q in QPS]])
        cells.append([sequence, '状态', *[QP_STATUS[by_qp[q]['status']] for q in QPS]])
    lines += markdown_table(['序列', '分量', *[f'QP{q}' for q in QPS]], cells)
    return lines


def documents(specs, points, sequences, summaries, audit, updated):
    qp_rows, qp_summaries = build_qp_analysis(specs, points)
    if qp_rows:
        audit = dict(audit, qp_analysis=dict(
            rounds=[r for r in QP_ANALYSIS_ROUNDS if any(s['round'] == r and s.get('qp_analysis') for s in specs)],
            experiments=sum(bool(s.get('qp_analysis')) for s in specs),
            sequence_qp_records=len(qp_rows), group_qp_records=len(qp_summaries),
            status=dict(Counter(r['status'] for r in qp_rows)),
            method='Replace target measured RD tuple only; other three QPs use Current; component PCHIP then 6:1:1',
            target_imputed_is_not_measured=True,
            max_vba_gap_pp=max((r['max_vba_gap_pp'] for r in qp_rows if r['max_vba_gap_pp'] != ''), default=0.0)))
    files = {'rd_points.csv': csv_text(points), 'sequence_bdrate.csv': csv_text(sequences),
             'group_summary.csv': csv_text(summaries),
             'sources.json': json.dumps(dict(updated=updated, **audit), indent=2, ensure_ascii=False) + '\n'}
    if qp_rows:
        files.update({'qp_bdrate.csv': csv_text(qp_rows), 'qp_group_summary.csv': csv_text(qp_summaries)})
    index = ['# 实验结果明细', '', f'更新时间：{updated}。仅数据登记，不含实验分析。', '',
             '[返回总结果台账](../TS_Predictor_Results_Ledger.md)', '',
             '每个实验按配置、序列列出 QP22/27/32/37 的总码率（kbps）、Y/U/V PSNR（dB），',
             '并并列 Current 参考点；每条序列单独列出 Y/U/V BD-rate 及 6:1:1 加权 BD-rate（%）。',
             '整体 BD-rate 使用完整实验四点曲线。QP分析每列只替换对应实验点，其余三个点使用Current。'
             '两者分开登记，QP列不可相加还原整体BD-rate；负数为节省，不先加权PSNR。', '',
             'CSV 的空字段和 Markdown 的“—”均为缺失/不可计算，不是零。补点逐点标记且保留原工作簿定位。',
             '各组的 incomplete 整体实验曲线不计算整体 BD-rate；组级可用子集均值明确标记，不冒充完整 CE/BCE。',
             '若参考点状态不是 pass，保留其原始数值和状态，但对应序列不计算 BD-rate。',
             '用户明确排除的结果标记 excluded_unreliable，原数值留存但不参与任何 BD-rate 或效果均值。',
             '逐序列/类别 CSV 的 measured_points 为收到的数值点数，包含该类排除点；是否纳入以 status/scope_status 为准。',
             'CSV 主来源按 catalog 精确指定文件，行号保留为 CSV!B行:E行；不会据此声称存在独立的工作簿 Reference 核对。',
             '这里只核验表内数值、指定 Current Reference 和可用配套 CSV；不认证服务器宏、帧范围或解码 hash。', '',
             '## 查询文件', '',
             '- [逐 QP 数据 CSV](rd_points.csv)：含实验、配置、序列、QP、两组 RD 值、来源单元格和补点状态。',
             '- [逐序列 BD-rate CSV](sequence_bdrate.csv)：含分量、加权 BD、实测/补点/缺失数量及积分区间。',
             '- [类别汇总 CSV](group_summary.csv)：按序列等权，含有效序列数及完整/子集标记。',
             *(['- [QP 分析 CSV](qp_bdrate.csv)：逐实验/配置/序列/QP的分量及6:1:1 BD-rate、状态、积分区间与来源。',
                '- [QP 类别汇总 CSV](qp_group_summary.csv)：每个QP单独统计有效序列、集合与均值；缺点不补零。'] if qp_rows else []),
             '- [来源与核验记录](sources.json)：源文件 SHA256、配套 CSV 核对及 VBA 数值交叉检查。', '',
             '## 按实验轮次', '']
    links = []
    for group in dict.fromkeys(s['round'] for s in specs):
        gs = [s for s in specs if s['round'] == group]
        lines = [f'# {group.upper()} 逐序列结果明细', '', f'更新时间：{updated}。基线：Current。', '',
                 '[明细索引与计算口径](README.md) · [总结果台账](../TS_Predictor_Results_Ledger.md)', '']
        for spec in gs:
            lines.append(f'- [{spec["experiment"]}](#{spec["experiment"].lower()})')
        lines.append('')
        for spec in gs:
            name = spec['experiment']
            source_description = (f'模式：`{spec["mode"]}`。源表：`{spec["path"]}`，Test；参考为 Current Reference。'
                                  if spec.get('source_format') != 'csv' else
                                  f'模式：`{spec["mode"]}`。编号版本：`{spec["numbering_revision"]}`。'
                                  f'原始 CSV：`{spec["path"]}`；参考为 `scripts/JVET-hhi.xlsm` 的 Current Reference。'
                                  'CSV 不含独立参考曲线；原始行号和文件 SHA256 见派生 CSV / sources.json。')
            lines += [f'## {name}', '', source_description, '']
            if spec.get('excluded_reason'):
                lines += [spec['excluded_reason'] + ' 下表计数仅表示已收到原始点，不表示可用实测。', '']
            configs = sorted({r['configuration'] for r in sequences if r['experiment'] == name})
            for config in configs:
                seqs = [r for r in sequences if r['experiment'] == name and r['configuration'] == config]
                lines += [f'### {config}：逐序列 BD-rate（%）', '']
                lines += markdown_table(['序列', 'Class', 'Y', 'U', 'V', '6:1:1',
                    '原始点/补点/缺失' if spec.get('excluded_reason') else '实测/补点/缺失', '状态'],
                    [[f'[{r["sequence"]}](#{name.lower()}-{config.lower()}-{r["sequence"].lower()})',
                      r['class_name'], *[fmt(r[k], signed=True) for k in BD],
                      f'{r["measured_points"]}/{r["imputed_points"]}/{r["missing_points"]}', STATUS[r['status']]] for r in seqs])
                lines += qp_markdown(name, config, qp_rows, qp_summaries)
                for seq in seqs:
                    lines += [f'<a id="{name.lower()}-{config.lower()}-{seq["sequence"].lower()}"></a>', '',
                              f'#### {config} / {seq["sequence"]}', '']
                    rr = [r for r in points if r['experiment'] == name and r['configuration'] == config and r['sequence'] == seq['sequence']]
                    cells = []
                    for r in rr:
                        for kind, label in (('anchor', 'Current'), ('test', name)):
                            cells.append([label, r['qp'], *[fmt(r[kind + '_' + k], 4) for k in METRICS],
                                          ('参考' if r['anchor_record_status'] == 'pass' else '参考：' + r['anchor_record_status'])
                                          if kind == 'anchor' else STATUS[r['status']]])
                    lines += markdown_table(['版本', 'QP', '码率 kbps', 'Y PSNR dB', 'U PSNR dB', 'V PSNR dB', '状态'], cells)
        files[group + '.md'] = '\n'.join(lines).rstrip() + '\n'
        pp = [r for r in points if r['round'] == group]
        links.append([f'[{group.upper()}]({group}.md)', len(gs), sum(r['status'] == 'measured' for r in pp),
                      sum(r['status'] == 'anchor_imputed' for r in pp), sum(r['status'] == 'missing' for r in pp)])
    index += markdown_table(['轮次', '方法数', '实测点', 'anchor 补点', '缺失点'], links)
    excluded_counts = Counter(r['experiment'] for r in points if r['status'] == 'excluded_unreliable')
    if excluded_counts:
        index += ['另保留用户排除的原始数值点（不计入上表实测点）：' +
                  '，'.join(f'{name}：{count} 点' for name, count in sorted(excluded_counts.items())) + '。', '']
    if qp_rows:
        index += ['QP分析当前登记：' + '、'.join(r.upper() for r in QP_ANALYSIS_ROUNDS
                    if any(s['round'] == r and s.get('qp_analysis') for s in specs)) + '。'
                  '其目标必须为可靠实测；历史anchor补点目标留空，原整体曲线的补点与完整性状态不变。',
                  'QP分析Markdown的空白数值栏与CSV空字段均表示不可计算，原因列保留；不代表0%。', '']
    index += ['## 维护与复现', '', '在仓库根目录运行（只读源表，生成本目录派生文件）：', '',
              '```bash', 'python3 scripts/ts_results_ledger.py',
              f'python3 scripts/ts_results_ledger.py --date {updated} --check', '```', '',
              '新增实验在脚本 catalog 中登记身份和源表路径；历史补点白名单不自动扩展。',
              '实际数值出现后优先使用实际值。`--check` 只比对当前输入生成的内容与已登记文件，不写文件。',
              '旧汇总的补点替换等变更保留在总结果台账中；源工作簿、CSV 和外部原稿不改写。', '']
    files['README.md'] = '\n'.join(index)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path, default=Path('docs/experiments/results'))
    parser.add_argument('--date', default=date.today().isoformat())
    parser.add_argument('--check', action='store_true', help='Check registered outputs without writes')
    args = parser.parse_args()
    date.fromisoformat(args.date)
    root = args.root.resolve()
    out = (root / args.out).resolve()
    if not any(out.is_relative_to(root / base) for base in ('docs/experiments/results', 'runs')):
        parser.error('--out must be within docs/experiments/results or runs')
    self_test()
    specs, points, sequences, summaries, audit = build(root)
    files = documents(specs, points, sequences, summaries, audit, args.date)
    if args.check:
        changed = [name for name, content in files.items() if not (out / name).exists() or (out / name).read_text(encoding='utf-8') != content]
        if changed:
            parser.exit(1, f'Ledger differs: {changed}\n')
    else:
        out.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (out / name).write_text(content, encoding='utf-8')
    print(f'{len(specs)} experiments; {len(sequences)} sequence records; {len(points)} QP records; {audit["point_status"]}')
    print(f'VBA cross-check maximum difference: {audit["max_vba_gap_pp"]:.3g} percentage points; inputs unchanged.')
    print(('Checked: ' if args.check else 'Generated: ') + str(out))


if __name__ == '__main__':
    main()
