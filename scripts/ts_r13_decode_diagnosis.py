#!/usr/bin/env python3
"""Read-only R13 .bin replay. Validate all decoded MD5s; never re-encode.

run accepts existing batch_test.py .done.json markers. Original video is used
only by optional diagnostic SSE measurement, not by normal reconstruction.
compare pairs stable block geometry keys, explicitly retaining unpaired rows.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
from collections import Counter

from ts_r13_log_diagnosis import DECODE, HASH, parse_log


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def records(path):
    result = []
    headers = {}
    for number, line in enumerate(Path(path).read_text(errors='replace').splitlines(), 1):
        if line.startswith('TS_R13_DEC {'):
            row = json.loads(line[len('TS_R13_DEC '):])
            if 'truncated' in row.get('kind', '').lower() or row.get('truncated'):
                raise ValueError(f'Truncated diagnostic: {path}:{number}')
            result.append({**row, 'log_line': number})
        elif line.startswith(('TS_R13_DEC_FRAME', 'TS_R13_DEC_TILE')):
            tag, values = line.split(' ', 1)
            values = next(csv.reader([values]))
            if tag.endswith('_HEADER'):
                headers[tag.removesuffix('_HEADER')] = values
                continue
            if tag not in headers or len(values) != len(headers[tag]):
                raise ValueError(f'Missing or mismatched CSV schema {path}:{number}')
            row = dict(zip(headers[tag], values))
            row = {k: (int(v) if v.lstrip('-').isdigit() else v) for k, v in row.items()}
            result.append({'kind': tag.removeprefix('TS_R13_DEC_').lower(), **row, 'log_line': number})
    return result


def validate_stages(rows):
    frames = {}
    for r in rows:
        if r['kind'] == 'frame':
            key = (r['poc'], r['stage'], r['component'])
            if key in frames:
                raise ValueError(f'Duplicate stage frame: {key}')
            frames[key] = r
    tiles = {}
    for r in rows:
        if r['kind'] == 'tile':
            tiles.setdefault((r['poc'], r['stage'], r['component']), []).append(r)
    for key, f in frames.items():
        grid = tiles.get(key, [])
        if sum(t['samples'] for t in grid) != f['samples']:
            raise ValueError(f'Incomplete stage tile population: {key}')
        if len({(t['x'], t['y']) for t in grid}) != len(grid):
            raise ValueError(f'Duplicate stage tiles: {key}')
        if f['has_original'] and sum(t['sse'] for t in grid) != f['sse']:
            raise ValueError(f'Stage tile SSE is not conserved: {key}')
    return len(frames)


def validate_decode(path, expected):
    actual = {}
    for line in Path(path).read_text(errors='replace').splitlines():
        match = DECODE.match(line)
        if not match:
            continue
        poc, digest = int(match[1]), HASH.search(line)
        if poc in actual or digest is None or digest[4] != 'OK':
            raise ValueError(f'Missing, duplicate or failed decode MD5: {path}: POC {poc}')
        actual[poc] = digest.groups()[:3]
    if actual != expected:
        raise ValueError(f'Decoder MD5/population differs from encoded source: {path}')
    return len(actual)


def run(args):
    done = json.loads(args.done.read_text())
    result = done['result']
    if result['status'] != 'ok' or result['encode_returncode'] or result['decode_returncode']:
        raise ValueError('Source marker is not an encode/decode success')
    frames, _ = parse_log(Path(result['encode_log']))
    expected = {poc: tuple(row[f'md5_{c}'] for c in 'yuv') for poc, row in frames.items()}
    if args.poc >= 0 and args.poc not in expected:
        raise ValueError('Requested POC not in bitstream')
    bitstream = Path(result['bitstream']).resolve()
    if bitstream.stat().st_size != done['bitstream_bytes']:
        raise ValueError('Source bitstream length changed')
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / 'case.json').exists():
        raise ValueError('Use a new output directory; existing completed case protected')
    env = {k: v for k, v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=done['fixed_predictor'], TS_R13_STATS='0', TS_R13_TRACE='0',
               TS_R13_DECODE_DIAG='1', TS_R13_DECODE_POC=str(args.poc),
               TS_R13_DECODE_MAX_POC=str(args.max_poc),
               TS_R13_DECODE_CCP=str(int(args.ccp)),
               TS_R13_DECODE_CTU=str(args.ctu), TS_R13_DECODE_LIMIT=str(args.limit))
    scope = done.get('r13_identity', {}).get('observation_env', {}).get('TS_R13_DIAG_SCOPE') or 'all'
    env['TS_R13_DIAG_SCOPE'] = scope
    original = None
    if args.original:
        if args.input_bits is None:
            raise ValueError('--original requires --input-bits')
        original = dict(path=str(args.original.resolve()), sha256=sha(args.original), input_bits=args.input_bits)
        env.update(TS_R13_DECODE_ORIGINAL=original['path'], TS_R13_DECODE_ORIGINAL_BITS=str(args.input_bits))
    command = [str(args.decoder.resolve()), '-b', str(bitstream), '-o', '', '-dph', '1']
    observer_env = {k:v for k,v in env.items() if k.startswith('TS_')}
    log = args.output / 'decode.log'
    with log.open('w') as stream:
        status = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
    if status:
        raise ValueError(f'Decode failed ({status}): {log}')
    count = validate_decode(log, expected)
    rows = records(log)
    if not rows:
        raise ValueError('No observer records: wrong binary or unsupported observer')
    stage_count = validate_stages(rows)
    summary = [r for r in rows if r['kind'] == 'syntax_summary']
    if len(summary) != 1 or summary[0]['rows'] != sum(r['kind'] in ('CU', 'TU', 'CTU') for r in rows):
        raise ValueError('Syntax observation incomplete or missing closing summary')
    off_count = None
    if args.verify_off:
        env['TS_R13_DECODE_DIAG'] = '0'
        off_log = args.output / 'decode_off.log'
        with off_log.open('w') as stream:
            off_status = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
        if off_status:
            raise ValueError('Observer-off decode failed')
        off_count = validate_decode(off_log, expected)
        if records(off_log):
            raise ValueError('Observer-off emitted diagnostic rows')
    source_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    patch = subprocess.check_output(['git', 'diff', '--', 'source'])
    (args.output / 'source.patch').write_bytes(patch)
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', 'source'], text=True).splitlines()
    data = dict(schema='R13-decoder-replay-v1', source_head=source_head,
                source_snapshot_scope='runtime worktree snapshot, not an attestation of all binary compilation inputs',
                source_patch_sha256=hashlib.sha256(patch).hexdigest(),
                untracked_source_sha256={p: sha(p) for p in untracked},
                source_done=str(args.done.resolve()), source_done_sha256=sha(args.done),
                sequence=done['sequence'], qp=done['QP'], mode=done['fixed_predictor'], scope=scope,
                bitstream=str(bitstream), bitstream_sha256=sha(bitstream),
                decoder=str(args.decoder.resolve()), decoder_sha256=sha(args.decoder),
                command=command, observer_env=observer_env,
                observer_off_env={**observer_env, 'TS_R13_DECODE_DIAG':'0'} if args.verify_off else None,
                original=original, returncode=status, checked_frames=count,
                observer_off_checked_frames=off_count, output_log_sha256=sha(log),
                conserved_stage_rows=stage_count,
                record_counts=dict(Counter(r['kind'] for r in rows)))
    (args.output / 'case.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(data['record_counts']))


def write_rows(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, keys, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


KEYS = {
    'CU': ('poc', 'ctu', 'channel', 'x', 'y', 'w', 'h'),
    'TU': ('poc', 'ctu', 'channel', 'component', 'cu_x', 'cu_y', 'cu_w', 'cu_h', 'x', 'y', 'w', 'h'),
    'CTU': ('poc', 'ctu', 'component', 'x', 'y', 'w', 'h'),
    'frame': ('poc', 'stage', 'component'),
    'tile': ('poc', 'stage', 'component', 'x', 'y'),
    'filter': ('poc', 'ctu', 'component'),
}
IGNORED = {'log_line', 'order', 'trajectory', 'tu_index'}


def compare_rows(left, right):
    differences, counts = [], {}
    for kind, fields in KEYS.items():
        paired = []
        for rows in (left, right):
            index = {}
            for row in rows:
                if row['kind'] != kind:
                    continue
                key = tuple(row[f] for f in fields)
                if key in index:
                    raise ValueError(f'Duplicate stable {kind} key: {key}')
                index[key] = row
            paired.append(index)
        l, r = paired
        count = Counter(reference=len(l), test=len(r))
        for key in sorted(l.keys() | r.keys()):
            a, b = l.get(key), r.get(key)
            status = 'paired' if a and b else 'reference_only' if a else 'test_only'
            changed = sorted(k for k in (a or {}).keys() | (b or {}).keys()
                             if k not in IGNORED and (a or {}).get(k) != (b or {}).get(k))
            count[status] += 1
            if status == 'paired' and not changed:
                count['equal'] += 1
                continue
            count['different'] += 1
            differences.append(dict(kind=kind, **dict(zip(fields, key)), status=status,
                                    changed_fields='|'.join(changed),
                                    reference_line=a.get('log_line') if a else None,
                                    test_line=b.get('log_line') if b else None,
                                    reference=json.dumps(a, sort_keys=True) if a else '',
                                    test=json.dumps(b, sort_keys=True) if b else ''))
        counts[kind] = dict(count)
    return differences, counts


def compare(args):
    left, right = records(args.reference), records(args.test)
    validate_stages(left)
    validate_stages(right)
    differences, counts = compare_rows(left, right)
    args.output.mkdir(parents=True, exist_ok=True)
    write_rows(args.output / 'differences.csv', differences)
    (args.output / 'comparison.json').write_text(json.dumps(dict(
        reference=str(args.reference), reference_sha256=sha(args.reference),
        test=str(args.test), test_sha256=sha(args.test), counts=counts), indent=2) + '\n')
    print(json.dumps(counts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('run')
    p.add_argument('--done', type=Path, required=True)
    p.add_argument('--decoder', type=Path, default=Path('build/ts-r14/bin/DecoderApp'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--poc', type=int, default=-1)
    p.add_argument('--max-poc', type=int, default=31)
    p.add_argument('--ctu', type=int, default=-1)
    p.add_argument('--limit', type=int, default=200000)
    p.add_argument('--original', type=Path)
    p.add_argument('--input-bits', type=int)
    p.add_argument('--verify-off', action='store_true')
    p.add_argument('--ccp', action='store_true')
    p = commands.add_parser('compare')
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--test', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    (run if args.command == 'run' else compare)(args)


if __name__ == '__main__':
    main()
