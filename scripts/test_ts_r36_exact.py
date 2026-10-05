#!/usr/bin/env python3
"""R3/R6 exact optimization verification with native synthetic TU tests only.

Build the same source with JVET_BJUT_TS_R36_EXACT_OPT=0 and =1. Compare full
CABAC byte payloads and complete final quantized coefficients/absSum, including
observation-on/off runs. Optional timing is serial and alternates build order;
it is a synthetic unit-test benchmark, NOT end-to-end EncoderApp timing.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import statistics
import struct
import subprocess
import time

from test_ts_r12_exact import assert_bytes, payload_summary as native_summary, sha256
from ts_predictor_naming import R6_MODE_NUMBERS

MODES = ['current', 'r3_risk_guard', 'r3_risk_guard_y', *R6_MODE_NUMBERS]
POLICIES = {'current': 1, 'r3_risk_guard': 13, 'r3_risk_guard_y': 14,
            **{name: 24 + number for name, number in R6_MODE_NUMBERS.items()}}
QUANT_MAGIC = b'TSR36QUANTv1\n'


def environment(runtime, observed=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=runtime, TS_R2_STATS='0', TS_R3_STATS='0',
               TS_R6_STATS='0', TS_R10_STATS='0', TS_R11_STATS='0', TS_R12_STATS='0')
    if observed:
        env.update(TS_R3_STATS='1', TS_R6_STATS='1', TS_COND_TRACE='1')
    return env


def quant_summary(data):
    if not data.startswith(QUANT_MAGIC):
        raise AssertionError('quant: missing/version-mismatched payload header')
    offset = len(QUANT_MAGIC)

    def words(count):
        nonlocal offset
        if offset + count * 8 > len(data):
            raise AssertionError('quant: truncated record')
        values = struct.unpack_from('<' + 'Q' * count, data, offset)
        offset += count * 8
        return values

    count, = words(1)
    if count != 240:
        raise AssertionError(f'quant: expected 240 records, got {count}')
    content_bytes = 0
    bdpcm_counts = [0, 0, 0]
    for trial in range(count):
        index, width, height, comp, qp, bdpcm, coefficients, abs_sum = words(8)
        if index != trial or not width or not height or comp not in (0, 1, 2) or qp > 63:
            raise AssertionError('quant: malformed fixture metadata')
        if bdpcm not in (0, 1, 2) or coefficients != width * height:
            raise AssertionError('quant: malformed BDPCM/coefficient count')
        length = coefficients * 8
        if offset + length > len(data):
            raise AssertionError('quant: truncated coefficient payload')
        q = struct.unpack_from('<' + 'q' * coefficients, data, offset)
        if sum(abs(v) for v in q) != abs_sum:
            raise AssertionError('quant: absSum differs from final q')
        offset += length
        content_bytes += length
        bdpcm_counts[bdpcm] += 1
    if offset != len(data) or min(bdpcm_counts) == 0:
        raise AssertionError('quant: trailing payload or missing BDPCM coverage')
    return dict(records=count, content_bytes=content_bytes, framed_bytes=len(data),
                bdpcm_counts=bdpcm_counts, sha256=sha256(data))


def check_observation(stderr, runtime):
    rows = [line for line in stderr.splitlines()
            if line.startswith(('TS_R3_STATS ', 'TS_R6_STATS '))]
    traces = [line for line in stderr.splitlines() if line.startswith('TS_COND ')]
    if runtime == 'current':
        if rows or traces:
            raise AssertionError('Current unexpectedly emitted R3/R6 observations')
        return dict(stats_rows=0, writer_reader_cg_pairs=0)
    if not rows or {int(line.split()[1].split(',')[0]) for line in rows} != {POLICIES[runtime]}:
        raise AssertionError(f'{runtime}: missing/mismatched statistics mode')
    index = 0
    pairs = 0
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
        pairs += size
    if not pairs:
        raise AssertionError(f'{runtime}: no Writer/Reader traces')
    return dict(stats_rows=len(rows), writer_reader_cg_pairs=pairs)


def invoke(executable, runtime, output, tag, kind, observed=False, payload=True, inner_repeats=1):
    env = environment(runtime, observed)
    if inner_repeats != 1:
        if kind != 'quant' or payload or not 1 <= inner_repeats <= 1000:
            raise ValueError('Internal repetition is for quant timing without payload only')
        env['TS_R36_BENCH_REPEAT'] = str(inner_repeats)
    artifact = output / f'{tag}.bin'
    if payload:
        env['TS_R36_EXACT_PAYLOAD'] = str(artifact.resolve())
    start = time.perf_counter()
    process = subprocess.run([str(executable)], env=env, text=True,
                             capture_output=True, timeout=600)
    elapsed = time.perf_counter() - start
    (output / f'{tag}.log').write_text(process.stdout + process.stderr)
    if process.returncode or 'PASS ' + runtime not in process.stdout:
        raise RuntimeError(f'{runtime}/{tag}: failed ({process.returncode}): {process.stderr[-3000:]}')
    if inner_repeats != 1:
        expected = f'TS_R36_BENCH_REPEAT {inner_repeats} total_trials={240 * inner_repeats}'
        if expected not in process.stdout.splitlines():
            raise AssertionError('Quant test did not acknowledge internal repetition; rebuild the test executable')
    data = artifact.read_bytes() if payload else b''
    summary = (native_summary(data, 'native') if kind == 'native' else quant_summary(data)) if payload else {}
    observation = [line for line in process.stderr.splitlines()
                   if line.startswith(('TS_R3_', 'TS_R6_', 'TS_COND '))]
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
                runs[build, observed] = invoke(executables[build, kind], runtime, local,
                                                tag, kind, observed)
        anchor = runs['baseline', False]
        for key, row in runs.items():
            assert_bytes(anchor['data'], row['data'], f'{runtime}/{kind}/{key}')
            if row['stdout'] != anchor['stdout']:
                raise AssertionError(f'{runtime}/{kind}/{key}: native test output differs')
            if not key[1] and row['observation']:
                raise AssertionError(f'{runtime}/{kind}/{key}: observation not disabled')
        if runs['baseline', True]['observation'] != runs['optimized', True]['observation']:
            raise AssertionError(f'{runtime}/{kind}: original/optimized diagnostics differ')
        item = dict(payload=anchor['payload'], full_payload_equal=True,
                    observation_bitexact=True, diagnostics_equal=True,
                    native_output=anchor['stdout'].strip(),
                    individual_elapsed_seconds={f'{b}_{int(o)}': row['elapsed']
                                                for (b, o), row in runs.items()})
        if kind == 'native':
            item.update(check_observation(runs['baseline', True]['stderr'], runtime))
            check_observation(runs['optimized', True]['stderr'], runtime)
        result['tests'][kind] = item
    return result


def microbenchmark(runtime, executables, output, repeats, inner_repeats):
    local = output / ('benchmark_' + runtime)
    local.mkdir(parents=True, exist_ok=True)
    result = {}
    for kind in ('native', 'quant'):
        inner = inner_repeats if kind == 'quant' else 1
        samples = {build: [] for build in ('baseline', 'optimized')}
        expected_output = None
        for build in samples:
            row = invoke(executables[build, kind], runtime, local,
                         f'{kind}_{build}_warmup', kind, payload=False, inner_repeats=inner)
            if expected_output is not None and row['stdout'] != expected_output:
                raise AssertionError(f'{runtime}/{kind}: benchmark repeated fixture output differs')
            expected_output = row['stdout']
        for repeat in range(repeats):
            order = ('baseline', 'optimized') if repeat % 2 == 0 else ('optimized', 'baseline')
            for build in order:
                row = invoke(executables[build, kind], runtime, local,
                             f'{kind}_{build}_{repeat}', kind, payload=False, inner_repeats=inner)
                if row['stdout'] != expected_output:
                    raise AssertionError(f'{runtime}/{kind}: benchmark repeated fixture output differs')
                samples[build].append(row['elapsed'])
        ratios = [o / b for b, o in zip(samples['baseline'], samples['optimized'])]
        result[kind] = dict(seconds=samples, paired_optimized_over_baseline=ratios,
                            median_ratio=statistics.median(ratios), internal_fixture_repeats=inner)
    return dict(runtime=runtime, results=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-exe', type=Path, required=True)
    parser.add_argument('--optimized-exe', type=Path, required=True)
    parser.add_argument('--baseline-quant-exe', type=Path, required=True)
    parser.add_argument('--optimized-quant-exe', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path('runs/ts_r36_exact'))
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--modes', choices=MODES, nargs='+', default=MODES)
    parser.add_argument('--benchmark-repeats', type=int, default=0)
    parser.add_argument('--benchmark-inner-repeats', type=int, default=20,
                        help='Repeat identical 240-TU quant fixture per timing sample (1..1000)')
    parser.add_argument('--benchmark-modes', choices=MODES, nargs='+',
                        default=['current', 'r3_risk_guard', 'r6_reject_nopred'])
    args = parser.parse_args()
    if args.jobs < 1 or args.benchmark_repeats < 0:
        parser.error('jobs must be positive and benchmark-repeats nonnegative')
    if not 1 <= args.benchmark_inner_repeats <= 1000:
        parser.error('benchmark-inner-repeats must be in [1,1000]')
    executables = {('baseline', 'native'): args.baseline_exe.resolve(),
                   ('optimized', 'native'): args.optimized_exe.resolve(),
                   ('baseline', 'quant'): args.baseline_quant_exe.resolve(),
                   ('optimized', 'quant'): args.optimized_quant_exe.resolve()}
    for executable in executables.values():
        if not executable.is_file():
            parser.error('missing executable: ' + str(executable))
    args.out.mkdir(parents=True, exist_ok=True)
    report = dict(test='r36_exact_optimization', sequence_encode_decode=False,
                  complete_bytes_compared=True, modes=args.modes,
                  expected_build_macros={'baseline': 0, 'optimized': 1},
                  executable={f'{b}_{k}': dict(path=str(p), sha256=sha256(p.read_bytes()))
                              for (b, k), p in executables.items()},
                  microbenchmark_scope='Synthetic TU native syntax/reference checks and synthetic TS-RDOQ/BDPCM; '
                                       'includes fixture/reference overhead, not full encoder timing')
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            report['results'] = list(pool.map(lambda mode: run_mode(mode, executables, args.out), args.modes))
        # All verification workers have stopped before beginning serial timings.
        report['microbenchmarks'] = [microbenchmark(mode, executables, args.out, args.benchmark_repeats,
                                                  args.benchmark_inner_repeats)
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
