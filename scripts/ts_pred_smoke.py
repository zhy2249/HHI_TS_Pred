#!/usr/bin/env python3
"""Reproducible small synthetic validation, never evidence for coding gains."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--off', type=Path, required=True)
    p.add_argument('--on', type=Path, required=True)
    p.add_argument('--decoder', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path('runs/ts_smoke'))
    p.add_argument('--extended', action='store_true', help='Also run 444, BDPCM, lossless and TSRC-disabled controls')
    p.add_argument('--cases', help='Optional comma-separated subset of case names')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cases = [('ai420', '420', 'intra', []), ('lb420', '420', 'lowdelay', [])]
    if args.extended:
        cases += [('ai444', '444', 'intra', []),
                  ('bdpcm', '420', 'intra', ['--BDPCM=1']),
                  ('lossless', '420', 'intra', ['--CostMode=lossless', '--TSRCdisableLL=0', '--Log2MaxTbSize=5']),
                  ('tsrc_off', '420', 'intra', ['--CostMode=lossless', '--TSRCdisableLL=1', '--Log2MaxTbSize=5']),
                  ('no_ts', '420', 'intra', ['--TransformSkip=0', '--BDPCM=0'])]
    if args.cases:
        cases = [c for c in cases if c[0] in args.cases.split(',')]
    report = []
    for name, chroma, config, extra in cases:
        if name in ('lossless', 'tsrc_off'):
            # Adapt the repository's legacy cfg/lossless/lossless.cfg to current option names.
            extra += ['--DepQuant=0', '--RDOQ=0', '--RDOQTS=0', '--SBT=0', '--MTS=0',
                      '--IntraLFNSTISlice=0', '--IntraLFNSTPBSlice=0', '--InterLFNST=0',
                      '--JointCbCr=0', '--DeblockingFilterDisable=1', '--SAO=0', '--ALF=0',
                      '--AlfImprovements=0', '--ALFCCCM=0', '--CCALF=0', '--CCSAO=0',
                      '--BIF=0', '--ChromaBIF=0', '--InternalBitDepth=8']
        src = out / f'{name}.yuv'
        rng = random.Random(381)
        with src.open('wb') as f:
            for frame in range(2):
                for comp in range(3):
                    size = 64 if comp == 0 or chroma == '444' else 32
                    for y in range(size):
                        for x in range(size):
                            # Mixture of repeated text-like edges, gradients, and low noise.
                            base = 35 + 150 * (((x + 2 * frame) // 7 + y // 9) % 2)
                            if y >= size // 2: base = 60 + (x * 2 + y + frame) % 100
                            f.write(bytes([max(0, min(255, base + rng.randrange(-5, 6)))]))
        common = ['-c', str(root / f'cfg/encoder_{config}_nx2.cfg'), '-i', str(src),
                  '--SourceWidth=64', '--SourceHeight=64', '-fr', '30', '-f', '2', '-q', '22',
                  '--InputBitDepth=8', '--InternalBitDepth=10', f'--InputChromaFormat={chroma}',
                  '--SEIDecodedPictureHash=1', '--TemporalSubsampleRatio=1',
                  *(['--CCSAO=0'] if chroma == '444' else []), *extra]
        hashes = {}
        for variant in ('original', 'off', 'on'):
            exe = getattr(args, variant).resolve()
            bit = out / f'{name}.{variant}.bin'
            env = {k: v for k, v in os.environ.items() if not k.startswith('TS_PRED_')}
            stats = out / f'{name}.csv'
            if variant == 'on':
                env.update(TS_PRED_STATS=str(stats), TS_PRED_SEQUENCE=name,
                           TS_PRED_CONFIGURATION=config, TS_PRED_QP='22',
                           TS_PRED_DEBUG=str(out / f'{name}.debug.csv'), TS_PRED_DEBUG_CGS='2')
            cmd = [str(exe), *common, '-b', str(bit), '-o', '/dev/null']
            with (out / f'{name}.{variant}.log').open('w', encoding='utf-8') as log:
                result = subprocess.run(cmd, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f'{name}/{variant} failed; see {out / (name + "." + variant + ".log")}')
            hashes[variant] = hashlib.sha256(bit.read_bytes()).hexdigest()
        assert len(set(hashes.values())) == 1, (name, hashes)
        cmd = [str(args.decoder.resolve()), '-b', str(out / f'{name}.on.bin'), '-o', '/dev/null', '-dph', '1']
        with (out / f'{name}.decode.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(cmd, cwd=root, stdout=log, stderr=subprocess.STDOUT)
        decode = (out / f'{name}.decode.log').read_text(encoding='utf-8')
        decode_ok = result.returncode == 0 and '(OK)' in decode and 'ERROR' not in decode and 'MISMATCH' not in decode
        if not decode_ok:
            # Distinguish an existing anchor decoding defect from observer corruption.
            cmd[cmd.index('-b') + 1] = str(out / f'{name}.original.bin')
            with (out / f'{name}.original.decode.log').open('w', encoding='utf-8') as log:
                original_decode = subprocess.run(cmd, cwd=root, stdout=log, stderr=subprocess.STDOUT)
            assert name == 'ai444' and original_decode.returncode == result.returncode != 0, name
        with (out / f'{name}.csv').open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            rates = [int(r[f'pred{m}_rate']) for m in range(6)]
            assert int(r['oracle_rate']) == min(rates)
            assert rates[1] == int(r['pred1_path_rate']) == int(r['current_pred_rate'])
            assert sum(int(r[f'pred1_{k}_count']) for k in ['hit', 'under', 'over']) == int(r['num_coeff'])
        report.append(dict(case=name, hashes=hashes, cg_count=len(rows), decode_hash_ok=decode_ok,
                           decode_issue=None if decode_ok else 'Original anchor 444 chroma mismatch also reproduced',
                           sizes=sorted({(int(r['TU_width']), int(r['TU_height'])) for r in rows})))
        print(name, 'bit-exact;', 'decoded hash OK;' if decode_ok else 'ANCHOR decode mismatch;', len(rows), 'CGs', flush=True)
    assert all(r['cg_count'] or r['case'] in ('no_ts', 'tsrc_off') for r in report), 'Vacuous TS case'
    report_path = out / 'validation.json'
    if args.cases and report_path.exists():
        old = json.loads(report_path.read_text(encoding='utf-8'))
        report = [r for r in old if r['case'] not in args.cases.split(',')] + report
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
