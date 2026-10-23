#!/usr/bin/env python3
"""Synthetic TU / linked-library CABAC/RDOQ validation; never starts a video app.

Build TsR14NativeTest and TsR13NativeTest in build/ts-r14 first. The optional
legacy comparison runs the unchanged R13 fixture executable from both builds;
its full binary records (q, syntax, budget, context) must match byte-for-byte.
Full records are temporary; bounded logs and SHA256 provenance are retained.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

LEGACY = {'current': 1, 'r2_risk': 10, 'r3_risk_guard': 13,
          'r6_reject_nopred': 26, 'r13_keep_hit_uniform': 98,
          'r13_keep_hit_spatial': 99}
R14 = {
    'r14_g2_none_equal': 1, 'r14_g4_none_equal': 4,
    'r14_g2_none_half': 7, 'r14_g4_none_half': 10,
    'r14_g2_none_zero': 13, 'r14_g4_none_zero': 16,
    'r14_fixed_near_only': 19, 'r14_fixed_quarter': 20,
    'r14_fixed_threequarter': 21, 'r14_g2_pair2_equal': 22,
    'r14_g4_pair2_equal': 23, 'r14_g2_pair2_half': 24,
    'r14_g4_pair2_half': 25, 'r14_g2_pair2_zero': 26,
    'r14_g4_pair2_zero': 27,
}


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


def clean_environment(runtime):
    env = {key: value for key, value in os.environ.items() if not key.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=runtime, TS_R3_STATS='0', TS_R6_STATS='0',
               TS_R10_STATS='0', TS_R11_STATS='0', TS_R12_STATS='0', TS_R13_STATS='0')
    return env


def coverage(output, prefix):
    line = next(line for line in output.splitlines() if line.startswith(prefix + ' '))
    return {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', line)}


def observation_checks(output, limit):
    """Trace line contents, including per-CG rolling p/state digest, must match."""
    traces = [line for line in output.splitlines() if line.startswith('TS_R14_TRACE ')]
    writer = [line.replace('role=W', 'role=X') for line in traces if 'role=W' in line]
    reader = [line.replace('role=R', 'role=X') for line in traces if 'role=R' in line]
    if len(writer) != limit or writer != reader:
        raise AssertionError(f'Bounded Writer/Reader trace mismatch: W={len(writer)} R={len(reader)}')
    return len(writer)


def table(output, prefix):
    header = None
    rows = []
    for line in output.splitlines():
        if line.startswith(prefix + '_HEADER '):
            candidate = next(csv.reader([line.split(' ', 1)[1]]))
            if header is not None and header != candidate:
                raise AssertionError('Conflicting observation schema: ' + prefix)
            header = candidate
        elif line.startswith(prefix + ' '):
            if header is None:
                raise AssertionError('Data before header: ' + prefix)
            values = next(csv.reader([line.split(' ', 1)[1]]))
            if len(values) != len(header):
                raise AssertionError('Observation schema width: ' + prefix)
            rows.append(dict(zip(header, map(int, values))))
    return rows


def statistics_checks(output, public_mode, syntax):
    rows = table(output, 'TS_R14_STATS')
    trials = table(output, 'TS_R14_TRIAL')
    if not rows or not trials:
        raise AssertionError('Missing final-Writer or separate RDOQ trial population')
    if {row['mode'] for row in rows + trials} != {public_mode}:
        raise AssertionError('Incorrect R14 public mode identity')
    total = lambda name: sum(row[name] for row in rows)
    for field, expected in (('tu_count', syntax['TU']), ('cg_count', syntax['CG']),
                            ('coeff_count', syntax['causal']), ('eligible_count', syntax['eligible']),
                            ('state_change_count', syntax['updates'])):
        if total(field) != expected:
            raise AssertionError(f'Incorrect final-Writer {field}: {total(field)} != {expected}')
    if total('tu_with_weight') + total('tu_no_weight') != syntax['TU']:
        raise AssertionError('Incomplete TU weight-change terminal population')
    if total('tu_with_pdiff') + total('tu_no_pdiff') != syntax['TU']:
        raise AssertionError('Incomplete TU predictor-change terminal population')
    if total('eligible_count') != total('next_pair_count') + total('next_unpaired_count'):
        raise AssertionError('Next-event pairing loses or duplicates eligible events')
    if total('tu_valid_sum') != total('eligible_count'):
        raise AssertionError('TU-local eligible totals disagree')
    if not total('actual_remap_vs_current'):
        raise AssertionError('Fixtures do not exercise actual regular remapping changes')
    for row in rows:
        if row['n'] < 0:
            if row['coeff_count'] or any(row[k] != -1 for k in ('cutoff', 'state', 'weight')):
                raise AssertionError('Sentinel totals row duplicates coefficients')
            continue
        if row['tu_count'] or row['cg_count']:
            raise AssertionError('Per-coefficient row duplicates TU/CG totals')
        if row['nonzero_count'] > row['coeff_count']:
            raise AssertionError('Incorrect nonzero population')
        if row['n'] < 3 and row['eligible_count']:
            raise AssertionError('Sparse support incorrectly eligible')
        if (not row['target'] or row['bdpcm']) and any(row[field] for field in
                ('eligible_count', 'state_change_count', 'p_vs_current', 'actual_remap_vs_current',
                 'p_vs_initial_weight', 'actual_remap_vs_initial_weight', 'next_p_changed', 'next_actual_remap_changed')):
            raise AssertionError('Non-target path changed by R14')
        if row['cutoff'] <= 0 and any(row[field] for field in
                ('actual_remap_nonzero', 'actual_remap_vs_current', 'actual_remap_vs_initial_weight', 'next_actual_remap_changed')):
            raise AssertionError('Pure bypass/zero CG incorrectly remapped')
        if not 0 <= row['actual_remap_vs_current'] <= row['p_vs_current'] <= row['coeff_count']:
            raise AssertionError('Current predictor/remapping population mismatch')
        if row['eligible_count'] != row['neutral_count'] + row['up_count'] + row['down_count']:
            raise AssertionError('Feedback directions not an exhaustive partition')
        if row['state_change_count'] != row['weight_change_count'] + row['phase_only_count']:
            raise AssertionError('Phase/weight transitions do not partition state changes')
        if row['eligible_count'] != row['step_better_count'] + row['step_worse_count'] + row['step_equal_count']:
            raise AssertionError('Immediate step population mismatch')
        if row['next_pair_count'] != row['next_positive_count'] + row['next_zero_count'] + row['next_negative_count']:
            raise AssertionError('Next-event gain partition mismatch')
        if row['next_phase_gain_sum']:
            raise AssertionError('Phase-only transition has nonzero next-event gain')
        if row['next_phase_pair_count'] > row['next_zero_count']:
            raise AssertionError('Phase-only pairs not contained in zero-gain pairs')
        if row['next_cross_cg_count'] > row['next_pair_count']:
            raise AssertionError('Cross-CG pairs exceed all pairs')
        if not 0 <= row['next_actual_remap_changed'] <= row['next_p_changed'] <= row['next_pair_count']:
            raise AssertionError('Next-event predictor/remapping population mismatch')
        if not 0 <= row['actual_remap_vs_initial_weight'] <= row['p_vs_initial_weight'] <= row['coeff_count']:
            raise AssertionError('Initial-weight predictor/remapping population mismatch')
    for row in trials:
        if not 0 <= row['rolled_back_state_count'] <= row['zero_cg_count'] <= row['cg_trial_count']:
            raise AssertionError('Invalid separate RDOQ rollback population')
    return dict(stats_rows=len(rows), trial_rows=len(trials),
                eligible_events=total('eligible_count'), next_pairs=total('next_pair_count'),
                next_cross_cg_pairs=total('next_cross_cg_count'), next_phase_pairs=total('next_phase_pair_count'),
                actual_remap_vs_current=total('actual_remap_vs_current'),
                actual_remap_vs_initial_weight=total('actual_remap_vs_initial_weight'),
                next_p_changed=total('next_p_changed'), next_actual_remap_changed=total('next_actual_remap_changed'),
                rd_trial_cgs=sum(row['cg_trial_count'] for row in trials),
                rd_zero_cgs=sum(row['zero_cg_count'] for row in trials),
                rd_nontrivial_state_rollbacks=sum(row['rolled_back_state_count'] for row in trials))


def run(executable, out, runtime):
    public_mode = R14.get(runtime)
    env = clean_environment(runtime)
    with tempfile.TemporaryDirectory(prefix=runtime + '_', dir=out) as temporary:
        temp = Path(temporary)

        def call(tag, options):
            payload, non_target = temp / (tag + '.bin'), temp / (tag + '_nontarget.bin')
            process = subprocess.run([str(executable)],
                env={**env, **options, 'TS_R14_EXACT_PAYLOAD': str(payload),
                     'TS_R14_NONTARGET_PAYLOAD': str(non_target)},
                text=True, capture_output=True, timeout=300)
            (out / (runtime + '_' + tag + '.log')).write_text(process.stdout + process.stderr)
            if process.returncode:
                raise RuntimeError(f'{runtime}/{tag}: {process.stdout[-1000:]} {process.stderr[-5000:]}')
            if 'PASS ' + runtime not in process.stdout or 'sequence_encode_decode=false' not in process.stdout:
                raise AssertionError('Missing native-test identity: ' + runtime)
            if not re.search(r'TS_R14_NATIVE_DIGEST \d+', process.stdout):
                raise AssertionError('Missing native payload digest')
            return process, payload, non_target

        quiet, original, non_target = call('off', {})
        syntax = coverage(quiet.stdout, 'TS_R14_SYNTAX')
        quant = coverage(quiet.stdout, 'TS_R14_QUANT')
        if any(line.startswith(('TS_R14_STATS', 'TS_R14_TRACE', 'TS_R14_DETAIL'))
               for line in quiet.stderr.splitlines()):
            raise AssertionError('R14 observation is not OFF by default')
        result = dict(runtime=runtime, policy=99 + public_mode if public_mode else LEGACY[runtime],
                      public_mode=public_mode, native_output=quiet.stdout.strip(),
                      payload_sha256=sha256(original), payload_bytes=original.stat().st_size,
                      non_target_sha256=sha256(non_target),
                      syntax_coverage=syntax, quant_coverage=quant,
                      _non_target=non_target.read_bytes())
        if public_mode:
            observed, observed_payload, observed_non_target = call('observed',
                dict(TS_R14_STATS='1', TS_R14_TRACE='1', TS_R14_DETAIL_LIMIT='7'))
            if quiet.stdout != observed.stdout or not identical(original, observed_payload):
                raise AssertionError('Observation changed full syntax/q/budget/context/state payload: ' + runtime)
            if not identical(non_target, observed_non_target):
                raise AssertionError('Observation changed non-target payload')
            population = statistics_checks(observed.stderr, public_mode, syntax)
            pairs = observation_checks(observed.stderr, 7)
            detail_count = sum(line.startswith('TS_R14_DETAIL ') for line in observed.stderr.splitlines())
            if detail_count != 7:
                raise AssertionError(f'Expected 7 bounded detail rows, got {detail_count}')
            result.update(observation_bitexact=True, writer_reader_cg_trace_pairs=pairs,
                          observation_coverage=population)
            if public_mode == 1:
                trace_only, trace_payload, _ = call('trace_only',
                    dict(TS_R14_TRACE='1', TS_R14_DETAIL_LIMIT='2'))
                if any(line.startswith('TS_R14_STATS') for line in trace_only.stderr.splitlines()):
                    raise AssertionError('Trace-only incorrectly enabled aggregate statistics')
                if not identical(original, trace_payload):
                    raise AssertionError('Trace-only changed full payload')
                observation_checks(trace_only.stderr, 2)
                result['trace_only_bitexact'] = True
        return result


def legacy_compare(before, after, out, runtime):
    """The pre-existing R13 harness remains unchanged in both executables."""
    env = clean_environment(runtime)
    with tempfile.TemporaryDirectory(prefix='legacy_' + runtime + '_', dir=out) as temporary:
        temp = Path(temporary)
        records = []
        for tag, executable in (('before', before), ('after', after)):
            payload = temp / (tag + '.bin')
            bdpcm = temp / (tag + '_bdpcm.bin')
            process = subprocess.run([str(executable)], env={**env,
                'TS_R13_EXACT_PAYLOAD': str(payload), 'TS_R13_BDPCM_PAYLOAD': str(bdpcm)},
                text=True, capture_output=True, timeout=300)
            (out / ('legacy_' + runtime + '_' + tag + '.log')).write_text(process.stdout + process.stderr)
            if process.returncode or 'PASS ' + runtime not in process.stdout:
                raise RuntimeError(f'Legacy {runtime}/{tag}: {process.stderr[-4000:]}')
            records.append((payload, bdpcm, process.stdout))
        if records[0][2] != records[1][2] or not identical(records[0][0], records[1][0]) or not identical(records[0][1], records[1][1]):
            raise AssertionError('Legacy mode changed from pre-R14 build: ' + runtime)
        return dict(runtime=runtime, byte_identical=True, payload_sha256=sha256(records[0][0]),
                    payload_bytes=records[0][0].stat().st_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=Path('build/ts-r14/bin/TsR14NativeTest'))
    parser.add_argument('--legacy-before-exe', type=Path,
                        help='Preserved pre-R14 build/ts-r13/bin/TsR13NativeTest')
    parser.add_argument('--legacy-after-exe', type=Path,
                        help='Unchanged TsR13NativeTest harness built with new sources')
    parser.add_argument('--out', type=Path, default=Path('runs/ts_r14_native'))
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--modes', nargs='+', choices=list(LEGACY) + list(R14),
                        help='Debug subset only; default validates all 15 R14 and 6 legacy policies')
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        parser.error('--jobs must be in [1,8]')
    if bool(args.legacy_before_exe) != bool(args.legacy_after_exe):
        parser.error('--legacy-before-exe and --legacy-after-exe must be supplied together')
    executable = args.exe.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    modes = args.modes or list(LEGACY) + list(R14)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda runtime: run(executable, args.out, runtime), modes))
    current = next((row['_non_target'] for row in results if row['runtime'] == 'current'), None)
    for result in results:
        if current is not None and result['public_mode']:
            if result['_non_target'] != current:
                raise AssertionError('R14 non-target fixtures differ from Current: ' + result['runtime'])
            result['non_target_current_byte_identical'] = True
        del result['_non_target']
    rollback_covered = any(row.get('observation_coverage', {}).get('rd_nontrivial_state_rollbacks', 0)
                           for row in results)
    if not args.modes and not rollback_covered:
        raise AssertionError('Full matrix failed to exercise an actual nontrivial RDOQ CG state rollback')
    legacy = []
    if args.legacy_before_exe:
        before, after = args.legacy_before_exe.resolve(), args.legacy_after_exe.resolve()
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            legacy = list(pool.map(lambda runtime: legacy_compare(before, after, args.out, runtime), LEGACY))
    report = dict(revision='R14-NF-168-v3', sequence_encode_decode=False,
                  complete_mode_matrix=not bool(args.modes),
                  rdoq_nontrivial_rollback_covered=rollback_covered,
                  native_exe_sha256=sha256(executable),
                  harness_sha256=sha256(Path(__file__).with_name('ts_r14_native_test.cpp')),
                  legacy_before_exe_sha256=sha256(args.legacy_before_exe) if legacy else None,
                  legacy_after_exe_sha256=sha256(args.legacy_after_exe) if legacy else None,
                  legacy_status='checked' if legacy else 'NOT RUN',
                  limits=['Synthetic TU/local syntax only; no frame/sequence encoding or BD-rate',
                          'rollback_api checks snapshot/restore; actual RDOQ state rollback coverage is reported separately per mode'],
                  results=results, legacy_results=legacy)
    (args.out / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    for result in results:
        print(result['runtime'], 'PASS', 'full native records, causal state/context/budget')
    print('Pre-R14 legacy byte comparison:', report['legacy_status'])


if __name__ == '__main__':
    main()
