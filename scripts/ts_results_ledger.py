#!/usr/bin/env python3
"""Export read-only workbook data to a queryable, results-only TS ledger.

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

KEY = re.compile(r'^(.+)\.Q(\d+)\.ecm\.(lb|ra|ai|lp)$')
METRICS = ('rate_kbps', 'psnr_y_db', 'psnr_u_db', 'psnr_v_db')
BD = ('bd_y_pct', 'bd_u_pct', 'bd_v_pct', 'bd_611_pct')
R9_MODES = ('r9_p10', 'r9_p12', 'r9_axis_sparse', 'r9_half_penalty',
            'r9_feature_penalty', 'r9_unit_risk', 'r9_protect_one', 'r9_joint_mapping',
            'r9_expert_integer', 'r9_expert_fractional', 'r9_quant_down',
            'r9_quant_down_up', 'r9_axis_feature')
STATUS = {'measured': '实测', 'anchor_imputed': 'anchor 补点',
          'missing': '缺失', 'complete': '完整实测',
          'imputed': '含补点', 'incomplete': '不完整，不计算', 'invalid': '无有效公共曲线',
          'invalid_anchor': '参考点未通过，不计算'}


def catalog(root):
    """Explicit experiment identities; never infer a mode from arbitrary uploads."""
    specs = []

    def add(group, experiment, mode, path, expected='CE'):
        specs.append(dict(round=group, experiment=experiment, mode=mode,
                          path=path, expected_lb=expected))

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
        add('r9', f'R9-{i}', mode, f'experiments/ts_predictor_r9/R9_{i}_JVET-hhi.xlsm')
    return specs


def imputation_allowed(experiment, config, seq, qp):
    # Frozen historical exceptions, NOT a general "fill missing QP22" rule.
    allowed = {
        'A1': {'PartyScene'}, 'A2': {'BQMall', 'PartyScene', 'FourPeople'},
        'A3': {'BQMall', 'PartyScene', 'FourPeople', 'Johnny', 'KristenAndSara'},
        'R2-4': {'PartyScene'}, 'R3-2': {'MarketPlace', 'BasketballDrive', 'BQTerrace'},
        'R8-23': {'PartyScene'}, 'R8-24': {'PartyScene'},
    }
    return config == 'lb' and qp == 22 and seq in allowed.get(experiment, ())


def csv_sources(spec, path):
    """Shared result folders contain other experiments: pair by exact ID."""
    if spec['round'] in ('r8', 'r9'):
        candidate = path.parent / (spec['experiment'].split('-')[1] + '.csv')
        return [candidate] if candidate.exists() else []
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


def point_values(experiment, config, seq, qp, actual, anchor):
    if actual is not None:
        return actual, 'measured'
    if imputation_allowed(experiment, config, seq, qp):
        return anchor[:], 'anchor_imputed'
    return [''] * 4, 'missing'


def sequence_result(rows):
    """A missing point never becomes zero BD-rate or a three-point fit."""
    if sorted(r['qp'] for r in rows) != list(QPS):
        raise ValueError('Expected one row for each of QP22/27/32/37')
    result = dict(measured_points=sum(r['status'] == 'measured' for r in rows),
                  imputed_points=sum(r['status'] == 'anchor_imputed' for r in rows),
                  missing_points=sum(r['status'] == 'missing' for r in rows),
                  **dict.fromkeys(BD, ''), calculation_error='')
    for c in 'yuv':
        result[f'{c}_overlap_low_db'] = result[f'{c}_overlap_high_db'] = ''
    result['max_vba_gap_pp'] = ''
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
                raw.append(dict(meta, qp=qp, **dict(zip(('anchor_' + k for k in METRICS), anchor[key])),
                                **dict(zip(('test_' + k for k in METRICS), test)), status=status,
                                source_file=spec['path'], source_cell=locations.get(key, ''),
                                anchor_file=anchor_name, anchor_cell=anchor_locations[key],
                                anchor_record_status=anchor_status[key], test_record_status=test_status.get(key, ''),
                                value_source='Current Reference' if status == 'anchor_imputed' else ('Test' if status == 'measured' else ''),
                                csv_rd_checked=key in checked if status == 'measured' else False))
            all_points.extend(raw)
            sequences.append(dict(meta, **sequence_result(raw)))
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
                    scope_status='full' if len(valid) == expected else 'available_subset',
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
                 max_vba_gap_pp=max(r['max_vba_gap_pp'] for r in sequences if r['max_vba_gap_pp'] != ''),
                 sources_unchanged=True, remote_build_config_frames_decode_hash_verified=False,
                 sources=[dict(path=k, sha256=v) for k, v in sorted(hashes.items())], csv_checks=csv_checks)
    return specs, all_points, sequences, summaries, audit


def fmt(value, digits=6, signed=False):
    if value == '':
        return '—'
    return format(value, f'{"+" if signed else ""}.{digits}f')


def markdown_table(headers, rows):
    return ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |',
            *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows], '']


def documents(specs, points, sequences, summaries, audit, updated):
    files = {'rd_points.csv': csv_text(points), 'sequence_bdrate.csv': csv_text(sequences),
             'group_summary.csv': csv_text(summaries),
             'sources.json': json.dumps(dict(updated=updated, **audit), indent=2, ensure_ascii=False) + '\n'}
    index = ['# 实验结果明细', '', f'更新时间：{updated}。仅数据登记，不含实验分析。', '',
             '[返回总结果台账](../TS_Predictor_Results_Ledger.md)', '',
             '每个实验按配置、序列列出 QP22/27/32/37 的总码率（kbps）、Y/U/V PSNR（dB），',
             '并并列 Current 参考点；每条序列单独列出 Y/U/V BD-rate 及 6:1:1 加权 BD-rate（%）。',
             'BD-rate 属于四点曲线，不是单个 QP 的指标。负数为节省；不先加权 PSNR。', '',
             'CSV 的空字段和 Markdown 的“—”均为缺失/不可计算，不是零。补点逐点标记且保留原工作簿定位。',
             '各组的 incomplete 曲线不计算 BD-rate；组级可用子集均值明确标记，不冒充完整 CE/BCE。',
             '若参考点状态不是 pass，保留其原始数值和状态，但对应序列不计算 BD-rate。',
             '这里只核验表内数值、Current Reference 和可用配套 CSV；不认证服务器宏、帧范围或解码 hash。', '',
             '## 查询文件', '',
             '- [逐 QP 数据 CSV](rd_points.csv)：含实验、配置、序列、QP、两组 RD 值、来源单元格和补点状态。',
             '- [逐序列 BD-rate CSV](sequence_bdrate.csv)：含分量、加权 BD、实测/补点/缺失数量及积分区间。',
             '- [类别汇总 CSV](group_summary.csv)：按序列等权，含有效序列数及完整/子集标记。',
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
            lines += [f'## {name}', '', f'模式：`{spec["mode"]}`。源表：`{spec["path"]}`，Test；参考为 Current Reference。', '']
            configs = sorted({r['configuration'] for r in sequences if r['experiment'] == name})
            for config in configs:
                seqs = [r for r in sequences if r['experiment'] == name and r['configuration'] == config]
                lines += [f'### {config}：逐序列 BD-rate（%）', '']
                lines += markdown_table(['序列', 'Class', 'Y', 'U', 'V', '6:1:1', '实测/补点/缺失', '状态'],
                    [[f'[{r["sequence"]}](#{name.lower()}-{config.lower()}-{r["sequence"].lower()})',
                      r['class_name'], *[fmt(r[k], signed=True) for k in BD],
                      f'{r["measured_points"]}/{r["imputed_points"]}/{r["missing_points"]}', STATUS[r['status']]] for r in seqs])
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
