#!/usr/bin/env python3
"""Read-only frame diagnosis for paired Current/R13-2 encoder logs.

Combined encoder + repeated decoder logs are supported. A frame is counted as
encoded only when it has a bits/PSNR record. Per-QP BD-rate is read from the
registered ledger, never inferred from a single pair of frame sequences.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import struct


FRAME = re.compile(
    r'^POC\s+(\d+)\s+LId:\s*(\d+)\s+TId:\s*(\d+)\s*'
    r'\(\s*([^,]+),\s*([A-Z])-SLICE,\s*QP\s+(-?\d+)\s*\)\s*'
    r'(\d+)\s+bits\s+\[Y\s+([\d.]+)\s+dB\s+U\s+([\d.]+)\s+dB\s+V\s+([\d.]+)\s+dB\]')
DECODE = re.compile(r'^POC\s+(\d+).*?\[DT\s+([\d.]+)\]')
HASH = re.compile(r'\[MD5:([a-fA-F0-9]+),([a-fA-F0-9]+),([a-fA-F0-9]+)(?:,\(([^)]+)\))?\]')
EXACT = re.compile(r'\[xY\s+([a-fA-F0-9]+)\s+xU\s+([a-fA-F0-9]+)\s+xV\s+([a-fA-F0-9]+)\]')
SUMMARY = re.compile(r'^\s*(\d+)\s+a\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)')
CFG_PREFIX = ('TOOL CFG:', 'FAST TOOL CFG:', 'ENC TOOL CFG:', 'SEI TOOL CFG:')
DEFAULT_PAIRS = (('Johnny', 27), ('Johnny', 32), ('KristenAndSara', 32))
FIELDS = ('rate_kbps', 'psnr_y_db', 'psnr_u_db', 'psnr_v_db')


def csv_rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def exact_double(value):
    result = struct.unpack('>d', bytes.fromhex(value.zfill(16)))[0]
    if not math.isfinite(result):
        raise ValueError('Non-finite exact PSNR')
    return result


def parse_log(path):
    source = path.read_bytes()
    text = source.decode('utf-8', errors='replace')
    frames, decode_rows, summaries = {}, [], []
    cfg, identities, versions, elapsed = [], [], [], []
    for line_number, line in enumerate(text.splitlines(), 1):
        if line.startswith(CFG_PREFIX):
            cfg.append(line.rstrip())
        if line.startswith(('EXPERIMENT:', 'TS predictor default:', 'TS R13 revision=',
                            'TS R13 diagnosis=', 'TS R13 ablation=')):
            if line not in identities:
                identities.append(line)
        if 'Encoder Version' in line and line.strip() not in versions:
            versions.append(line.strip())
        m = re.search(r'Total Time:\s+([\d.]+)\s+sec\.\s+\[user\]\s+([\d.]+)\s+sec\.\s+\[elapsed\]', line)
        if m:
            elapsed.append(dict(user_seconds=float(m[1]), elapsed_seconds=float(m[2])))
        if (m := SUMMARY.match(line)):
            summaries.append(dict(frame_count=int(m[1]), **dict(zip(FIELDS, map(float, m.groups()[1:])))))
        if (m := FRAME.match(line)):
            poc = int(m[1])
            if poc in frames:
                raise ValueError(f'{path}:{line_number}: duplicate encoded POC {poc}')
            row = dict(poc=poc, layer_id=int(m[2]), temporal_id=int(m[3]), nal_type=m[4].strip(),
                       slice_type=m[5], actual_qp=int(m[6]), bits=int(m[7]), source_line=line_number)
            exact = EXACT.search(line)
            values = [exact_double(exact[i]) for i in (1, 2, 3)] if exact else list(map(float, m.groups()[7:10]))
            row.update({f'psnr_{c}_db': value for c, value in zip('yuv', values)})
            row['psnr_precision'] = 'hex_double' if exact else 'printed_decimal'
            dimensions = re.search(r'\[dpb wxh\s+(\d+)x(\d+)\]', line)
            row['width'] = int(dimensions[1]) if dimensions else ''
            row['height'] = int(dimensions[2]) if dimensions else ''
            encoded_time = re.search(r'\[ET\s+([\d.]+)\s*\]', line)
            row['encode_seconds_printed'] = float(encoded_time[1]) if encoded_time else ''
            md5 = HASH.search(line)
            row.update({f'md5_{c}': md5[i] if md5 else '' for i, c in enumerate('yuv', 1)})
            frames[poc] = row
        elif (m := DECODE.match(line)):
            md5 = HASH.search(line)
            decode_rows.append(dict(poc=int(m[1]), dt_seconds=float(m[2]),
                                    md5=md5.groups()[:3] if md5 else None,
                                    status=md5[4] if md5 else None))
    if not frames:
        raise ValueError(f'{path}: no encoded frames')
    if len(summaries) > 1:
        raise ValueError(f'{path}: multiple encoded summaries')
    summary = summaries[0] if summaries else None
    if summary and summary['frame_count'] != len(frames):
        raise ValueError(f'{path}: frame count differs from summary')
    gap = None
    if summary:
        gap = max(abs(statistics.mean(r[f'psnr_{c}_db'] for r in frames.values()) - summary[f'psnr_{c}_db']) for c in 'yuv')
        if gap > 0.000051:
            raise ValueError(f'{path}: printed average PSNR mismatch {gap}')
    decode_errors = []
    decode_counts = {poc: 0 for poc in frames}
    for row in decode_rows:
        p = row['poc']
        if p not in frames or row['status'] != 'OK':
            decode_errors.append(row)
            continue
        if row['md5'] != tuple(frames[p][f'md5_{c}'] for c in 'yuv'):
            decode_errors.append(row)
            continue
        decode_counts[p] += 1
    ablations = [line for line in identities if line.startswith('TS R13 ablation=')]
    scopes = {m[1] for line in ablations if (m := re.search(r'(?:^|; )scope=(all|luma|chroma)(?:;|$)', line))}
    if ablations and len(scopes) != 1:
        raise ValueError(f'{path}: missing or conflicting R13 ablation scope')
    identity = dict(path=str(path), sha256=hashlib.sha256(source).hexdigest(), frame_count=len(frames),
                    poc_min=min(frames), poc_max=max(frames), summary=summary,
                    printed_summary_max_psnr_gap_db=gap, encoder_versions=versions, identity_lines=identities,
                    tool_configuration_lines=cfg, encoder_times=elapsed,
                    decode_frame_records=len(decode_rows), decode_hash_errors=len(decode_errors),
                    min_decoder_passes_per_poc=min(decode_counts.values()),
                    max_decoder_passes_per_poc=max(decode_counts.values()),
                    has_predictor_statistics='TS_R13_STATS_HEADER' in text,
                    has_r13_diagnostic_scoring=any(line.startswith('TS R13 diagnosis=') for line in identities),
                    r13_component_scope=next(iter(scopes)) if scopes else 'all',
                    changes_coding_ablation=bool(ablations),
                    source_or_binary_hash_verified=False)
    return frames, identity


def compare_frames(reference, test, sequence, qp):
    if set(reference) != set(test):
        raise ValueError(f'{sequence} QP{qp}: unequal encoded POC sets')
    rows = []
    for p in sorted(reference):
        a, b = reference[p], test[p]
        row = dict(sequence=sequence, nominal_qp=qp, poc=p, slice_type=a['slice_type'],
                   temporal_id=a['temporal_id'], nal_type=a['nal_type'],
                   width=a['width'], height=a['height'],
                   actual_qp=a['actual_qp'], test_actual_qp=b['actual_qp'],
                   reference_bits=a['bits'], test_bits=b['bits'], delta_bits=b['bits']-a['bits'],
                   delta_bits_pct=100*(b['bits']/a['bits']-1) if a['bits'] else '',
                   frame_control_equal=int(all(a[k] == b[k] for k in ('actual_qp', 'slice_type', 'nal_type', 'temporal_id', 'layer_id', 'width', 'height'))))
        if (a['width'], a['height']) != (b['width'], b['height']):
            raise ValueError(f'{sequence} QP{qp} POC{p}: unequal frame dimensions')
        for c in 'yuv':
            row[f'reference_psnr_{c}_db'] = a[f'psnr_{c}_db']
            row[f'test_psnr_{c}_db'] = b[f'psnr_{c}_db']
            row[f'delta_psnr_{c}_db'] = b[f'psnr_{c}_db'] - a[f'psnr_{c}_db']
            row[f'mse_change_{c}_pct'] = 100 * math.expm1(-math.log(10) * row[f'delta_psnr_{c}_db'] / 10)
            row[f'md5_{c}_equal'] = int(a[f'md5_{c}'] == b[f'md5_{c}']) if a[f'md5_{c}'] and b[f'md5_{c}'] else ''
        rows.append(row)
    return rows


def summarize(rows, sequence, qp, label):
    if len({(r['width'], r['height']) for r in rows}) != 1:
        raise ValueError('Window MSE comparison requires constant frame dimensions')
    a = sum(r['reference_bits'] for r in rows)
    b = sum(r['test_bits'] for r in rows)
    out = dict(sequence=sequence, nominal_qp=qp, window=label, frame_count=len(rows),
               poc_min=min(r['poc'] for r in rows), poc_max=max(r['poc'] for r in rows),
               reference_bits=a, test_bits=b, delta_bits=b-a, delta_bits_pct=100*(b/a-1))
    for c in 'yuv':
        values = [r[f'delta_psnr_{c}_db'] for r in rows]
        out.update({f'mean_delta_psnr_{c}_db': statistics.mean(values),
                    f'min_delta_psnr_{c}_db': min(values), f'max_delta_psnr_{c}_db': max(values),
                    f'loss_frames_{c}': sum(v < -0.00005 for v in values),
                    f'md5_equal_frames_{c}': sum(r[f'md5_{c}_equal'] == 1 for r in rows)})
        # Equal-resolution, equal-peak paired frames: sum normalized MSE before
        # forming a ratio. Do not transform mean PSNR or average frame ratios.
        reference_mse = sum(10 ** (-r[f'reference_psnr_{c}_db'] / 10) for r in rows)
        test_mse = sum(10 ** (-r[f'test_psnr_{c}_db'] / 10) for r in rows)
        out[f'aggregate_mse_change_{c}_pct'] = 100 * (test_mse/reference_mse - 1)
    return out


def audit_ledger(identity, sequence, qp, role, points):
    if identity.get('changes_coding_ablation'):
        return dict(status='not_checked_component_ablation_not_formal_R13')
    matching = [r for r in points if r['experiment'] == 'R13-2' and r['configuration'] == 'LB'
                and r['sequence'] == sequence and int(r['qp']) == qp]
    if len(matching) != 1 or identity['summary'] is None:
        return dict(status='not_checked')
    prefix = 'anchor_' if role == 'reference' else 'test_'
    differences = {field: identity['summary'][field]-float(matching[0][prefix+field]) for field in FIELDS}
    return dict(status='match' if max(map(abs, differences.values())) < 0.000051 else 'mismatch',
                differences=differences, ledger_source=matching[0]['source_file'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=Path('experiments/ts_predictor_r13'))
    parser.add_argument('--ledger', type=Path, default=Path('docs/experiments/results/rd_points.csv'))
    parser.add_argument('--no-ledger-check', action='store_true', help='For short runs not covering the registered full sequence')
    parser.add_argument('--pair', action='append', nargs=4, metavar=('SEQUENCE', 'QP', 'REFERENCE_LOG', 'TEST_LOG'))
    parser.add_argument('--output-dir', type=Path, default=Path('runs/r13_diagnosis_20261024/log_audit'))
    args = parser.parse_args()
    pairs = [(s, int(q), Path(a), Path(b)) for s, q, a, b in args.pair] if args.pair else [
        (s, q, args.source_dir/f'{s}_{q}_base', args.source_dir/f'{s}_{q}_R13_2') for s, q in DEFAULT_PAIRS]
    points = [] if args.no_ledger_check else csv_rows(args.ledger)
    all_frames, pair_rows, windows, summaries, audit = [], [], [], [], []
    for sequence, qp, a_path, b_path in pairs:
        a, ai = parse_log(a_path)
        b, bi = parse_log(b_path)
        for role, frames, identity in (('reference', a, ai), ('test', b, bi)):
            all_frames.extend(dict(sequence=sequence, nominal_qp=qp, role=role, **row) for row in frames.values())
            identity['ledger_summary_check'] = (dict(status='not_checked_short_scope') if args.no_ledger_check
                                               else audit_ledger(identity, sequence, qp, role, points))
        rows = compare_frames(a, b, sequence, qp)
        pair_rows.extend(rows)
        summary = summarize(rows, sequence, qp, 'all')
        summary['reference_r13_component_scope'] = ai['r13_component_scope']
        summary['test_r13_component_scope'] = bi['r13_component_scope']
        summary['contains_coding_ablation'] = ai['changes_coding_ablation'] or bi['changes_coding_ablation']
        summary['tool_configuration_equal'] = ai['tool_configuration_lines'] == bi['tool_configuration_lines']
        summary['frame_control_mismatches'] = sum(not r['frame_control_equal'] for r in rows)
        summary['first_different_bits_poc'] = next((r['poc'] for r in rows if r['delta_bits']), '')
        for c in 'yuv':
            summary[f'first_different_md5_{c}_poc'] = next((r['poc'] for r in rows if r[f'md5_{c}_equal'] == 0), '')
        summaries.append(summary)
        intervals = [('poc0', 0, 0), ('poc1_8', 1, 8), ('poc9_16', 9, 16), ('poc17_32', 17, 32),
                     ('poc33_64', 33, 64), ('poc65_128', 65, 128), ('poc129_end', 129, max(a))]
        intervals += [(f'prefix_{end+1}', 0, end) for end in (8, 16, 32, 64, 128)]
        for label, low, high in intervals:
            selected = [r for r in rows if low <= r['poc'] <= high]
            if selected:
                windows.append(summarize(selected, sequence, qp, label))
        for actual in sorted({r['actual_qp'] for r in rows}):
            windows.append(summarize([r for r in rows if r['actual_qp'] == actual], sequence, qp, f'actual_qp_{actual}'))
        for slice_type in sorted({r['slice_type'] for r in rows}):
            windows.append(summarize([r for r in rows if r['slice_type'] == slice_type], sequence, qp, f'slice_{slice_type}'))
        for temporal_id in sorted({r['temporal_id'] for r in rows}):
            windows.append(summarize([r for r in rows if r['temporal_id'] == temporal_id], sequence, qp, f'temporal_id_{temporal_id}'))
        audit.append(dict(sequence=sequence, nominal_qp=qp, reference=ai, test=bi,
                          tool_configuration_equal=summary['tool_configuration_equal'],
                          frame_control_mismatches=summary['frame_control_mismatches']))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in [('frames', all_frames), ('pair_frames', pair_rows), ('windows', windows), ('summary', summaries)]:
        write_csv(args.output_dir/f'{name}.csv', rows)
    (args.output_dir/'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['# R13相关日志逐帧审计', '', '以下为原始日志配对，单位bits/%/dB；单QP日志不计算BD-rate。', '',
             '| 序列/QP | 帧数 | bits差% | ΔY | ΔU | ΔV | 工具配置相同 | R13 scope（参考/测试） |',
             '|---|---:|---:|---:|---:|---:|---|---|']
    for r in summaries:
        lines.append(f"| {r['sequence']} QP{r['nominal_qp']} | {r['frame_count']} | {r['delta_bits_pct']:+.6f} | "
                     + ' | '.join(f"{r[f'mean_delta_psnr_{c}_db']:+.6f}" for c in 'yuv')
                     + f" | {r['tool_configuration_equal']} | {r['reference_r13_component_scope']}/{r['test_r13_component_scope']} |")
    lines += ['', 'PSNR优先读取日志xY/xU/xV中的精确double；summary与台账比较使用打印值。',
              '编码POC仅按含bits/PSNR的行统计；重复解码POC不重复计入。',
              '工具配置行和POC控制参数相同不等于配置文件、输入或二进制身份完全认证。',
              '服务器耗时来自不同运行，不能直接作为复杂度比。',
              'luma/chroma scope会改变编解码行为，属于组件消融，不能记为正式R13；diagnosis观察本身不反馈决策。',
              'MSE变化先累加各帧10^(-PSNR/10)再取比，适用于相同峰值与固定尺寸；不是对平均PSNR取指数。',
              '逐帧差异包含参考帧反馈及模式搜索传播，不是同一TU/固定q反事实。',
              '短前缀的bits/PSNR差不代替300帧正式RD或BD-rate。', '']
    (args.output_dir/'summary.md').write_text('\n'.join(lines), encoding='utf-8')
    for item in audit:
        for role in ('reference', 'test'):
            source = item[role]
            if hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() != source['sha256']:
                raise ValueError(f"Input changed during analysis: {source['path']}")
    print(f'Wrote {len(pair_rows)} paired frames, {len(windows)} windows and {len(audit)} source audits to {args.output_dir}')


if __name__ == '__main__':
    main()
