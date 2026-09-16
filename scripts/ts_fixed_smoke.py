#!/usr/bin/env python3
"""Short closed-loop coding checks. Synthetic inputs are NOT RD evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
import batch_test as batch


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--encoder', type=Path, default=Path('build/ts-fixed/bin/EncoderApp'))
    p.add_argument('--decoder', type=Path, default=Path('build/ts-fixed/bin/DecoderApp'))
    p.add_argument('--anchor', type=Path, required=True, help='Untouched original EncoderApp')
    p.add_argument('--off', type=Path, help='Rebuilt macro-OFF EncoderApp for regression')
    p.add_argument('--out', type=Path, default=Path('runs/ts_fixed_smoke'))
    p.add_argument('--jobs', type=int, default=2)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    src = out / 'synthetic_input.yuv'
    rng = random.Random(381)
    payload = bytearray()
    for frame in range(2):
        for comp in range(3):
            size = 64 if comp == 0 else 32
            for y in range(size):
                for x in range(size):
                    base = 35 + 150 * (((x + 2 * frame) // 7 + y // 9) % 2)
                    if y >= size // 2:
                        base = 60 + (x * 2 + y + frame) % 100
                    payload.append(max(0, min(255, base + rng.randrange(-5, 6))))
    if not src.is_file() or src.read_bytes() != payload:
        src.write_bytes(payload)
    lossless = ['--CostMode=lossless', '--Log2MaxTbSize=5', '--DepQuant=0', '--RDOQ=0',
                '--RDOQTS=0', '--SBT=0', '--MTS=0', '--IntraLFNSTISlice=0',
                '--IntraLFNSTPBSlice=0', '--InterLFNST=0', '--JointCbCr=0',
                '--DeblockingFilterDisable=1', '--SAO=0', '--ALF=0', '--AlfImprovements=0',
                '--ALFCCCM=0', '--CCALF=0', '--CCSAO=0', '--BIF=0', '--ChromaBIF=0',
                '--InternalBitDepth=8']
    cases = [('ai', 'intra', []), ('lb', 'lowdelay', []),
             ('lb_high', 'lowdelay', [], True),
             ('bdpcm', 'intra', ['--BDPCM=1']),
             ('lossless', 'intra', lossless + ['--TSRCdisableLL=0']),
             ('tsrc_off', 'intra', lossless + ['--TSRCdisableLL=1']),
             ('no_ts', 'intra', ['--TransformSkip=0', '--BDPCM=0'])]
    jobs = []
    for entry in cases:
        case, config, extra = entry[:3]
        cfg = root / f'cfg/encoder_{config}_nx2.cfg'
        if len(entry) == 4:
            cfg = root / 'scripts/HHI测试cfg/LBeu/cfg/encoder_lowdelay_nx2High.cfg'
        for mode in ['anchor', *(['off'] if args.off else []), 'current', 'nopred', 'gradient', 'directional']:
            exe = args.anchor if mode == 'anchor' else args.off if mode == 'off' else args.encoder
            job = batch._make_job(order=len(jobs), name=f'{case}_{mode}', repo_root=root,
                                  cwd=root, encoder=exe.resolve(), decoder=args.decoder.resolve(),
                                  cfgs=[cfg], sequence_cfg=root / 'cfg/per-sequence/BasketballDrill.cfg',
                                  input_path=src, qp=22, frames=2,
                                  extra_args=['--SourceWidth=64', '--SourceHeight=64', '-fr', '30',
                                              '--InputBitDepth=8', '--InternalBitDepth=10',
                                              '--InputChromaFormat=420', '--TemporalSubsampleRatio=1',
                                              '--SEIDecodedPictureHash=1', *extra],
                                  decoder_args=['-dph', '1'], decode_md5=True, xlsm_tag=None,
                                  run_dir=out, overwrite=False)
            jobs.append(replace(job, no_recon=True,
                                fixed_predictor=None if mode in ('anchor', 'off') else mode))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(batch._run_one, jobs))
    batch._write_summary(out / 'summary.csv', rows)
    failed = [r for r in rows if r.get('error_info') != 'pass']
    assert not failed, [(r['name'], r['error_info']) for r in failed]
    hashes = {j.name: hashlib.sha256(j.bitstream.read_bytes()).hexdigest() for j in jobs}
    for entry in cases:
        case = entry[0]
        assert hashes[f'{case}_current'] == hashes[f'{case}_anchor'], case
        if args.off:
            assert hashes[f'{case}_off'] == hashes[f'{case}_anchor'], case
        if case in ('no_ts', 'tsrc_off'):
            assert len({hashes[f'{case}_{m}'] for m in ('current', 'nopred', 'gradient', 'directional')}) == 1, case
    for mode in ('nopred', 'gradient', 'directional'):
        assert any(hashes[f'{c}_{mode}'] != hashes[f'{c}_current'] for c in ('ai', 'lb', 'lossless')), mode
    assert list(out.rglob('*.yuv')) == [src], 'Unexpected reconstructed video'
    (out / 'validation.json').write_text(json.dumps({'hashes': hashes, 'jobs': len(rows),
        'decode_hash_all_pass': True, 'current_bit_exact': True,
        'macro_off_bit_exact': bool(args.off), 'no_reconstructed_video': True}, indent=2))
    print(f'PASS: {len(rows)} coding jobs; current bit-exact, decode hashes pass, no reconstruction output')


if __name__ == '__main__':
    main()
