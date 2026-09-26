#!/usr/bin/env python3
"""R8 small correctness tests. Synthetic inputs, NOT CTC or BD-rate evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import batch_test as batch
from ts_predictor_naming import R8_MODE_NUMBERS


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--encoder',type=Path,default=Path('build/ts-r8/bin/EncoderApp'))
    p.add_argument('--decoder',type=Path,default=Path('build/ts-r8/bin/DecoderApp'))
    p.add_argument('--native-test',type=Path,default=Path('build/ts-r8/bin/TsRateCodecTest'))
    p.add_argument('--quant-test',type=Path,help='Optional new native quantization stress-test executable')
    p.add_argument('--legacy',type=Path,default=Path('build/ts-r7/bin/EncoderApp'))
    p.add_argument('--off',type=Path,help='Optional freshly compiled master-OFF encoder')
    p.add_argument('--anchor-off',type=Path,default=Path('build/ts-rate-off/bin/EncoderApp'))
    p.add_argument('--out',type=Path,default=Path('runs/ts_r8_smoke'))
    p.add_argument('--jobs',type=int,default=6)
    args = p.parse_args()
    root=Path(__file__).resolve().parents[1]; out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    for key in ('TS_RATE_SHADOW','TS_RATE_RDOQ_SHADOW','TS_COND_TRACE','TS_FIXED_PREDICTOR'):
        os.environ.pop(key,None)
    os.environ['TS_R8_TRACE']='1'; os.environ['TS_R8_STATS']='1'
    native={}
    for m in R8_MODE_NUMBERS:
        r=subprocess.run([str(args.native_test.resolve())],env={**os.environ,'TS_FIXED_PREDICTOR':m},
                         check=True,text=True,capture_output=True)
        native[m]=r.stdout.strip(); print(r.stdout.strip(),flush=True)
    quant={}
    if args.quant_test:
        for m in ('r8_r3_dual_quant','r8_raw_dual_quant'):
            r=subprocess.run([str(args.quant_test.resolve())],env={**os.environ,'TS_FIXED_PREDICTOR':m},
                             check=True,text=True,capture_output=True)
            quant[m]=r.stdout.strip(); print(r.stdout.strip(),flush=True)
    rng=random.Random(381); data=bytearray()
    for f in range(2):
        for size in (64,32,32):
            for y in range(size):
                for x in range(size):
                    base=35+150*(((x+2*f)//7+y//9)%2) if y<size//2 else 60+(x*2+y+f)%100
                    data.append(max(0,min(255,base+rng.randrange(-5,6))))
    src=out/'synthetic.yuv'
    if not src.exists() or src.read_bytes()!=data: src.write_bytes(data)
    cases=[('ai22',22,'cfg/encoder_intra_nx2.cfg',[]),
           ('ai0',0,'cfg/encoder_intra_nx2.cfg',['--TransformSkipLog2MaxSize=5']),
           ('lb22',22,'scripts/HHI测试cfg/LBeu/cfg/encoder_lowdelay_nx2High.cfg',[]),
           ('ra37',37,'cfg/encoder_randomaccess_nx2.cfg',[]),
           ('no_ts',22,'cfg/encoder_intra_nx2.cfg',['--TransformSkip=0']),
           ('bdpcm',22,'cfg/encoder_intra_nx2.cfg',['--BDPCM=1'])]
    jobs=[]; by_key={}
    def add(case,label,encoder,mode):
        cname,qp,cfg,extra=case
        j=batch._make_job(order=len(jobs),name=cname+'_'+label,repo_root=root,cwd=root,
            encoder=encoder.resolve(),decoder=args.decoder.resolve(),cfgs=[root/cfg],
            sequence_cfg=root/'cfg/per-sequence/BasketballDrill.cfg',input_path=src,qp=qp,frames=2,
            extra_args=['--SourceWidth=64','--SourceHeight=64','-fr','30','--InputBitDepth=8',
                        '--InternalBitDepth=10','--TemporalSubsampleRatio=1','--SEIDecodedPictureHash=1',*extra],
            decoder_args=['-dph','1'],decode_md5=True,xlsm_tag=None,run_dir=out,overwrite=False)
        j=replace(j,no_recon=True,fixed_predictor=mode);jobs.append(j);by_key[(cname,label)]=j
    controls=('current','r3_risk_guard','rate_raw','rate_guard')
    for case in cases:
        for m in (*controls,*R8_MODE_NUMBERS): add(case,m,args.encoder,m)
        for m in controls: add(case,'legacy_'+m,args.legacy,m)
        if args.off:
            add(case,'off',args.off,None)
            add(case,'anchor_off',args.anchor_off,None)
    # All previously registered algorithms remain bit-exact on an active case.
    old=[m for m in batch._TS_PREDICTOR_MODES if m not in (*controls,*R8_MODE_NUMBERS)]
    for m in old:
        add(cases[0],m,args.encoder,m);add(cases[0],'legacy_'+m,args.legacy,m)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool: rows=list(pool.map(batch._run_one,jobs))
    batch._write_summary(out/'summary.csv',rows)
    if any(r['error_info']!='pass' for r in rows): raise RuntimeError('Failed smoke task: see summary.csv')
    hashes={key:sha(j.bitstream) for key,j in by_key.items()}
    for (case,label),value in hashes.items():
        if label.startswith('legacy_'): assert value==hashes[(case,label[7:])],(case,label)
        if label=='off': assert value==hashes[(case,'current')],case
        if label=='anchor_off': assert value==hashes[(case,'off')],case
    for m in R8_MODE_NUMBERS: assert hashes[('no_ts',m)]==hashes[('no_ts','current')],m
    parents={1:'rate_raw',4:'r8_raw_sparse_max',8:'rate_guard',13:'r8_raw_sparse_max',
             15:'rate_raw',16:'r8_raw_sparse_max',17:'r8_raw_sparse_max',19:'r8_complete_sparse_max',
             2:'r8_raw_sparse_max',3:'r8_raw_sparse_max',5:'r8_guard_sparse_max',6:'r8_guard_sparse_max',
             7:'rate_guard',9:'rate_guard',10:'rate_guard',11:'r8_reject_nopred',12:'r8_trim_saving',
             14:'r8_mixed_raw',18:'r8_minimax',20:'r8_smoothed_dense',21:'r8_complete_sparse_max',
             22:'r8_dual_path',23:'r3_risk_guard',24:'r8_raw_sparse_max'}
    changes={m:[c for c,*_ in cases if hashes[(c,m)]!=hashes[(c,parents[n])]] for m,n in R8_MODE_NUMBERS.items()}
    # Absence on a tiny synthetic clip is a coverage warning, NOT a reason to
    # tune frozen formulas. Native/formula tests independently prove activity.
    missing_activity=[m for m,v in changes.items() if not v]
    traces=0; path_records=0
    for j in jobs:
        if j.fixed_predictor not in R8_MODE_NUMBERS: continue
        read=lambda path:[l for l in path.read_text(errors='replace').splitlines() if l.startswith(('TS_R8_TRACE ','TS_R8_PATH '))]
        enc,dec=read(j.encode_log),read(j.decode_log)
        assert enc==dec,('Writer/Reader trace mismatch',j.name)
        traces+=sum(l.startswith('TS_R8_TRACE ') for l in enc)
        path_records+=sum(l.startswith('TS_R8_PATH ') for l in enc)
    assert traces>0
    # Stats/trace disabled must not alter any algorithm decision.
    os.environ['TS_R8_TRACE']='0';os.environ['TS_R8_STATS']='0'
    start=len(jobs)
    for m in R8_MODE_NUMBERS: add(cases[0],'quiet_'+m,args.encoder,m)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool: quiet=list(pool.map(batch._run_one,jobs[start:]))
    batch._write_summary(out/'quiet_summary.csv',quiet)
    assert all(r['error_info']=='pass' for r in quiet)
    for m in R8_MODE_NUMBERS: assert sha(by_key[('ai22','quiet_'+m)].bitstream)==hashes[('ai22',m)]
    result=dict(tasks=len(jobs),all_hash_checks=True,old_modes_bit_exact=len(controls)+len(old),
                master_off_bit_exact=bool(args.off),no_ts_bit_exact=True,stats_off_bit_exact=True,
                writer_reader_matching_cg_traces=traces,changed_vs_primary=changes,native=native,
                writer_reader_matching_path_records=path_records,
                native_quant_stress=quant,
                synthetic_no_activity_warning=missing_activity,
                binary_sha256={str(x):sha(x) for x in (args.encoder,args.decoder,args.legacy,*([args.off,args.anchor_off] if args.off else []))},
                bitstreams={f'{c}/{m}':h for (c,m),h in hashes.items()},bdrate_measured=False)
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('native','binary_sha256','bitstreams')},indent=2))


if __name__=='__main__': main()
