#!/usr/bin/env python3
"""Replay an existing short encode with bounded search observation; require bit-exact.

This explicitly RUNS encoding. It neither changes algorithm/tool settings nor
computes BD-rate. Source marker parameters, source input, and frame count are reused.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from ts_r13_decode_diagnosis import sha, validate_decode
from ts_r13_log_diagnosis import parse_log


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--done', type=Path, required=True)
    p.add_argument('--encoder', type=Path, required=True)
    p.add_argument('--decoder', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--poc', type=int, default=16)
    p.add_argument('--ctu', type=int, required=True)
    p.add_argument('--limit', type=int, default=200000)
    p.add_argument('--pred-detail', action='store_true',
                   help='Only replay the fixed Johnny QP32 POC16 8x32 TS target; no full search trace')
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('New output directory required')
    done = json.loads(args.done.read_text())
    if done['result']['status'] != 'ok':
        raise ValueError('Source run was not successful')
    expected, info = parse_log(Path(done['result']['encode_log']))
    if args.poc not in expected:
        raise ValueError('Target POC outside source prefix')
    if args.pred_detail and (args.poc != 16 or args.ctu != 36 or done['sequence'] != 'Johnny'
                            or done['QP'] != 32 or done['fixed_predictor'] != 'r13_keep_hit_uniform'):
        raise ValueError('Predictor detail probe is restricted to the original Johnny32 EQ target')
    command = list(done['command'])
    command[0] = str(args.encoder.resolve())
    args.output.mkdir(parents=True)
    bitstream = (args.output / 'output.bin').resolve()
    command[command.index('-b') + 1] = str(bitstream)
    command[command.index('-o') + 1] = ''
    env = {k:v for k,v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=done['fixed_predictor'], TS_R13_STATS='0', TS_R13_TRACE='0',
               TS_R13_DIAG='0', TS_R13_SEARCH_TRACE='1', TS_R13_SEARCH_POC=str(args.poc),
               TS_R13_SEARCH_CTU=str(args.ctu), TS_R13_SEARCH_LIMIT=str(args.limit),
               TS_R13_DIAG_SCOPE=info['r13_component_scope'])
    if args.pred_detail:
        env.update(TS_R13_SEARCH_TRACE='0', TS_R13_PRED_DETAIL=str((args.output/'detail').resolve()))
    patch = subprocess.check_output(['git', 'diff', '--', 'source'])
    (args.output / 'source.patch').write_bytes(patch)
    new_sources = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', 'source'], text=True).splitlines()
    identity = dict(command=command, source_done=str(args.done.resolve()), source_done_sha256=sha(args.done),
                    source_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                    source_patch_sha256=hashlib.sha256(patch).hexdigest(),
                    untracked_source_sha256={s:sha(s) for s in new_sources},
                    encoder_sha256=sha(args.encoder), decoder_sha256=sha(args.decoder),
                    input_sha256=sha(done['result']['input']),
                    observer_env={k:v for k,v in env.items() if k.startswith('TS_')},
                    reference_bitstream_sha256=sha(done['result']['bitstream']))
    (args.output / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    start = time.monotonic()
    with (args.output / 'encode.log').open('w') as log:
        rc = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    identity.update(encode_returncode=rc, elapsed_seconds=time.monotonic()-start)
    if rc:
        raise ValueError(f'Encoding failed {rc}; logs preserved')
    actual, _ = parse_log(args.output / 'encode.log')
    if set(actual) != set(expected) or any(
            actual[poc][key] != expected[poc][key] for poc in actual
            for key in ('bits', 'psnr_y_db', 'psnr_u_db', 'psnr_v_db', 'md5_y', 'md5_u', 'md5_v')):
        raise ValueError('Encoder observation changed frame output')
    identity['bitstream_sha256'] = sha(bitstream)
    if identity['bitstream_sha256'] != identity['reference_bitstream_sha256']:
        raise ValueError('Encoder observation changed complete bitstream')
    events = []
    for line in (args.output / 'encode.log').read_text(errors='replace').splitlines():
        if line.startswith('TS_R13_SEARCH {'):
            events.append(json.loads(line[len('TS_R13_SEARCH '):]))
    if args.pred_detail:
        details = [line for line in (args.output/'encode.log').read_text().splitlines()
                   if line.startswith('TS_R13_PRED_DETAIL ')]
        if len(details) != 1 or 'sp_minus_eq_frac=90521 ' not in details[0]:
            raise ValueError('Missing, duplicate or changed predictor detail target')
        for suffix in ('coeff', 'candidates', 'bins', 'summary'):
            path = args.output/f'detail_{suffix}.csv'
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f'Missing detail table: {path}')
        identity['predictor_detail'] = details[0]
    elif not events or any(r['event'] == 'truncated' for r in events):
        raise ValueError('No search trace or truncated search trace')
    elif (events[0]['event'] != 'ctu_begin' or events[-1]['event'] != 'ctu_end'
            or events[-1].get('truncated') or any(
                r['poc'] != args.poc or r['ctu'] != args.ctu or r['seq'] != i + 1
                for i, r in enumerate(events))
            or sum(r['event'] == 'ctu_begin' for r in events) != 1
            or sum(r['event'] == 'ctu_end' for r in events) != 1):
        raise ValueError('Incomplete or misidentified target CTU search trace')
    decode = [str(args.decoder.resolve()), '-b', str(bitstream), '-o', '', '-dph', '1']
    with (args.output / 'decode.log').open('w') as log:
        rc = subprocess.run(decode, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    if rc:
        raise ValueError('Decode failed')
    count = validate_decode(args.output / 'decode.log', {
        poc: tuple(r[f'md5_{c}'] for c in 'yuv') for poc, r in expected.items()})
    identity.update(decode_command=decode, decode_returncode=rc, checked_frames=count,
                    bit_exact=True, trace_events=len(events), encode_log_sha256=sha(args.output/'encode.log'))
    (args.output / 'complete.json').write_text(json.dumps(identity, indent=2) + '\n')
    print(json.dumps(dict(bit_exact=True, checked_frames=count, trace_events=len(events))))


if __name__ == '__main__':
    main()
