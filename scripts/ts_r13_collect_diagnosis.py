#!/usr/bin/env python3
"""Collect completed local R13 diagnostic runs into small, separate query tables.

Reads explicit case roots and their done markers. Does not launch encoders,
modify source workbooks, or compute BD-rate from short prefixes.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from ts_r13_diagnostic import KEYS, parse as parse_diagnostic
from ts_r13_frame_diagnosis import parse as parse_stages
from ts_r13_log_diagnosis import DECODE, HASH, parse_log, write_csv


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(roots, output):
    tables = defaultdict(list)
    sources = []
    seen = set()
    for root in roots:
        for marker in sorted(root.rglob('*.done.json')):
            marker = marker.resolve()
            if marker in seen:
                raise ValueError('Repeated case root or done marker')
            seen.add(marker)
            done = json.loads(marker.read_text())
            result = done['result']
            if (result['status'] != 'ok' or result['encode_status'] != 'ok'
                    or result['decode_status'] != 'ok'
                    or int(result['encode_returncode']) != 0 or int(result['decode_returncode']) != 0):
                raise ValueError('A diagnostic done marker is not a decoded success')
            log, decode = Path(result['encode_log']), Path(result['decode_log'])
            actual_bytes = Path(result['bitstream']).stat().st_size
            if actual_bytes != int(done['bitstream_bytes']) or actual_bytes != int(result['bitstream_bytes']):
                raise ValueError('Bitstream size differs from successful marker')
            frames, info = parse_log(log)
            checked = set()
            for line in decode.read_text(errors='replace').splitlines():
                match = DECODE.match(line)
                if not match:
                    continue
                poc = int(match[1])
                md5 = HASH.search(line)
                if poc in checked or poc not in frames or not md5 or md5[4] != 'OK':
                    raise ValueError('Invalid, duplicate or unpaired decoded frame')
                if md5.groups()[:3] != tuple(frames[poc][f'md5_{c}'] for c in 'yuv'):
                    raise ValueError('Encoder/decoder MD5 mismatch')
                checked.add(poc)
            if checked != set(frames) or len(frames) != int(result['frames']):
                raise ValueError('Decoded frame population differs from requested/encoded population')
            case = '/'.join(log.resolve().relative_to(root.resolve()).parts[:-3]) or done['fixed_predictor']
            label = dict(case_root=root.name, case=case, sequence=done['sequence'],
                         qp=done['QP'], mode=done['fixed_predictor'],
                         scope=info['r13_component_scope'], frame_count=len(frames))
            row = {**label, 'rate_kbps': info['summary']['rate_kbps'],
                   **{f'psnr_{c}_db': mean(f[f'psnr_{c}_db'] for f in frames.values()) for c in 'yuv'},
                   'coded_frame_bits': sum(f['bits'] for f in frames.values()),
                   'bitstream_bytes': Path(result['bitstream']).stat().st_size,
                   'bitstream_sha256': sha(Path(result['bitstream'])),
                   'decode_hash_checked_frames': len(checked), 'status': 'local_short_measured_not_BD',
                   'encode_log': str(log.relative_to(Path.cwd())), 'decode_log': str(decode.relative_to(Path.cwd()))}
            tables['local_runs'].append(row)
            tables['local_frames'].extend({**label, **f} for f in frames.values())
            text = log.read_text(errors='replace')
            if info['has_r13_diagnostic_scoring']:
                reports, scale = parse_diagnostic(text)
                stage = parse_stages(log)
                tables['local_stages'].extend({**label, **s} for s in stage['FRAME'].values())
                for table, group_keys in [('CG', ('component', 'bdpcm')),
                                          ('RDOQ', ('component', 'probe_mode', 'trial_cg_zero'))]:
                    groups = defaultdict(lambda: defaultdict(float))
                    for r in reports.get(table, []):
                        key = tuple(r[k] for k in group_keys)
                        for field, value in r.items():
                            if field not in KEYS[table]:
                                groups[key][field] += value
                    for key, totals in groups.items():
                        record = {**label, **dict(zip(group_keys, key)), **totals}
                        if table == 'CG':
                            record['population'] = 'final_selected_TS_CG_fixed_q_same_entry_context'
                            for field, value in totals.items():
                                if field.endswith('_fracbits'):
                                    record[field.replace('_fracbits', '_bits')] = value / scale
                        else:
                            record['population'] = 'TS_RDOQ_search_trials_including_discarded_TUs'
                        tables['local_writer' if table == 'CG' else 'local_rdoq'].append(record)
            sources.append({**label, 'command': done['command'],
                            'identity_lines': info['identity_lines'],
                            'fingerprint': done['fingerprint'],
                            'encode_log_sha256': sha(log), 'decode_log_sha256': sha(decode),
                            'marker_sha256': sha(marker), 'scope_changes_coding': info['changes_coding_ablation']})
    if not sources:
        raise ValueError('No completed diagnostic runs; existing output was not changed')
    for name in ('local_runs', 'local_frames', 'local_stages', 'local_writer', 'local_rdoq'):
        if not tables[name] and (output / (name + '.csv')).exists():
            raise ValueError(f'Refusing to leave a stale {name}.csv; use a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        write_csv(output / (name + '.csv'), rows)
    (output / 'local_sources.json').write_text(json.dumps(sources, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: len(v) for k, v in tables.items()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-root', required=True, type=Path, action='append')
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    collect(args.case_root, args.output_dir)


if __name__ == '__main__':
    main()
