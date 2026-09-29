#!/usr/bin/env python3
"""Bounded R11 engineering validation; no formal CTC or BD-rate claims."""
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
from ts_predictor_naming import R11_MODE_NUMBERS

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--encoder',type=Path,default=Path('build/ts-r11/bin/EncoderApp'))
    p.add_argument('--decoder',type=Path,default=Path('build/ts-r11/bin/DecoderApp'))
    p.add_argument('--native-test',type=Path,default=Path('build/ts-r11/bin/TsRateCodecTest'))
    p.add_argument('--legacy',type=Path,default=Path('build/ts-r10/bin/EncoderApp'))
    p.add_argument('--off',type=Path)
    p.add_argument('--legacy-off',type=Path,default=Path('build/ts-r10-off/bin/EncoderApp'))
    p.add_argument('--out',type=Path,default=Path('runs/ts_r11_smoke'))
    p.add_argument('--jobs',type=int,default=8)
    p.add_argument('--skip-legacy',action='store_true',help='Focused repeat only; does not claim old-mode validation')
    args=p.parse_args(); root=Path(__file__).resolve().parents[1]; out=args.out.resolve(); out.mkdir(parents=True,exist_ok=True)
    for key in ('TS_FIXED_PREDICTOR','TS_RATE_SHADOW','TS_RATE_RDOQ_SHADOW','TS_COND_TRACE'): os.environ.pop(key,None)
    for r in ('R2','R3','R4','R5','R6','R8','R9','R10','R11'):
        os.environ[f'TS_{r}_STATS']='0'; os.environ[f'TS_{r}_TRACE']='0'
    os.environ['TS_R10_CACHE']='0'
    modes=tuple(R11_MODE_NUMBERS); controls=('r3_risk_guard','r9_expert_integer','r10_integer_then_fractional')
    def native(m):
        r=subprocess.run([str(args.native_test.resolve())],env={**os.environ,'TS_FIXED_PREDICTOR':m},text=True,capture_output=True,check=True)
        print(r.stdout.strip(),flush=True); return m,r.stdout.strip()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool: native_results=dict(pool.map(native,modes))
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
    def add(case,label,exe,mode):
        name,qp,cfg,extra=case
        j=batch._make_job(order=len(jobs),name=name+'_'+label,repo_root=root,cwd=root,
            encoder=exe.resolve(),decoder=args.decoder.resolve(),cfgs=[root/cfg],
            sequence_cfg=root/'cfg/per-sequence/BasketballDrill.cfg',input_path=src,qp=qp,frames=2,
            extra_args=['--SourceWidth=64','--SourceHeight=64','-fr','30','--InputBitDepth=8','--InternalBitDepth=10',
                        '--TemporalSubsampleRatio=1','--SEIDecodedPictureHash=1',*extra],
            decoder_args=['-dph','1'],decode_md5=True,xlsm_tag=None,run_dir=out,overwrite=False)
        j=replace(j,no_recon=True,fixed_predictor=mode); jobs.append(j); keyed[(name,label)]=j
    def run(todo):
        with ThreadPoolExecutor(max_workers=args.jobs) as pool: rows=list(pool.map(batch._run_one,todo))
        allrows.extend(rows); batch._write_summary(out/'summary.csv',allrows)
        if any(r['error_info']!='pass' for r in rows): raise RuntimeError('Smoke failure; inspect summary.csv')
    # Quiet baseline and all old runtime modes; compare to the preserved R10 binary.
    for case in cases:
        for m in ('current',*controls,*modes): add(case,m,args.encoder,m)
        if args.off: add(case,'off',args.off,None); add(case,'legacy_off',args.legacy_off,None)
    old=[] if args.skip_legacy else [m for m in batch._TS_PREDICTOR_MODES if m not in modes]
    for m in old:
        if ('ai22',m) not in keyed: add(cases[0],m,args.encoder,m)
        add(cases[0],'legacy_'+m,args.legacy,m)
    run(jobs[:])
    for m in old: assert sha(keyed[('ai22',m)].bitstream)==sha(keyed[('ai22','legacy_'+m)].bitstream),m
    for cname,*_ in cases:
        if args.off:
            assert sha(keyed[(cname,'current')].bitstream)==sha(keyed[(cname,'off')].bitstream)==sha(keyed[(cname,'legacy_off')].bitstream)
    for m in modes: assert sha(keyed[('no_ts',m)].bitstream)==sha(keyed[('no_ts','current')].bitstream)
    # Frozen trajectories R3/R9-9/R10-3 plus all R11: enabling observation cannot change q/bitstream.
    os.environ.update(TS_R11_STATS='1',TS_R11_TRACE='1'); start=len(jobs)
    for case in cases:
        for m in (*controls,*modes): add(case,'observed_'+m,args.encoder,m)
    run(jobs[start:]); traces=0
    for cname,*_ in cases:
        for m in (*controls,*modes):
            j=keyed[(cname,'observed_'+m)]
            assert sha(j.bitstream)==sha(keyed[(cname,m)].bitstream),(cname,m,'observation changed bitstream')
            if m in modes:
                read=lambda p:[l for l in p.read_text(errors='replace').splitlines() if l.startswith('TS_R11_TRACE ')]
                enc,dec=read(j.encode_log),read(j.decode_log); assert enc==dec,(cname,m,'trace mismatch'); traces+=len(enc)
    assert traces>0
    changes={m:[c for c,*_ in cases if sha(keyed[(c,m)].bitstream)!=sha(keyed[(c,controls[-1])].bitstream)] for m in modes}
    result=dict(revision='R11-20260929-v1',tasks=len(jobs),legacy_modes_bit_exact=len(old),
        master_off_bit_exact=bool(args.off),no_ts_bit_exact=True,stats_off_bit_exact=True,
        matching_traces=traces,changed_vs_r10_3=changes,native=native_results,bdrate_measured=False,
        binary_sha256={str(x):sha(x) for x in (args.encoder,args.decoder,args.legacy)},
        bitstreams={f'{c}/{m}':sha(j.bitstream) for (c,m),j in keyed.items()})
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('native','bitstreams')},indent=2))

if __name__=='__main__': main()
