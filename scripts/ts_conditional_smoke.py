#!/usr/bin/env python3
"""Short correctness tests only, not a CTC batch runner or RD benchmark."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile
import batch_test as batch
from ts_predictor_naming import R6_MODE_NUMBERS

MODES = ('current', 'directional', 'q32', 'conf2', 'prev', 'ewma', 'q32_ewma')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--encoder', type=Path, default=Path('build/ts-conditional/bin/EncoderApp'))
    p.add_argument('--decoder', type=Path, default=Path('build/ts-conditional/bin/DecoderApp'))
    p.add_argument('--anchor', type=Path, default=Path('build/ts-anchor/bin/EncoderApp'))
    p.add_argument('--off', type=Path, help='Newly rebuilt macro-OFF encoder for bit-exact regression')
    p.add_argument('--out', type=Path, default=Path('runs/ts_conditional_smoke'))
    p.add_argument('--jobs', type=int, default=3)
    revision = p.add_mutually_exclusive_group()
    revision.add_argument('--r2', action='store_true', help='Test the four R2 modes instead of revision1')
    revision.add_argument('--r3', action='store_true', help='Test R3 plus all old modes for regression')
    revision.add_argument('--r4', action='store_true', help='Test R4 plus all old modes for regression')
    revision.add_argument('--r5', action='store_true', help='Test two R5 modes plus all old modes for regression')
    revision.add_argument('--r6', action='store_true', help='R6 plus Current/R3; all legacy modes also checked at QP0')
    p.add_argument('--legacy-encoder', type=Path, help='Check unchanged old fixed modes against this preserved binary')
    args = p.parse_args()
    modes = ('current', 'nopred', 'gradient', 'directional', 'r2_modal', 'r2_risk', 'r2_cn_log', 'r2_cn_frac') if args.r2 else MODES
    experiments = modes[4:] if args.r2 else modes[2:]
    if args.r3:
        experiments = ('r3_risk_guard', 'r3_risk_guard_y', 'r3_cn_guard', 'r3_cn_guard_y')
        modes = ('current', 'nopred', 'gradient', 'directional', 'q32', 'conf2', 'prev', 'ewma', 'q32_ewma',
                 'r2_modal', 'r2_risk', 'r2_cn_log', 'r2_cn_frac', *experiments)
    if args.r4:
        experiments = ('r4_identity_only', 'r4_magnitude_only', 'r4_guard_rescue',
                       'r4_directional_risk', 'r4_causal_models', 'r4_signed_plane')
        modes = tuple(m for m in batch._TS_PREDICTOR_MODES if not m.startswith(('r5_', 'r6_', 'rate_')))
    if args.r5:
        experiments = ('r5_margin_first', 'r5_current_veto')
        modes = tuple(m for m in batch._TS_PREDICTOR_MODES if not m.startswith(('r6_', 'rate_')))
    if args.r6:
        experiments = tuple(R6_MODE_NUMBERS)
        modes = ('current', 'r3_risk_guard', *experiments)
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    src = out/'synthetic_input.yuv'
    rng = random.Random(381)
    payload = bytearray()
    for frame in range(2):
        for comp in range(3):
            size = 64 if comp == 0 else 32
            for y in range(size):
                for x in range(size):
                    base = 35 + 150 * (((x + 2 * frame)//7 + y//9) % 2)
                    if y >= size//2:
                        base = 60 + (x*2+y+frame) % 100
                    payload.append(max(0, min(255, base+rng.randrange(-5, 6))))
    if not src.exists() or src.read_bytes() != payload:
        src.write_bytes(payload)
    os.environ['TS_COND_TRACE'] = '1'
    # Force slice QP for boundary identity checks; still run normal RD mode decisions.
    common = ['--IntraQPOffset=0', '--BDPCM=0']
    lossless = ['--CostMode=lossless', '--Log2MaxTbSize=5', '--DepQuant=0', '--RDOQ=0',
                '--RDOQTS=0', '--SBT=0', '--MTS=0', '--IntraLFNSTISlice=0',
                '--IntraLFNSTPBSlice=0', '--InterLFNST=0', '--JointCbCr=0',
                '--DeblockingFilterDisable=1', '--SAO=0', '--ALF=0', '--AlfImprovements=0',
                '--ALFCCCM=0', '--CCALF=0', '--CCSAO=0', '--BIF=0', '--ChromaBIF=0',
                '--InternalBitDepth=8', '--BDPCM=0']
    cases = [('q22', 22, common), ('q32', 32, common), ('q33', 33, common),
             ('no_ts', 22, common+['--TransformSkip=0']),
             ('q0', 0, common+['--TransformSkipLog2MaxSize=5']),
             ('lossless', 22, lossless+['--TSRCdisableLL=0']),
             ('tsrc_off', 22, lossless+['--TSRCdisableLL=1']),
             ('dqp', 32, common+['--AdaptiveQP=1', '--MaxQPAdaptationRange=4']),
             ('bdpcm', 22, ['--BDPCM=1']),
             ('lb', 22, []), ('ra', 22, [])]
    if args.r3 or args.r4 or args.r5 or args.r6:
        cases.extend([('q27', 27, common), ('q37', 37, common)])
    jobs = []
    for case, qp, extra in cases:
        case_modes = tuple(m for m in batch._TS_PREDICTOR_MODES if not m.startswith('rate_')) if args.r6 and case == 'q0' else modes
        for mode in ('anchor', *(['off'] if args.off else []), *case_modes):
            cfg = root/'cfg/encoder_intra_nx2.cfg'
            if case == 'lb':
                cfg = root/'scripts/HHI测试cfg/LBeu/cfg/encoder_lowdelay_nx2High.cfg'
            elif case == 'ra':
                cfg = root/'cfg/encoder_randomaccess_nx2.cfg'
            job = batch._make_job(order=len(jobs), name=f'{case}_{mode}', repo_root=root, cwd=root,
                encoder=(args.anchor if mode == 'anchor' else args.off if mode == 'off' else args.encoder).resolve(),
                decoder=args.decoder.resolve(), cfgs=[cfg],
                sequence_cfg=root/'cfg/per-sequence/BasketballDrill.cfg', input_path=src,
                qp=qp, frames=2,
                extra_args=['--SourceWidth=64', '--SourceHeight=64', '-fr', '30', '--InputBitDepth=8',
                            '--InternalBitDepth=10', '--InputChromaFormat=420', '--TemporalSubsampleRatio=1',
                            '--SEIDecodedPictureHash=1', *extra],
                decoder_args=['-dph', '1'], decode_md5=True, xlsm_tag=None, run_dir=out, overwrite=False)
            jobs.append(replace(job, no_recon=True, fixed_predictor=None if mode in ('anchor','off') else mode))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(batch._run_one, jobs))
    batch._write_summary(out/'summary.csv', rows)
    assert all(r.get('error_info') == 'pass' for r in rows), [(r['name'],r['error_info']) for r in rows if r.get('error_info') != 'pass']
    hashes = {j.name: hashlib.sha256(j.bitstream.read_bytes()).hexdigest() for j in jobs}
    traces = {}
    activity = []
    totals = {m: {} for m in experiments} if args.r3 or args.r4 or args.r5 or args.r6 else {}
    for job in jobs:
        # Keep exact final-CG state, score, budget and coefficient hash comparison.
        enc = Path(job.encode_log).read_text(errors='replace')
        dec = Path(job.decode_log).read_text(errors='replace')
        a = re.findall(r'TS_COND [^\r\n]*', enc)
        b = re.findall(r'TS_COND [^\r\n]*', dec)
        assert a == b, (job.name, 'encoder/decoder state mismatch', len(a), len(b))
        if job.fixed_predictor in ('prev', 'ewma', 'q32_ewma', 'r2_cn_log', 'r2_cn_frac', 'r3_cn_guard', 'r3_cn_guard_y'):
            assert all('state=0 ' in line and 'selected=1 ' in line for line in a if 'cg=0 ' in line)
        assert re.findall(r'TS_R3_CERT [^\r\n]*', enc) == re.findall(r'TS_R3_CERT [^\r\n]*', dec), job.name
        assert 'TS_R3_STATS ' not in dec, job.name
        assert 'TS_R4_STATS ' not in dec, job.name
        assert 'TS_R5_STATS ' not in dec, job.name
        assert 'TS_R6_STATS ' not in dec, job.name
        if (args.r3 or args.r4 or args.r5 or args.r6) and job.fixed_predictor in experiments:
            stats_prefix = 'TS_R6' if args.r6 else 'TS_R5' if args.r5 else 'TS_R4' if args.r4 else 'TS_R3'
            header = re.findall(stats_prefix + r'_STATS_HEADER ([^\r\n]*)', enc)
            lines = re.findall(stats_prefix + r'_STATS ([^\r\n]*)', enc)
            assert bool(header) == bool(lines) and len(header) <= 1, job.name
            if header:
                columns = header[0].split(',')
                for line in lines:
                    values = list(map(int, line.split(',')))
                    assert len(values) == len(columns), job.name
                    row = dict(zip(columns, values))
                    if args.r6:
                        assert row['r3_proposed'] == row['r3_accepted'] + row['r3_rejected']
                        assert row['active_count'] == sum(row[f'support{i}'] for i in range(6))
                        assert row['active_count'] == sum(row[k] for k in ('hit','under','over'))
                        assert row['active_count'] == sum(row[k] for k in ('modified0','modified1','modified2','modified_high'))
                        assert sum(row[f'support{i}'] for i in (3,4,5)) == sum(row[k] for k in ('dense_no_proposal','dense_rejected','dense_accepted'))
                        assert row['remap_vs_r3'] <= row['p_vs_r3'] <= row['active_count']
                        assert row['remap_vs_r3'] <= row['active_nonzero']
                        assert row['active_count'] == sum(row[k] for k in ('p_current','p_identity','p_other'))
                        assert row['active_count'] == sum(row[k] for k in ('current_hits0','current_hits1','current_hits_multi'))
                        assert row['lu_only'] == row['lu_equal'] + row['lu_unequal']
                        assert row['remap_vs_r3'] == sum(row[f'remap_vs_r3_n{i}'] for i in range(6))
                        assert row['remap_vs_r3_n0'] == 0
                        if row['policy'] <= 28:
                            assert row['remap_vs_r3_n1'] == row['remap_vs_r3_n2'] == 0
                        else:
                            assert row['remap_vs_r3_n3'] == row['remap_vs_r3_n4'] == row['remap_vs_r3_n5'] == 0
                        if row['policy'] == 26:
                            assert row['fallback_no_proposal'] == 0
                        if row['policy'] == 29:
                            assert row['lu_p_vs_r3'] == row['lu_remap_vs_r3'] == 0
                        if not row['scope_enabled_cg']:
                            assert row['remap_vs_r3'] == 0
                    elif args.r4 or args.r5:
                        assert row['r3_proposed'] == row['r3_accepted'] + row['r3_rejected']
                        assert row['active_count'] == sum(row[f'support{i}'] for i in range(6))
                        assert row['active_count'] == sum(row[k] for k in ('p_current', 'p_identity', 'p_other'))
                        assert row['active_count'] == sum(row[k] for k in ('r3_current', 'r3_identity', 'r3_other'))
                        assert row['accepted'] <= row['attempted']
                        if args.r4:
                            assert row['rescue'] <= row['accepted']
                        else:
                            assert row['veto'] == row['veto_identity'] + row['veto_other']
                            if row['policy'] == 24:
                                assert row['veto'] == row['accepted'] == row['p_vs_r3']
                                assert row['accepted_parent_reordered'] == row['fallback_rescued'] == 0
                            else:
                                assert row['p_vs_r3'] == row['accepted_parent_reordered'] + row['fallback_rescued']
                    else:
                        assert row['local_proposed'] == row['local_accept'] + row['local_reject']
                    if not row['scope_enabled_cg']:
                        assert row['remap_different'] == 0
                        if not args.r4 and not args.r5 and not args.r6:
                            assert row['nopred_cg'] == row['local_proposed'] == 0
                    if job.fixed_predictor.endswith('_y') and row['component'] != 0:
                        assert row['scope_enabled_cg'] == 0
                    if 'cn_guard' in job.fixed_predictor:
                        assert row['state_positive_cg'] == row['nopred_cg'] + row['certificate_block_cg']
                        assert sum(row[k] for k in ('gain_positive_cg','gain_zero_cg','gain_negative_cg')) == row['scope_enabled_cg']
                        assert sum(row[k] for k in ('next_certificate_positive_cg','next_certificate_zero_cg','next_certificate_negative_cg')) == row['scope_enabled_cg']
                    activity.append(dict(job=job.name, mode=job.fixed_predictor, **row))
                    for key in columns[9:]:
                        totals[job.fixed_predictor][key] = totals[job.fixed_predictor].get(key, 0) + row[key]
        traces[job.name] = dict(cgs=len(a), switches=sum('selected=3 ' in l or 'selected=0 ' in l for l in a),
                               remap_changes=sum(int(re.search(r'mapped=(\d+)',l)[1]) for l in a))
    for case, qp, extra in cases:
        assert hashes[case+'_current'] == hashes[case+'_anchor'], case
        if args.off:
            assert hashes[case+'_off'] == hashes[case+'_anchor'], case
    assert len({hashes['no_ts_'+m] for m in modes}) == 1
    assert len({hashes['tsrc_off_'+m] for m in modes}) == 1
    if not args.r2 and not args.r3 and not args.r4 and not args.r5 and not args.r6:
        for case in ('q22','q32'):
            assert hashes[case+'_q32'] == hashes[case+'_directional'], case
            assert hashes[case+'_q32_ewma'] == hashes[case+'_ewma'], case
        for mode in ('q32','q32_ewma'):
            assert hashes['q33_'+mode] == hashes['q33_current'], mode
    for mode in experiments:
        assert sum(traces[c+'_'+mode]['remap_changes'] for c, _, _ in cases) > 0, (mode,'vacuous')
    # Debug observation must not affect coding. Replay five active q0 cases without trace.
    with tempfile.TemporaryDirectory(prefix='ts-conditional-no-trace-') as d:
        for mode in experiments:
            job = next(j for j in jobs if j.name == 'q0_'+mode)
            command = json.loads(job.bitstream.with_suffix('.done.json').read_text())['command']
            bitstream = Path(d)/(mode+'.bin')
            command[command.index('-b')+1] = str(bitstream)
            env = batch._job_env(job)
            env.pop('TS_COND_TRACE', None)
            env['TS_R2_STATS'] = '0'
            env['TS_R3_STATS'] = '0'
            env['TS_R4_STATS'] = '0'
            env['TS_R5_STATS'] = '0'
            env['TS_R6_STATS'] = '0'
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            assert result.returncode == 0, (mode, result.stderr[-2000:])
            assert 'TS_COND ' not in result.stderr
            assert 'TS_R3_' not in result.stderr
            assert 'TS_R4_' not in result.stderr
            assert 'TS_R5_' not in result.stderr
            assert 'TS_R6_' not in result.stderr
            assert hashlib.sha256(bitstream.read_bytes()).hexdigest() == hashes['q0_'+mode], mode
        if args.legacy_encoder:
            legacy_modes = tuple(m for m in modes if m not in experiments) if args.r3 or args.r4 or args.r5 or args.r6 else ('nopred','gradient','directional')
            if args.r6:
                legacy_modes = tuple(m for m in batch._TS_PREDICTOR_MODES if m not in experiments)
            for mode in legacy_modes:
                job = next(j for j in jobs if j.name == 'q0_'+mode)
                command = json.loads(job.bitstream.with_suffix('.done.json').read_text())['command']
                command[0] = str(args.legacy_encoder.resolve())
                bitstream = Path(d)/('legacy_'+mode+'.bin')
                command[command.index('-b')+1] = str(bitstream)
                result = subprocess.run(command, cwd=root, env=batch._job_env(job), capture_output=True, text=True)
                assert result.returncode == 0, result.stderr[-2000:]
                assert hashlib.sha256(bitstream.read_bytes()).hexdigest() == hashes['q0_'+mode], mode
    assert list(out.rglob('*.yuv')) == [src]
    if args.r3:
        for mode, values in totals.items():
            assert values.get('remap_different', 0) > 0, (mode, 'no actual effect')
            if 'risk_guard' in mode:
                assert values['local_accept'] > 0 and values['local_reject'] > 0, (mode, 'guard not covered')
            else:
                assert values['nopred_cg'] > 0 and values['certificate_block_cg'] > 0, (mode, 'certificate not covered')
        with (out/'r3_activity.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(activity[0]))
            writer.writeheader(); writer.writerows(activity)
    if args.r4 or args.r5 or args.r6:
        for mode, values in totals.items():
            assert values.get('remap_different', 0) > 0, (mode, 'no actual effect versus Current')
        with (out/('r6_activity.csv' if args.r6 else 'r5_activity.csv' if args.r5 else 'r4_activity.csv')).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(activity[0]))
            writer.writeheader(); writer.writerows(activity)
    (out/'validation.json').write_text(json.dumps(dict(hashes=hashes, traces=traces, jobs=len(rows),
        state_trace_equal=True, decode_hash_all_pass=True, current_anchor_exact=True,
        macro_off_anchor_exact=bool(args.off), trace_off_bit_exact_checks=len(experiments),
        legacy_mode_checks=len(legacy_modes) if args.legacy_encoder else 0,
        revision='r6' if args.r6 else 'r5' if args.r5 else 'r4' if args.r4 else 'r3' if args.r3 else 'r2' if args.r2 else 'r1',
        r3_certificate_trace_equal=args.r3, r3_stats_rows=len(activity) if args.r3 else 0,
        r3_stats=totals if args.r3 else {}, activity_rows=len(activity), activity_totals=totals,
        r6_incremental_activity_covered=all(totals[m].get('remap_vs_r3',0)>0 for m in experiments) if args.r6 else None,
        r6_same_R3_cases={m:[c for c,_,_ in cases if hashes[c+'_'+m]==hashes[c+'_r3_risk_guard']] for m in experiments} if args.r6 else {},
        r5_incremental_activity_covered=all(totals[m].get('remap_vs_r3',0)>0 for m in experiments) if args.r5 else None,
        r5_same_R3_cases={m:[c for c,_,_ in cases if hashes[c+'_'+m]==hashes[c+'_r3_risk_guard']] for m in experiments} if args.r5 else {}),indent=2)+'\n')
    print(f'PASS {len(rows)} short encodes: decoded hashes, state traces, boundary identities and nonvacuous switching')
    if args.r5 or args.r6:
        for mode in experiments:
            print(f"Incremental check {mode}: remap_vs_r3={totals[mode].get('remap_vs_r3',0)}; "
                  "zero means new mechanism coverage is NOT demonstrated by this smoke, even if legacy R3 is active")


if __name__ == '__main__':
    main()
