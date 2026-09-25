#!/usr/bin/env python3
"""Small closed-loop correctness/regression cases, never a BD-rate experiment."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import random
import batch_test as batch


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--encoder',type=Path,default=Path('build/ts-rate/bin/EncoderApp'))
    p.add_argument('--decoder',type=Path,default=Path('build/ts-rate/bin/DecoderApp'))
    p.add_argument('--legacy',type=Path,default=Path('build/ts-r6/bin/EncoderApp'))
    p.add_argument('--off',type=Path)
    p.add_argument('--out',type=Path,default=Path('runs/ts_rate_smoke'))
    p.add_argument('--jobs',type=int,default=2)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]; out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ.pop('TS_RATE_SHADOW',None);os.environ.pop('TS_RATE_RDOQ_SHADOW',None)
    rng=random.Random(381);data=bytearray()
    for frame in range(2):
        for size in (64,32,32):
            for y in range(size):
                for x in range(size):
                    base=35+150*(((x+2*frame)//7+y//9)%2) if y<size//2 else 60+(x*2+y+frame)%100
                    data.append(max(0,min(255,base+rng.randrange(-5,6))))
    src=out/'synthetic.yuv'
    if not src.exists() or src.read_bytes()!=data:src.write_bytes(data)
    cases=[('ai22',22,'cfg/encoder_intra_nx2.cfg',[]),
           ('ai0',0,'cfg/encoder_intra_nx2.cfg',['--TransformSkipLog2MaxSize=5']),
           ('lb22',22,'scripts/HHI测试cfg/LBeu/cfg/encoder_lowdelay_nx2High.cfg',[]),
           ('ra37',37,'cfg/encoder_randomaccess_nx2.cfg',[]),
           ('no_ts',22,'cfg/encoder_intra_nx2.cfg',['--TransformSkip=0']),
           ('bdpcm',22,'cfg/encoder_intra_nx2.cfg',['--BDPCM=1'])]
    jobs=[]
    for case,qp,cfg,extra in cases:
        specs=[('current',args.encoder,'current'),('r3_risk_guard',args.encoder,'r3_risk_guard'),
               ('rate_raw',args.encoder,'rate_raw'),('rate_guard',args.encoder,'rate_guard'),
               ('legacy_current',args.legacy,'current'),('legacy_r3',args.legacy,'r3_risk_guard')]
        if args.off:specs.append(('off',args.off,'current'))
        for label,encoder,mode in specs:
            j=batch._make_job(order=len(jobs),name=case+'_'+label,repo_root=root,cwd=root,
                encoder=encoder.resolve(),decoder=args.decoder.resolve(),cfgs=[root/cfg],
                sequence_cfg=root/'cfg/per-sequence/BasketballDrill.cfg',input_path=src,qp=qp,frames=2,
                extra_args=['--SourceWidth=64','--SourceHeight=64','-fr','30','--InputBitDepth=8',
                            '--InternalBitDepth=10','--TemporalSubsampleRatio=1','--SEIDecodedPictureHash=1',*extra],
                decoder_args=['-dph','1'],decode_md5=True,xlsm_tag=None,run_dir=out,overwrite=False)
            jobs.append(replace(j,no_recon=True,fixed_predictor=None if label=='off' else mode))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool: rows=list(pool.map(batch._run_one,jobs))
    batch._write_summary(out/'summary.csv',rows)
    if any(r['error_info']!='pass' for r in rows):raise RuntimeError('Failed smoke tasks; see summary.csv')
    hashes={j.name:hashlib.sha256(j.bitstream.read_bytes()).hexdigest() for j in jobs}
    for case,*_ in cases:
        assert hashes[case+'_current']==hashes[case+'_legacy_current'],case
        assert hashes[case+'_r3_risk_guard']==hashes[case+'_legacy_r3'],case
        if args.off:assert hashes[case+'_off']==hashes[case+'_legacy_current'],case
    changed={m:[c for c,*_ in cases if hashes[c+'_'+m]!=hashes[c+'_r3_risk_guard']] for m in ('rate_raw','rate_guard')}
    assert all(changed.values()), 'No closed-loop activity; stop before CTC'
    result=dict(tasks=len(jobs),all_hash_checks=True,legacy_current_R3_bit_exact=True,
                master_off_bit_exact=bool(args.off),changed_vs_R3=changed,hashes=hashes,
                binaries={str(x):hashlib.sha256(x.read_bytes()).hexdigest()
                          for x in (args.encoder,args.decoder,args.legacy,*([args.off] if args.off else []))})
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('hashes','binaries')},indent=2))


if __name__=='__main__':main()
