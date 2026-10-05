#!/usr/bin/env python3
"""Compare R12 original/optimized synthetic TU bytes and TS-RDOQ q, not videos.

Both builds must use this same test harness, with EXACT_OPT=0 versus 1.
The optional microbenchmark includes fixture/reference-check overhead and is
NOT an EncoderApp timing experiment or an end-to-end encoding speed claim.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import statistics
import struct
import subprocess
import time

from ts_predictor_naming import R12_MODE_NUMBERS
from ts_r12_activity import parse

MODES = ['r10_integer_then_fractional', *R12_MODE_NUMBERS]
MAGIC = {'native': b'TSR12CABACv1\n', 'quant': b'TSR12QUANTv1\n'}


def environment(runtime):
    env = {k: v for k, v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=runtime, TS_R10_CACHE='0',
               TS_R10_STATS='0', TS_R11_STATS='0')
    return env


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def payload_summary(data, kind):
    """Validate explicit record boundaries before any equality assertion."""
    magic = MAGIC[kind]
    if not data.startswith(magic):
        raise AssertionError(f'{kind}: missing/version-mismatched payload header')
    offset = len(magic)

    def words(count):
        nonlocal offset
        if offset + count * 8 > len(data):
            raise AssertionError(f'{kind}: truncated payload record')
        values = struct.unpack_from('<' + 'Q' * count, data, offset)
        offset += count * 8
        return values

    count, = words(1)
    expected = 160 if kind == 'native' else 180
    if count != expected:
        raise AssertionError(f'{kind}: expected {expected} records, got {count}')
    content_bytes = 0
    for trial in range(count):
        if kind == 'native':
            index, width, height, comp, qp, bdpcm, rice, length = words(8)
            if not (1 <= rice <= 8 and bdpcm in (0, 1)):
                raise AssertionError('native: malformed syntax fixture metadata')
        else:
            index, width, height, comp, qp, coefficients, abs_sum = words(7)
            if coefficients != width * height:
                raise AssertionError('quant: coefficient count does not match TU')
            length = coefficients * 8
        if index != trial or comp not in (0, 1, 2) or not width or not height or qp > 63:
            raise AssertionError(f'{kind}: malformed fixture metadata')
        if offset + length > len(data):
            raise AssertionError(f'{kind}: truncated coefficient/CABAC payload')
        if kind == 'quant':
            q = struct.unpack_from('<' + 'q' * coefficients, data, offset)
            if sum(abs(v) for v in q) != abs_sum:
                raise AssertionError('quant: absSum differs from serialized final q')
        offset += length
        content_bytes += length
    if offset != len(data):
        raise AssertionError(f'{kind}: unexpected trailing bytes')
    return dict(records=count, content_bytes=content_bytes,
                framed_bytes=len(data), sha256=sha256(data))


def assert_bytes(a, b, label):
    # Compare complete serialized contents, not merely their hashes.
    if a == b:
        return
    offset = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    raise AssertionError(f'{label}: mismatch at byte {offset}; lengths {len(a)} and {len(b)}')


def check_traces(stderr, runtime):
    mode = R12_MODE_NUMBERS.get(runtime, 0)
    rows = parse(stderr, 85 + mode if mode else 73)
    if not rows or {row['mode'] for row in rows} != {mode}:
        raise AssertionError(f'{runtime}: missing/wrong observation mode')
    traces = [line for line in stderr.splitlines() if line.startswith('TS_R12_TRACE ')]
    index = 0
    while index < len(traces):
        if ' cg=0 ' not in traces[index]:
            raise AssertionError(f'{runtime}: missing trace TU boundary')
        end = index + 1
        while end < len(traces) and ' cg=0 ' not in traces[end]:
            end += 1
        size = end - index
        if traces[index:end] != traces[end:end + size]:
            raise AssertionError(f'{runtime}: Writer/Reader traces differ')
        index = end + size
    if not traces or len(traces) % 2:
        raise AssertionError(f'{runtime}: missing/incomplete Writer/Reader traces')
    details = sum(line.startswith('TS_R12_DETAIL ') for line in stderr.splitlines())
    if details != 3:
        raise AssertionError(f'{runtime}: expected three bounded details')
    return dict(stats_rows=len(rows), writer_reader_cg_pairs=len(traces) // 2, details=details)


def invoke(executable, runtime, output, tag, kind, observed=False, payload=True):
    env = environment(runtime)
    if observed:
        env.update(TS_R12_STATS='1', TS_R12_TRACE='1', TS_R12_DETAIL_LIMIT='3')
    artifact = output / f'{tag}.bin'
    if payload:
        env['TS_R12_EXACT_PAYLOAD'] = str(artifact.resolve())
    start = time.perf_counter()
    process = subprocess.run([str(executable)], env=env, text=True, capture_output=True, timeout=600)
    elapsed = time.perf_counter() - start
    (output / f'{tag}.log').write_text(process.stdout + process.stderr)
    if process.returncode or 'PASS ' + runtime not in process.stdout:
        raise RuntimeError(f'{runtime}/{tag}: failed ({process.returncode}): {process.stderr[-3000:]}')
    data = artifact.read_bytes() if payload else b''
    summary = payload_summary(data, kind) if payload else {}
    observation = [line for line in process.stderr.splitlines() if line.startswith('TS_R12_')]
    return dict(stdout=process.stdout, stderr=process.stderr, data=data,
                payload=summary, observation=observation, elapsed=elapsed)


def run_mode(runtime, executables, output):
    local = output / runtime
    local.mkdir(parents=True, exist_ok=True)
    result = dict(runtime=runtime, tests={})
    for kind in ('native', 'quant'):
        runs = {}
        for build in ('baseline', 'optimized'):
            for observed in (False, True):
                tag = f'{kind}_{build}_{"observed" if observed else "off"}'
                runs[build, observed] = invoke(executables[build, kind], runtime,
                                                local, tag, kind, observed)
        anchor = runs['baseline', False]
        for key, row in runs.items():
            assert_bytes(anchor['data'], row['data'], f'{runtime}/{kind}/{key}')
            if row['stdout'] != anchor['stdout']:
                raise AssertionError(f'{runtime}/{kind}/{key}: native test output differs')
        if runs['baseline', True]['observation'] != runs['optimized', True]['observation']:
            raise AssertionError(f'{runtime}/{kind}: original/optimized diagnostics differ')
        item = dict(payload=anchor['payload'], full_payload_equal=True,
                    observation_bitexact=True, diagnostics_equal=True,
                    individual_elapsed_seconds={f'{b}_{int(o)}': r['elapsed']
                                                for (b, o), r in runs.items()},
                    native_output=anchor['stdout'].strip())
        if kind == 'native':
            item.update(check_traces(runs['baseline', True]['stderr'], runtime))
            check_traces(runs['optimized', True]['stderr'], runtime)
        result['tests'][kind] = item
    return result


def microbenchmark(runtime, executables, output, repeats):
    """Serial alternating pairs only; never share a timing pool with other tests."""
    local = output / ('benchmark_' + runtime)
    local.mkdir(parents=True, exist_ok=True)
    results = {}
    for kind in ('native', 'quant'):
        samples = {build: [] for build in ('baseline', 'optimized')}
        # One unreported warmup per build; no payload file I/O during timing.
        for build in samples:
            invoke(executables[build, kind], runtime, local,
                   f'{kind}_{build}_warmup', kind, payload=False)
        for repeat in range(repeats):
            order = ('baseline', 'optimized') if repeat % 2 == 0 else ('optimized', 'baseline')
            for build in order:
                row = invoke(executables[build, kind], runtime, local,
                             f'{kind}_{build}_{repeat}', kind, payload=False)
                samples[build].append(row['elapsed'])
        ratios = [o / b for b, o in zip(samples['baseline'], samples['optimized'])]
        results[kind] = dict(seconds=samples, paired_optimized_over_baseline=ratios,
                             median_ratio=statistics.median(ratios))
    return dict(runtime=runtime, results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-exe', type=Path, required=True)
    parser.add_argument('--optimized-exe', type=Path, required=True)
    parser.add_argument('--baseline-quant-exe', type=Path, required=True)
    parser.add_argument('--optimized-quant-exe', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path('runs/ts_r12_exact'))
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--benchmark-repeats', type=int, default=0)
    parser.add_argument('--benchmark-modes', nargs='+', choices=MODES,
                        default=['r12_c_distance_softtrim'])
    args = parser.parse_args()
    if args.jobs < 1 or args.benchmark_repeats < 0:
        parser.error('jobs must be positive and benchmark-repeats nonnegative')
    executables = {('baseline', 'native'): args.baseline_exe.resolve(),
                   ('optimized', 'native'): args.optimized_exe.resolve(),
                   ('baseline', 'quant'): args.baseline_quant_exe.resolve(),
                   ('optimized', 'quant'): args.optimized_quant_exe.resolve()}
    for executable in executables.values():
        if not executable.is_file():
            parser.error('missing executable: ' + str(executable))
    args.out.mkdir(parents=True, exist_ok=True)
    report = dict(revision='R12-POS-01', test='exact_optimization',
                  sequence_encode_decode=False, complete_bytes_compared=True,
                  executable={f'{b}_{k}': dict(path=str(p), sha256=sha256(p.read_bytes()))
                              for (b, k), p in executables.items()},
                  microbenchmark_scope='Synthetic TU native syntax/reference checks and synthetic TS-RDOQ; '
                                       'includes fixture/reference overhead, not full encoder timing')
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            report['results'] = list(pool.map(lambda mode: run_mode(mode, executables, args.out), MODES))
        report['microbenchmarks'] = [microbenchmark(mode, executables, args.out, args.benchmark_repeats)
                                     for mode in args.benchmark_modes] if args.benchmark_repeats else []
        report['status'] = 'passed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
        raise
    finally:
        (args.out / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    for result in report['results']:
        print(result['runtime'], 'full CABAC bytes + RDOQ q/absSum + observation equality PASS')


if __name__ == '__main__':
    main()
