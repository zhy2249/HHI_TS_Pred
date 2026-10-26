#!/usr/bin/env python3
"""Real library tests on synthetic TUs, never EncoderApp or video encoding.

Full coefficient/syntax/context records stream through FIFOs into SHA256.
Only bounded text and hashes are retained; no huge raw records on disk.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from ts_predictor_naming import R15_MODE_NUMBERS

LEGACY = ('current', 'r2_risk', 'r3_risk_guard', 'r6_reject_nopred',
          'r13_keep_hit_uniform', 'r13_keep_hit_spatial')


def hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def run(binary, runtime, out, label, family='R15', stats=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith('TS_')}
    env['TS_FIXED_PREDICTOR'] = runtime
    if family == 'R15':
        env['TS_R15_STATS'] = str(int(stats))  # Explicit even if the build default is 1.
    record = {'runtime': runtime, 'binary_sha256': hash_file(binary), 'stats': stats}
    with tempfile.TemporaryDirectory(prefix='ts-r15-native-') as tmp:
        pipes = {'payload': Path(tmp) / 'payload', 'nontarget': Path(tmp) / 'nontarget'}
        if family == 'R15':
            pipes['target'] = Path(tmp) / 'target'
        errors = []
        def consume(key, path):
            try:
                h, size = hashlib.sha256(), 0
                with path.open('rb') as f:
                    for block in iter(lambda: f.read(1048576), b''):
                        h.update(block)
                        size += len(block)
                record[key] = {'sha256': h.hexdigest(), 'bytes_streamed': size}
            except Exception as exc:
                errors.append(str(exc))
        threads = []
        for key, path in pipes.items():
            os.mkfifo(path)
            thread = threading.Thread(target=consume, args=(key, path), daemon=True)
            thread.start()
            threads.append(thread)
        env[f'TS_{family}_EXACT_PAYLOAD'] = str(pipes['payload'])
        env[f'TS_{family}_' + ('BDPCM_PAYLOAD' if family == 'R13' else 'NONTARGET_PAYLOAD')] = str(pipes['nontarget'])
        if family == 'R15':
            env['TS_R15_TARGET_PAYLOAD'] = str(pipes['target'])
        result = subprocess.run([str(binary.resolve())], env=env, capture_output=True, text=True, timeout=180)
        for thread in threads:
            thread.join(timeout=5)
        output = result.stdout + result.stderr
        (out / f'{label}.log').write_text(output[:131072])
        if result.returncode or errors or any(t.is_alive() for t in threads):
            raise RuntimeError(f'{label} failed: rc={result.returncode}; {errors}; {output[-4000:]}')
        if len(output) > 131072 or 'PASS ' not in output:
            raise RuntimeError(f'{label}: missing PASS or excessive output')
        record['coverage'] = [line for line in output.splitlines() if re.match(r'TS_R15_(SYNTAX|QUANT)', line)]
        record['output_sha256'] = hashlib.sha256(output.encode()).hexdigest()
    return record


def require_equal(a, b, key='payload'):
    if a[key] != b[key]:
        raise AssertionError((a['runtime'], b['runtime'], key, a[key], b[key]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=Path('build/ts-r15-codec'))
    parser.add_argument('--legacy-build-dir', type=Path)
    parser.add_argument('--master-off-build-dir', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('runs/ts_r15_codec_validation'))
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    records = {}
    # One subprocess at a time. Hash consumers use at most three 1 MiB buffers.
    binary = args.build_dir / 'bin/TsR15NativeTest'
    for name in ('current', 'nopred', *R15_MODE_NUMBERS):
        records[name] = run(binary, name, out, name)
        if name.startswith('r15_'):
            require_equal(records[name], records['current'], 'nontarget')
        print(f'PASS {name}', flush=True)
    # Legacy NoPred also changes TS RDOQ with TSRC disabled. R15 deliberately
    # keeps that non-target path native; compare Identity on the shared scope.
    require_equal(records['nopred'], records['r15_identity'], 'target')
    require_equal(records['r15_g_eq_k2'], records['r15_n_eq_k2'])
    for name in R15_MODE_NUMBERS:
        observed = run(binary, name, out, name + '_stats', stats=True)
        require_equal(records[name], observed)
        records[name + '_stats'] = observed
    legacy = args.build_dir / 'bin/TsR13NativeTest'
    if args.legacy_build_dir:
        for name in LEGACY:
            before = run(args.legacy_build_dir / 'bin/TsR13NativeTest', name, out, 'before_' + name, family='R13')
            after = run(legacy, name, out, 'after_' + name, family='R13')
            require_equal(before, after)
            records['legacy_' + name] = {'before': before, 'after': after}
    if args.master_off_build_dir:
        before = run(args.master_off_build_dir / 'bin/TsR15NativeTest', 'current', out, 'master_off')
        after = records['current']
        require_equal(before, after)
        records['master_off'] = {'off': before, 'on_current': after}
    (out / 'native_validation.json').write_text(json.dumps({
        'schema': 'R15-CODEC-NATIVE-v1', 'video_apps_run': False, 'records': records,
        'output_contract': 'raw records hashed through FIFO; no raw payload retained',
        'comparison': 'SHA256 and byte length over q, syntax, budget, fractional bits and all context fields',
        'status': 'PASS'}, indent=2) + '\n')
    print('PASS all R15 native checks; no video application was invoked', flush=True)


if __name__ == '__main__':
    main()
