#!/usr/bin/env python3
"""Verify R13 diagnostic purity with synthetic TU Writer/Reader/RDOQ fixtures.

No EncoderApp/DecoderApp or video is started. Full binary payloads are compared
byte for byte in temporary files and removed after each mode/scope. The native
harness intentionally lacks EncoderApp startup announcements; parser identity
is supplied by this runner only, and never inserted into the preserved raw log.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from test_ts_r13_native import identical, sha256
from ts_r13_diagnostic import parse

MODES = {'current': 1, 'r13_keep_hit_uniform': 98, 'r13_keep_hit_spatial': 99}
RECORDED_ENV = ('TS_FIXED_PREDICTOR', 'TS_R13_DIAG_SCOPE', 'TS_R13_DETAIL_LIMIT', 'TS_R13_DIAG')


def run(executable, before, output, runtime, scope):
    policy = MODES[runtime]
    env = {k: v for k, v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=runtime, TS_R13_DIAG_SCOPE=scope,
               TS_R13_DETAIL_LIMIT='4')
    with tempfile.TemporaryDirectory(prefix=f'{runtime}_{scope}_', dir=output) as folder:
        temp = Path(folder)

        def call(tag, diagnostic, program=executable):
            payload, bdpcm = temp / (tag + '.bin'), temp / (tag + '_bdpcm.bin')
            command_env = {**env, 'TS_R13_DIAG': str(int(diagnostic)),
                           'TS_R13_EXACT_PAYLOAD': str(payload),
                           'TS_R13_BDPCM_PAYLOAD': str(bdpcm)}
            process = subprocess.run([str(program)], env=command_env,
                                     text=True, capture_output=True, timeout=300)
            log = output / f'{runtime}_{scope}_{tag}.log'
            log.write_text(process.stdout + process.stderr)
            if process.returncode:
                raise RuntimeError(f'{runtime}/{scope}/{tag}: rc={process.returncode}; see {log}')
            if f'PASS {runtime}' not in process.stdout or 'sequence_encode_decode=false' not in process.stdout:
                raise AssertionError(f'Missing native fixture PASS identity: {log}')
            if not re.search(r'TS_R13_NATIVE_DIGEST \d+', process.stdout):
                raise AssertionError(f'Missing complete-payload digest: {log}')
            return process, payload, bdpcm, log

        quiet, original, bdpcm, quiet_log = call('off', False)
        if 'TS_R13_DIAG_' in quiet.stderr or 'TS_R13_FRAME_' in quiet.stderr:
            raise AssertionError('Diagnostic is not OFF by default/explicit OFF')
        observed, observed_payload, observed_bdpcm, observed_log = call('on', True)
        if not identical(original, observed_payload) or not identical(bdpcm, observed_bdpcm):
            raise AssertionError(f'Diagnostic changed full syntax/q/context/budget payload: {runtime}/{scope}')
        if observed.stdout != quiet.stdout:
            raise AssertionError(f'Diagnostic changed native coverage/digest output: {runtime}/{scope}')

        # Metadata is known from this subprocess environment, not falsely
        # attributed to the native harness's own stdout/stderr.
        parser_prefix = f'TS R13 diagnosis=R13-DIAG-v1; trajectory={runtime}; frac-scale=32768;\n'
        if scope != 'all':
            parser_prefix += (f'TS R13 ablation=R13-COMPONENT-v1; scope={scope}; '
                              'changes-coding=1; decoder-must-match=1;\n')
        reports, scale = parse(parser_prefix + observed.stderr)
        if set(reports) != {'CG', 'COEFF', 'RDOQ'}:
            raise AssertionError('Native diagnostic must exercise Writer and RDOQ tables')
        if any(row['trajectory_policy'] != policy for rows in reports.values() for row in rows):
            raise AssertionError('Native diagnostic has incorrect trajectory policy')

        coverage = {}
        for kind in ('SYNTAX', 'QUANT'):
            line = next(line for line in quiet.stdout.splitlines()
                        if line.startswith(f'TS_R13_{kind} '))
            coverage[kind.lower()] = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
        cg = reports['CG']
        if sum(r['tu_count'] for r in cg) != coverage['syntax']['TU']:
            raise AssertionError('Writer diagnostic TU population differs from syntax fixtures')
        if sum(r['cg_count'] for r in cg) != coverage['syntax']['CG']:
            raise AssertionError('Writer diagnostic CG population differs from syntax fixtures')
        for mode in (0, 1, 2):
            coeff = [r for r in reports['COEFF'] if r['shadow_mode'] == mode]
            if sum(r['coeff_count'] for r in coeff) != sum(r['coeff_count'] for r in cg):
                raise AssertionError('Diagnostic coefficient branches have different populations')
            if sum(r['nonzero_count'] for r in coeff) != sum(r['nonzero_count'] for r in cg):
                raise AssertionError('Diagnostic coefficient nonzero branches have different populations')

        result = dict(runtime=runtime, scope=scope, sequence_encode_decode=False,
                      # Do not persist inherited PATH/proxy/auth environment.
                      environment={k: v for k, v in {**env, 'TS_R13_DIAG': '0 or 1'}.items()
                                   if k in RECORDED_ENV},
                      payload_sha256=sha256(original), payload_bytes=original.stat().st_size,
                      bdpcm_sha256=sha256(bdpcm), diagnostic_bitexact=True,
                      native_writer_reader_q_context_budget_consistent=True,
                      scope_is_algorithm_ablation=scope != 'all',
                      parser_identity_source='runner subprocess environment; absent in raw native log',
                      frac_scale=scale, table_rows={k: len(v) for k, v in reports.items()},
                      coverage=coverage, raw_logs=[str(quiet_log), str(observed_log)],
                      _bdpcm=bdpcm.read_bytes())
        if before and scope == 'all':
            _, reference, reference_bdpcm, reference_log = call('before', False, before)
            if not identical(original, reference) or not identical(bdpcm, reference_bdpcm):
                raise AssertionError(f'Diagnostic patch OFF differs from frozen binary payload: {runtime}')
            result['before_byte_identical'] = True
            result['raw_logs'].append(str(reference_log))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=Path('build/ts-r14/bin/TsR13NativeTest'))
    parser.add_argument('--before-exe', type=Path, default=Path('build/ts-r13/bin/TsR13NativeTest'))
    parser.add_argument('--out', type=Path, default=Path('runs/r13_diagnosis_20261024/native_diagnostic'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    executable, before = args.exe.resolve(), args.before_exe.resolve()
    results, reference_bdpcm = [], None
    for runtime in MODES:
        for scope in (('all',) if runtime == 'current' else ('all', 'luma', 'chroma')):
            result = run(executable, before, args.out, runtime, scope)
            bdpcm = result.pop('_bdpcm')
            if reference_bdpcm is None:
                reference_bdpcm = bdpcm
            if bdpcm != reference_bdpcm:
                raise AssertionError('BDPCM changed across policy/scope')
            result['bdpcm_cross_policy_scope_identical'] = True
            results.append(result)
            print(runtime, scope, 'PASS', flush=True)
            report = dict(sequence_encode_decode=False, results=results,
                          native_exe_sha256=sha256(executable), before_exe_sha256=sha256(before),
                          harness_sha256=sha256(Path(__file__).with_name('ts_r13_native_test.cpp')))
            (args.out / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    for runtime in ('r13_keep_hit_uniform', 'r13_keep_hit_spatial'):
        if len({r['payload_sha256'] for r in results if r['runtime'] == runtime}) != 3:
            raise AssertionError(f'Scope ablations lack payload activity: {runtime}')
    print('Seven policy/scope cases passed; temporary payloads removed; raw logs and hashes preserved.')


if __name__ == '__main__':
    main()
