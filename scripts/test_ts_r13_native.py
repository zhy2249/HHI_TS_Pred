#!/usr/bin/env python3
"""TU-local CABAC/RDOQ regression only; never starts EncoderApp/DecoderApp."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from ts_r13_activity import parse

MODES = {'current': 1, 'r2_risk': 10, 'r3_risk_guard': 13,
         'r6_reject_nopred': 26, 'r13_keep_hit_uniform': 98,
         'r13_keep_hit_spatial': 99}


def sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def identical(a, b):
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open('rb') as left, b.open('rb') as right:
        while True:
            chunk = left.read(1024 * 1024)
            if chunk != right.read(1024 * 1024):
                return False
            if not chunk:
                return True


def run(executable, baseline, out, runtime):
    policy = MODES[runtime]
    env = {key: value for key, value in os.environ.items() if not key.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=runtime, TS_R3_STATS='0', TS_R6_STATS='0',
               TS_R10_STATS='0', TS_R11_STATS='0', TS_R12_STATS='0')
    # Full binary records are compared byte-for-byte, then removed. Persistent
    # output consists of bounded fixture logs and small provenance reports.
    with tempfile.TemporaryDirectory(prefix=runtime + '_', dir=out) as temporary:
        temp = Path(temporary)

        def call(tag, options, program=executable):
            payload, bdpcm = temp / (tag + '.bin'), temp / (tag + '_bdpcm.bin')
            process = subprocess.run([str(program)],
                env={**env, **options, 'TS_R13_EXACT_PAYLOAD': str(payload),
                     'TS_R13_BDPCM_PAYLOAD': str(bdpcm)},
                text=True, capture_output=True, timeout=300)
            (out / (runtime + '_' + tag + '.log')).write_text(process.stdout + process.stderr)
            if process.returncode:
                raise RuntimeError(f'{runtime}/{tag}: {process.stdout[-1000:]} {process.stderr[-3000:]}')
            if 'PASS ' + runtime not in process.stdout or 'sequence_encode_decode=false' not in process.stdout:
                raise AssertionError('Missing native-test identity: ' + runtime)
            if not re.search(r'TS_R13_NATIVE_DIGEST \d+', process.stdout):
                raise AssertionError('Missing native payload digest')
            return process, payload, bdpcm

        quiet, original, bdpcm = call('off', {})
        syntax_line = next(line for line in quiet.stdout.splitlines()
                           if line.startswith('TS_R13_SYNTAX '))
        syntax_coverage = {key: int(value) for key, value in
                           re.findall(r'(\w+)=(\d+)', syntax_line)}
        quant_line = next(line for line in quiet.stdout.splitlines()
                          if line.startswith('TS_R13_QUANT '))
        quant_coverage = {key: int(value) for key, value in
                          re.findall(r'(\w+)=(\d+)', quant_line)}
        if any(line.startswith(('TS_R13_STATS', 'TS_R13_TRACE', 'TS_R13_DETAIL'))
               for line in quiet.stderr.splitlines()):
            raise AssertionError('R13 observation is not OFF by default')
        observed, observed_payload, observed_bdpcm = call('observed',
            dict(TS_R13_STATS='1', TS_R13_TRACE='1', TS_R13_DETAIL_LIMIT='7'))
        if quiet.stdout != observed.stdout or not identical(original, observed_payload):
            raise AssertionError('Observation changed syntax/q/budget/context payload: ' + runtime)
        if not identical(bdpcm, observed_bdpcm):
            raise AssertionError('Observation changed BDPCM')
        rows = parse(observed.stderr)
        if not rows or {row['shadow_mode'] for row in rows} != {1, 2}:
            raise AssertionError('Both same-H shadow modes must be reported')
        if {row['trajectory_policy'] for row in rows} != {policy}:
            raise AssertionError('Incorrect trajectory identity')
        for mode in (1, 2):
            population = [row for row in rows if row['shadow_mode'] == mode]
            if sum(row['tu_count'] for row in population) != syntax_coverage['TU']:
                raise AssertionError('Final Writer TU counted incorrectly')
            if sum(row['cg_count'] for row in population) != syntax_coverage['CG']:
                raise AssertionError('Final Writer CG counted incorrectly')
            if sum(row['coeff_count'] for row in population) != syntax_coverage['causal']:
                raise AssertionError('Final Writer coefficient counted incorrectly')
            for row in population:
                if row['n'] < 0:
                    if row['coeff_count']:
                        raise AssertionError('Totals rows must not duplicate coefficients')
                    continue
                if row['n'] < 3 and (row['valid_margin_count'] or row['scored_count']):
                    raise AssertionError('Sparse support incorrectly scored')
                if row['sparse_count'] + row['scored_count'] != row['coeff_count']:
                    raise AssertionError('Sparse/scored populations are not exhaustive')
                if row['bdpcm'] and row['actual_remap_position']:
                    raise AssertionError('BDPCM marked as actual remapping')
                if not row['cutoff'] and row['actual_remap_position']:
                    raise AssertionError('Bypass marked as actual remapping')
                if row['selected_current_equiv'] + row['selected_identity_not_current'] + row['selected_other'] != row['coeff_count']:
                    raise AssertionError('Selection populations are not disjoint')
        traces = [line for line in observed.stderr.splitlines() if line.startswith('TS_R13_TRACE ')]
        writer = [line.replace('role=W', 'role=X') for line in traces if 'role=W' in line]
        reader = [line.replace('role=R', 'role=X') for line in traces if 'role=R' in line]
        if len(writer) != 7 or writer != reader:
            raise AssertionError('Bounded Writer/Reader trace mismatch')
        if sum(line.startswith('TS_R13_DETAIL ') for line in observed.stderr.splitlines()) != 7:
            raise AssertionError('Detail output is missing or unbounded')
        result = dict(runtime=runtime, policy=policy, native_output=quiet.stdout.strip(),
                      payload_sha256=sha256(original), payload_bytes=original.stat().st_size,
                      bdpcm_sha256=sha256(bdpcm), observation_bitexact=True,
                      syntax_coverage=syntax_coverage, quant_coverage=quant_coverage,
                      stats_rows=len(rows), writer_reader_cg_trace_pairs=len(writer),
                      _bdpcm=bdpcm.read_bytes())
        if runtime == 'r13_keep_hit_uniform':
            trace_only, trace_payload, _ = call('trace_only',
                dict(TS_R13_TRACE='1', TS_R13_DETAIL_LIMIT='2'))
            if parse(trace_only.stderr) or not identical(original, trace_payload):
                raise AssertionError('Trace-only mode changed payload or enabled aggregate statistics')
            result['trace_only_bitexact'] = True
        if baseline and policy < 98:
            reference, reference_payload, _ = call('baseline', {}, baseline)
            if not identical(original, reference_payload):
                raise AssertionError('Legacy mode differs from baseline byte records: ' + runtime)
            result['baseline_byte_identical'] = True
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=Path('build/ts-r13/bin/TsR13NativeTest'))
    parser.add_argument('--baseline-exe', type=Path,
                        help='The SAME harness compiled with frozen pre-R13 sources')
    parser.add_argument('--baseline-revision', default='', help='Verified source revision of --baseline-exe')
    parser.add_argument('--out', type=Path, default=Path('runs/ts_r13_native'))
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1 or args.jobs > 8:
        parser.error('--jobs must be in [1,8]')
    if args.baseline_exe and not args.baseline_revision:
        parser.error('--baseline-revision is required with --baseline-exe')
    executable = args.exe.resolve()
    baseline = args.baseline_exe.resolve() if args.baseline_exe else None
    args.out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda runtime: run(executable, baseline, args.out, runtime), MODES))
    expected = results[0]['_bdpcm']
    if any(result['_bdpcm'] != expected for result in results):
        raise AssertionError('BDPCM fixtures changed between predictor policies')
    for result in results:
        del result['_bdpcm']
        result['bdpcm_cross_policy_byte_identical'] = True
    if len({result['payload_sha256'] for result in results[-2:]}) < 2:
        raise AssertionError('Uniform/spatial native fixtures have no activity difference')
    if any(result['payload_sha256'] == results[1]['payload_sha256'] for result in results[-2:]):
        raise AssertionError('New policy is identical to R2 in native fixtures')
    report = dict(revision='R13-KH-168-v1', sequence_encode_decode=False,
                  native_exe_sha256=sha256(executable),
                  harness_sha256=sha256(Path(__file__).with_name('ts_r13_native_test.cpp')),
                  baseline_revision=args.baseline_revision or None,
                  baseline_exe_sha256=sha256(baseline) if baseline else None,
                  baseline_status='checked' if baseline else 'NOT RUN', results=results)
    (args.out / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    for result in results:
        print(result['runtime'], 'PASS', 'observation bit-exact; BDPCM cross-policy bit-exact')
    print('Baseline legacy comparison:', report['baseline_status'])


if __name__ == '__main__':
    main()
