#!/usr/bin/env python3
"""R10 correctness/causality and optional serial cache timing. Not BD-rate evidence."""
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
from ts_predictor_naming import R10_MODE_NUMBERS

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--encoder',type=Path,default=Path('build/ts-r10/bin/EncoderApp'))
    p.add_argument('--decoder',type=Path,default=Path('build/ts-r10/bin/DecoderApp'))
    p.add_argument('--native-test',type=Path,default=Path('build/ts-r10/bin/TsRateCodecTest'))
    p.add_argument('--legacy',type=Path,default=Path('build/ts-r9/bin/EncoderApp'))
    p.add_argument('--off',type=Path)
    p.add_argument('--anchor-off',type=Path,default=Path('build/ts-r9-off/bin/EncoderApp'))
    p.add_argument('--out',type=Path,default=Path('runs/ts_r10_smoke'))
    p.add_argument('--jobs',type=int,default=8)
    p.add_argument('--benchmark-repeats',type=int,default=0,help='Optional serial paired AI0 synthetic timing; not general speed claim')
    p.add_argument('--skip-legacy',action='store_true',help='Focused rerun only; never reports old-mode bit-exact coverage')
    args=p.parse_args(); root=Path(__file__).resolve().parents[1]; out=args.out.resolve(); out.mkdir(parents=True,exist_ok=True)
    for key in ('TS_FIXED_PREDICTOR','TS_RATE_SHADOW','TS_RATE_RDOQ_SHADOW','TS_COND_TRACE'):
        os.environ.pop(key,None)
    for name in ('R2','R3','R4','R5','R6','R8','R9','R10'):
        os.environ[f'TS_{name}_STATS']='0'; os.environ[f'TS_{name}_TRACE']='0'
    modes=tuple(R10_MODE_NUMBERS); parent='r9_expert_integer'; native={}
    for cache in ('0','1'):
        for m in (parent,*modes):
            r=subprocess.run([str(args.native_test.resolve())],env={**os.environ,'TS_FIXED_PREDICTOR':m,'TS_R10_CACHE':cache},
                             check=True,text=True,capture_output=True)
            native[f'{m}/cache{cache}']=r.stdout.strip(); print(r.stdout.strip(),flush=True)
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
    jobs=[]; keyed={}; allrows=[]
    def add(case,label,encoder,mode,overwrite=False):
        cname,qp,cfg,extra=case
        j=batch._make_job(order=len(jobs),name=cname+'_'+label,repo_root=root,cwd=root,
            encoder=encoder.resolve(),decoder=args.decoder.resolve(),cfgs=[root/cfg],
            sequence_cfg=root/'cfg/per-sequence/BasketballDrill.cfg',input_path=src,qp=qp,frames=2,
            extra_args=['--SourceWidth=64','--SourceHeight=64','-fr','30','--InputBitDepth=8','--InternalBitDepth=10',
                        '--TemporalSubsampleRatio=1','--SEIDecodedPictureHash=1',*extra],
            decoder_args=['-dph','1'],decode_md5=True,xlsm_tag=None,run_dir=out,overwrite=overwrite)
        j=replace(j,no_recon=True,fixed_predictor=mode); jobs.append(j); keyed[(cname,label)]=j
        return j
    def run(todo):
        with ThreadPoolExecutor(max_workers=args.jobs) as pool: rows=list(pool.map(batch._run_one,todo))
        allrows.extend(rows); batch._write_summary(out/'summary.csv',allrows)
        if any(r['error_info']!='pass' for r in rows): raise RuntimeError('Smoke failed; inspect summary.csv')
    os.environ.update(TS_R10_STATS='1',TS_R10_TRACE='1',TS_R10_CACHE='0')
    for case in cases:
        for m in ('current',parent,*modes): add(case,m,args.encoder,m)
        if not args.skip_legacy:
            for m in ('current',parent): add(case,'legacy_'+m,args.legacy,m)
        if args.off:
            add(case,'off',args.off,None); add(case,'anchor_off',args.anchor_off,None)
    old=[] if args.skip_legacy else [m for m in batch._TS_PREDICTOR_MODES if m not in ('current',parent,*modes)]
    for m in old:
        add(cases[0],m,args.encoder,m); add(cases[0],'legacy_'+m,args.legacy,m)
    run(jobs[:]); traces=0
    for (case,label),j in keyed.items():
        if label.startswith('legacy_'): assert sha(j.bitstream)==sha(keyed[(case,label[7:])].bitstream),(case,label)
        if label=='off': assert sha(j.bitstream)==sha(keyed[(case,'current')].bitstream)
        if label=='anchor_off': assert sha(j.bitstream)==sha(keyed[(case,'off')].bitstream)
        if label in modes:
            read=lambda path:[l for l in path.read_text(errors='replace').splitlines() if l.startswith('TS_R10_TRACE ')]
            enc,dec=read(j.encode_log),read(j.decode_log); assert enc==dec,(case,label,'trace')
            traces+=len(enc)
    assert traces>0
    for m in modes: assert sha(keyed[('no_ts',m)].bitstream)==sha(keyed[('no_ts','current')].bitstream)
    for cache in ('0','1'):
        os.environ.update(TS_R10_STATS='0',TS_R10_TRACE='0',TS_R10_CACHE=cache)
        start=len(jobs)
        for case in cases:
            for m in (parent,*modes): add(case,f'quiet{cache}_{m}',args.encoder,m)
        run(jobs[start:])
        for case,*_ in cases:
            for m in (parent,*modes):
                assert sha(keyed[(case,f'quiet{cache}_{m}')].bitstream)==sha(keyed[(case,m)].bitstream),(case,m,cache)
    timing=[]
    # Warmup both variants, then alternate pair order; no concurrent smoke jobs.
    if args.benchmark_repeats:
        for repeat in range(-1,args.benchmark_repeats):
            for cache in (('0','1') if repeat%2==0 else ('1','0')):
                os.environ['TS_R10_CACHE']=cache
                j=add(cases[1],f'timing_{repeat}_{cache}',args.encoder,parent,overwrite=True)
                row=batch._run_one(j); assert row['error_info']=='pass'
                assert sha(j.bitstream)==sha(keyed[('ai0',parent)].bitstream)
                if repeat>=0: timing.append(dict(repeat=repeat,cache=int(cache),encode_seconds=row['encode_seconds']))
    changes={m:[c for c,*_ in cases if sha(keyed[(c,m)].bitstream)!=sha(keyed[(c,parent)].bitstream)] for m in modes}
    result=dict(revision='R10-20260928-v1',tasks=len(jobs),legacy_modes_bit_exact=0 if args.skip_legacy else len(old)+2,
        master_off_bit_exact=bool(args.off),no_ts_bit_exact=True,stats_off_bit_exact=True,cache_bit_exact=True,
        matching_traces=traces,changed_vs_r9_9=changes,native=native,serial_synthetic_timing=timing,bdrate_measured=False,
        binary_sha256={str(x):sha(x) for x in (args.encoder,args.decoder,args.legacy)},
        bitstreams={f'{c}/{m}':sha(j.bitstream) for (c,m),j in keyed.items()})
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('native','bitstreams')},indent=2))

if __name__=='__main__': main()
