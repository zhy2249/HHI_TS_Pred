#!/usr/bin/env python3
"""R13 symmetric decoder-only audit. Never launches EncoderApp or reads raw YUV.

prepare copies source streams; inspect validates hashes and explicit native modes;
decode-pair decodes each origin using its own mode; replay consumes native snapshots.
"""
import argparse
from collections import defaultdict, Counter
import concurrent.futures
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
import sys
import time

REV = 'R13-DUAL-DECODE-AUDIT-impl2'
SPEC = 'R13-DUAL-DECODE-AUDIT-v1'
from ts_audit_stats import (POLICIES, save, read_json, csv_write, read_csv, hash_frames,
                            summarize, compare, point_metrics, strata_dimensions)
NATIVE = {'R13-1': 'r13_keep_hit_uniform', 'R13-2': 'r13_keep_hit_spatial'}
DEFAULTS = dict(seed=20261025, tus_per_frame_component=2, uniform_positions=2,
                disagreement_positions=2, replays_per_frame=96, visits_per_frame=125000,
                snapshot_cache_bytes=64*1024**2, snapshot_disk_bytes=64*1024**2,
                core_bytes=32*1024**2, raw_bytes=8*1024**2, log_bytes=8*1024**2,
                sampling_revision="hash-avalanche-v2", budget_revision="component-TU-reserved-family-v2")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def resolved(base, value):
    p = Path(value)
    return p if p.is_absolute() else (base/p).resolve()


def prepare(args):
    if args.output.exists():raise ValueError('Use a new bundle directory')
    pairs={}; inventory=[]; old=None
    if args.from_manifest:
        old=read_json(args.from_manifest);base=args.from_manifest.resolve().parent
        inputs=[]
        for entry in old['pairs']:
            pair=json.loads(json.dumps(entry));pairs[pair['pair_id']]=pair
            pair.setdefault('validation_only',any(s['path'].startswith('validation_streams/') for s in pair['origins'].values()))
            if set(pair['origins'])!=set(NATIVE):raise ValueError('Both origins required')
            for origin,stream in pair['origins'].items():
                src=resolved(base,stream['path'])
                if stream['native_policy']!=NATIVE[origin] or src.stat().st_size!=stream['bytes'] or sha(src)!=stream['sha256']:
                    raise ValueError('Original manifest source binding/hash mismatch')
                inputs.append((pair['pair_id'],origin,src))
    else:
        inputs=[]
        for src in sorted(args.source.glob('13_[12]/*.bin')):
            match=re.fullmatch(r'(.+)_(22|27|32|37)\.bin',src.name)
            if not match:raise ValueError('Unknown stream name: '+str(src))
            sequence,qp=match[1],int(match[2]);key=f'{sequence}_QP{qp}';origin='R13-'+src.parent.name[-1]
            pairs.setdefault(key,dict(pair_id=key,sequence=sequence,nominal_qp=qp,
                configuration=None,configuration_hint='historical LB half-frame; unverified server identity',
                width=None,height=None,bit_depth=None,chroma_format=None,frame_rate=None,
                frame_skip=None,temporal_subsample=None,expected_frames=None,source_content_sha256=None,
                pairing_status='unverified_encoding_identity',unknown=['encoder source/binary/config/input identity','frame range'],origins={}))
            pairs[key]['origins'][origin]=dict(native_policy=NATIVE[origin],scope='all',binding_source='user 13_1/13_2 directories',
                encoder_commit=None,encoder_sha256=None,config_sha256=None,sei_status='uninspected')
            inputs.append((key,origin,src))
    if not inputs:raise ValueError('No source streams')
    if any(set(p['origins'])!=set(NATIVE) for p in pairs.values()):raise ValueError('Every pair must contain both origins')
    args.output.mkdir(parents=True);(args.output/'bin').mkdir();(args.output/'scripts').mkdir()
    binary=args.output/'bin/DecoderAppAudit';shutil.copy2(args.decoder,binary)
    if subprocess.check_output([str(binary.resolve()),'--ts-audit-version'],text=True).strip()!=REV:
        raise ValueError('Decoder audit revision mismatch')
    for key,origin,src in inputs:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',key):raise ValueError('Unsafe pair id')
        dst=args.output/'streams'/key/(origin.replace('-','_')+'.bin');dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst);digest=sha(src)
        if sha(dst)!=digest:raise ValueError('Copy hash mismatch')
        stream=pairs[key]['origins'][origin];stream.update(path=dst.relative_to(args.output).as_posix(),sha256=digest,bytes=dst.stat().st_size)
        inventory.append(dict(pair_id=key,origin=origin,source=str(src),destination=stream['path'],bytes=stream['bytes'],sha256=digest))
    patch=subprocess.check_output(['git','diff','HEAD','--','source'])
    new=subprocess.check_output(['git','ls-files','--others','--exclude-standard','source'],text=True).splitlines()
    build=dict(source_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        source_patch_sha256=hashlib.sha256(patch).hexdigest(),untracked_source_sha256={p:sha(p) for p in new},
        source_identity_status='packaging worktree; compile provenance requires the recorded build validation',
        binary_sha256=sha(binary),platform=platform.platform(),machine=platform.machine(),
        compiler=subprocess.check_output(['c++','--version'],text=True).splitlines()[0],
        minimum_isa='x86_64 SSE4.1; runtime SSE4.2/AVX/AVX2 dispatch; no -march=native',
        runtime_dependencies=subprocess.check_output(['ldd',str(binary)],text=True),build_type='Release',gpu_required=False,
        script_sha256={p:sha(Path(__file__).with_name(p)) for p in ('ts_decode_score_audit.py','ts_audit_stats.py')})
    save(args.output/'build_info.json',build)
    manifest=dict(schema=2,spec_version=SPEC,implementation_revision=REV,scoring_revision='R13-KH-168-v1',
        score_scale=168,rate_scale=32768,decoder=dict(path='bin/DecoderAppAudit',sha256=sha(binary)),
        policies=POLICIES,limits=DEFAULTS,pairs=list(pairs.values()),fixtures={
            'CE01':dict(status='missing_fixture',population='SEARCH_FIXTURE',reason='Legacy context omits stateUsed; no encoding started.')})
    save(args.output/'manifest.json',manifest);csv_write(args.output/'copy_inventory.csv',inventory)
    for name in ('ts_decode_score_audit.py','ts_audit_stats.py'):
        shutil.copy2(Path(__file__).with_name(name),args.output/'scripts'/name)
    (args.output/'README_run.md').write_text('''# R13双来源解码审计 impl2

Linux x86_64/SSE4.1，Python 3.10+标准库。运行库见build_info.json。
从包目录执行，无需原图，不保存重建视频，不运行编码器：

```bash
python3 scripts/ts_decode_score_audit.py inspect --manifest manifest.json
python3 scripts/ts_decode_score_audit.py decode-pair --manifest manifest.json --pair Johnny_QP32 --first-poc 0 --last-poc 31 --verify-off --output results/j32
```

观察范围只限制统计；解码读取完整文件以保留参考关系。
源码/构建/统计schema见随包文档或对应Git提交。服务器编码身份未知字段保留null。
CE01是落选候选，不能由最终码流恢复。不存在SEI时仅验证on/off一致。
完整七方法/单点/快照/输出完成状态分别记录；summary只请求廉价分母。
预算不足不会改变解码，缺失不作0处理；小型验收不是全数据集收益结论。
''')
    print(json.dumps(dict(pairs=len(pairs),streams=len(inputs),bytes=sum(x['bytes'] for x in inventory),output=str(args.output))))

def inspect_manifest(path):
    m=read_json(path); base=path.resolve().parent
    if m.get('schema')!=2 or m.get('implementation_revision')!=REV or m.get('spec_version')!=SPEC or m.get('policies')!=POLICIES:
        raise ValueError('Unsupported manifest/schema/method set')
    if m.get('limits')!=DEFAULTS:
        raise ValueError('This implementation requires the registered symmetric resource profile')
    decoder=resolved(base,m['decoder']['path'])
    if sha(decoder)!=m['decoder']['sha256']:
        raise ValueError('Decoder fingerprint mismatch')
    if subprocess.check_output([str(decoder),'--ts-audit-version'],text=True).strip()!=REV:
        raise ValueError('Decoder revision mismatch')
    seen=set()
    for pair in m['pairs']:
        if pair['pair_id'] in seen: raise ValueError('Duplicate pair id')
        seen.add(pair['pair_id'])
        if set(pair['origins'])!=set(NATIVE):raise ValueError('Both native origins are required')
        for origin,s in pair['origins'].items():
            if origin not in NATIVE or s['native_policy']!=NATIVE[origin] or s['scope']!='all':
                raise ValueError('Source policy binding mismatch; never guess another policy')
            stream=resolved(base,s['path'])
            if stream.stat().st_size!=s['bytes'] or sha(stream)!=s['sha256']:
                raise ValueError(f'Stream fingerprint mismatch: {stream}')
            with stream.open('rb') as f:
                if f.read(60).startswith(b'version https://git-lfs'):
                    raise ValueError('LFS pointer is not a bitstream')
    return m,decoder


def bounded_run(command,env,log):
    size=0; truncated=False
    with log.open('wb') as output:
        proc=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        while True:
            chunk=proc.stdout.read(65536)
            if not chunk: break
            kept=chunk[:max(0,DEFAULTS['log_bytes']//2-size)]; output.write(kept);size+=len(kept)
            truncated |= len(kept)!=len(chunk)
        rc=proc.wait()
    return rc,truncated


def effective_limits(m,args):
    limits=dict(m['limits'])
    for option,key in [('replays','replays_per_frame'),('visits','visits_per_frame'),
                       ('snapshot_bytes','snapshot_disk_bytes'),('raw_bytes','raw_bytes'),('core_bytes','core_bytes')]:
        value=getattr(args,option,None)
        if value is not None:
            if value<0 or value>DEFAULTS[key]:raise ValueError('Resource limit must only lower the registered maximum: '+option)
            if key=='core_bytes' and value<256*1024:raise ValueError('Core budget must reserve at least 256 KiB for metadata')
            limits[key]=value
    return limits


def decode_origin(m,manifest,decoder,pair,origin,args):
    out=args.output/origin
    stream=pair['origins'][origin];path=resolved(manifest.resolve().parent,stream['path'])
    limits=effective_limits(m,args)
    fingerprint=dict(schema=2,revision=REV,decoder=sha(decoder),stream=sha(path),
        wrapper=sha(Path(__file__)),statistics=sha(Path(__file__).with_name('ts_audit_stats.py')),
        origin=origin,native_policy=stream['native_policy'],pair=pair['pair_id'],expected_frames=pair.get('expected_frames'),
        first=args.first_poc,last=args.last_poc,component=args.component,profile=args.profile,tu=args.tu,
        limits=limits,verify_off=args.verify_off)
    if out.exists():
        marker=out/'completed.json'
        if getattr(args,'resume',False) and marker.exists() and read_json(marker)==fingerprint:
            return origin,read_json(out/'decode_validation.json')
        previous=out/'run.json'
        if getattr(args,'resume',False) and not marker.exists() and previous.exists() and read_json(previous).get('task_fingerprint')==fingerprint:
            archived=out.parent/'failed_attempts'/f'{origin}-{time.time_ns()}'
            archived.parent.mkdir(exist_ok=True);out.rename(archived)
        else:raise ValueError(f'Existing output has no matching completion fingerprint: {out}')
    out.mkdir(parents=True)
    env={k:v for k,v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=stream['native_policy'],TS_R13_DIAG_SCOPE='all',TS_R13_STATS='0',TS_R13_TRACE='0',TS_AUDIT_HASH=str((out/'reconstruction.csv').resolve()))
    command=[str(decoder),'-b',str(path),'-o','','-dph','1']
    identity=dict(schema=2,spec_version=SPEC,implementation_revision=REV,pair_id=pair['pair_id'],origin=origin,native_policy=stream['native_policy'],nominal_qp=pair['nominal_qp'],
        manifest_sha256=sha(manifest),decoder_sha256=sha(decoder),stream_sha256=sha(path),command=command,profile=args.profile,first_poc=args.first_poc,last_poc=args.last_poc,
        component=args.component,tu_filter=args.tu,policies=POLICIES,limits=limits,pairing_status=pair['pairing_status'],source_identity=stream,population='FINAL_SELECTED')
    build_info=manifest.resolve().parent/'build_info.json'
    identity['task_fingerprint']=fingerprint
    identity['build_identity']=read_json(build_info) if build_info.exists() else None
    env.update(TS_SCORE_AUDIT=str(out.resolve()),TS_AUDIT_PROFILE=args.profile,TS_AUDIT_FIRST=str(args.first_poc),TS_AUDIT_LAST=str(args.last_poc),TS_AUDIT_COMPONENT=str(args.component),
        TS_AUDIT_REPLAYS=str(limits['replays_per_frame']),TS_AUDIT_VISITS=str(limits['visits_per_frame']),
        TS_AUDIT_RAW_BYTES=str(limits['raw_bytes']),TS_AUDIT_SNAPSHOT_BYTES=str(limits['snapshot_disk_bytes']))
    if args.profile=='detail':env['TS_AUDIT_TU']=args.tu
    identity['observer_env']={k:v for k,v in env.items() if k.startswith('TS_')};save(out/'run.json',identity)
    start=time.monotonic();rc,truncated=bounded_run(command,env,out/'decode.log')
    identity.update(returncode=rc,elapsed_seconds=time.monotonic()-start)
    hashes=hash_frames(out/'reconstruction.csv');text=(out/'decode.log').read_text(errors='replace')
    sei_lines=[line for line in text.splitlines() if re.match(r'POC\s+\d+',line)]
    sei_ok=sum(bool(re.search(r'MD5:.*(?:\(OK\)|,OK\]|\(OK\)\])',line)) for line in sei_lines)
    sei_present=any('MD5:' in line or 'CRC:' in line or 'Checksum:' in line for line in sei_lines)
    native_path=out/'native_validation.json'
    native=read_json(native_path) if native_path.exists() else None
    frames_ok=pair.get('expected_frames') is None or len(hashes)==pair['expected_frames']
    decode_ok=rc==0 and bool(hashes) and frames_ok and bool(native and native['valid'])
    sei_status=('SEI_log_incomplete' if truncated else 'SEI_failed' if rc and sei_present else
        'SEI_MD5_all_decoded_frames_verified' if sei_present and sei_ok==len(hashes) else
        'SEI_partial_or_non_MD5' if sei_present else 'SEI_not_available')
    validation=dict(schema=2,returncode=rc,expected_frames=pair.get('expected_frames'),actual_frames=len(hashes),
        expected_frame_count_known=pair.get('expected_frames') is not None,sei_status=sei_status,sei_md5_ok_count=sei_ok,
        log_truncated=truncated,on_off_equal=None,native_replay=native,decode_complete=decode_ok,
        native_replay_complete=native.get('native_replay_complete') if native else False,
        policy_complete=native.get('policy_complete') if native else [False]*7,
        point_oracle_complete=native.get('point_oracle_complete') if native else False,
        snapshot_complete=native.get('snapshot_complete') if native else False,
        output_complete=False,audit_complete=False)
    if not decode_ok:
        save(out/'decode_validation.json',validation);save(out/'run.json',identity)
        raise ValueError(f'{origin} decode/native verification failed; see {out}')
    if args.verify_off:
        off_env={k:v for k,v in env.items() if not k.startswith(('TS_SCORE_AUDIT','TS_AUDIT_'))}
        off_env['TS_AUDIT_HASH']=str((out/'reconstruction_off.csv').resolve())
        off_rc,off_truncated=bounded_run(command,off_env,out/'off.log')
        validation.update(off_returncode=off_rc,on_off_equal=off_rc==0 and hashes==hash_frames(out/'reconstruction_off.csv'))
        validation['log_truncated']|=off_truncated
        if not validation['on_off_equal']:
            save(out/'decode_validation.json',validation);raise ValueError('Audit on/off reconstruction mismatch')
    aggregation=summarize(out,identity);identity['aggregation']=aggregation
    validation['output_complete']=native['output_complete'] and aggregation['output_complete'] and not validation['log_truncated']
    validation['census_complete']=decode_ok and validation['output_complete']
    validation['detail_status']='not_in_final_bitstream' if args.profile=='detail' and not aggregation['sampled_tu'] and validation['output_complete'] else 'incomplete_query' if not validation['output_complete'] else 'ok'
    validation['audit_complete']=(decode_ok and validation['output_complete'] and native['audit_complete'] is True) if args.profile!='summary' else None
    validation['completeness_contract']='full selected-TU native + all seven policies + both point samples + snapshots + all outputs; summary only requests census'
    validation['output_truncated_files']=aggregation['output_truncated_files'];validation['output_dropped_rows']=aggregation['output_dropped_rows']
    save(out/'decode_validation.json',validation);save(out/'run.json',identity)
    # A partial observation is still a reproducible completed decode task.
    # Resume preserves its explicit incomplete status; it never repairs it by
    # changing budgets silently or records failure as success.
    save(out/'completed.json',fingerprint)
    return origin,validation

def select_examples(args):
    """Filter retained point observations, never the primary sampling population."""
    if args.output.exists():raise ValueError('Use a fresh example output directory')
    if not 1<=args.max_examples<=320:raise ValueError('Example limit must be 1..320')
    if args.first_poc<0 or args.last_poc<args.first_poc:raise ValueError('Invalid POC range')
    size=None
    if args.size:
        if not re.fullmatch(r'[1-9][0-9]*x[1-9][0-9]*',args.size):raise ValueError('Size must be WxH')
        size=tuple(map(int,args.size.split('x')))
    component={'Y':0,'U':1,'V':2,'all':-1}[args.component]
    raw=args.input/'audit.jsonl'
    if raw.stat().st_size>8*1024**2:raise ValueError('Input exceeds registered raw observation bound')
    records=[json.loads(line) for line in raw.read_text().splitlines()]
    tus={r['id']:r for r in records if r['kind']=='tu'}
    selected=[];missing_metadata=0
    for row in records:
        if row['kind']!='point' or not args.first_poc<=row['poc']<=args.last_poc:continue
        if component>=0 and row['component']!=component:continue
        if row['tu'] not in tus:
            missing_metadata+=1;continue
        tu=tus[row['tu']]
        if size and (tu['w'],tu['h'])!=size:continue
        delta=row['cost_frac'][4]-row['cost_frac'][3]
        if args.loss_sign!='all' and args.loss_sign!=('positive' if delta>0 else 'negative' if delta<0 else 'zero'):continue
        selected.append({**row,'width':tu['w'],'height':tu['h'],'snapshot':tu['snapshot'],'SP_minus_EQ_frac':delta})
    selected.sort(key=lambda r:(-abs(r['SP_minus_EQ_frac']),r['poc'],r['tu'],r['scan']))
    args.output.mkdir(parents=True)
    with (args.output/'examples.jsonl').open('w') as f:
        for row in selected[:args.max_examples]:f.write(json.dumps(row,allow_nan=False)+'\n')
    save(args.output/'selection.json',dict(input=str(args.input.resolve()),size=args.size,loss_sign=args.loss_sign,
        first_poc=args.first_poc,last_poc=args.last_poc,component=args.component,matched=len(selected),
        saved=min(len(selected),args.max_examples),skipped_missing_tu_metadata=missing_metadata,order='descending absolute SP-minus-EQ cost',
        population='retained sampled positions only; selection is for explanation, not representative frequencies'))


def run_batch(args,manifest,decoder):
    pairs=[p for p in manifest['pairs'] if not p.get('validation_only',False)] if args.pairs=='all' else [p for p in manifest['pairs'] if p['pair_id'] in args.pairs.split(',')]
    if not pairs or (args.pairs!='all' and {p['pair_id'] for p in pairs}!=set(args.pairs.split(','))):raise ValueError('Unknown or empty pair selection')
    if args.jobs<1:raise ValueError('jobs must be positive')
    if args.profile=='detail' or args.origin:raise ValueError('Batch requires symmetric standard/summary observations')
    plan=dict(pairs=[p['pair_id'] for p in pairs],decoder_tasks=2*len(pairs),max_parallel_decoders=args.jobs,
        first_poc=args.first_poc,last_poc=args.last_poc,limits=effective_limits(manifest,args),video_encoding=False)
    if args.dry_run:print(json.dumps(plan,ensure_ascii=False,indent=2));return
    if args.output.exists() and not args.resume:raise ValueError('Use a new batch output or matching --resume')
    args.output.mkdir(parents=True,exist_ok=True);save(args.output/'batch_plan.json',plan)
    # One shared pool of origin tasks, without pair/group completion barriers.
    results=[];pending={p['pair_id']:2 for p in pairs};failed=set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        work={}
        for pair in pairs:
            local=argparse.Namespace(**vars(args));local.output=args.output/pair['pair_id'];local.output.mkdir(parents=True,exist_ok=True)
            for origin in NATIVE:work[pool.submit(decode_origin,manifest,args.manifest,decoder,pair,origin,local)]=(pair,origin)
        for future in concurrent.futures.as_completed(work):
            pair,origin=work[future];key=pair['pair_id']
            try:
                _,validation=future.result()
                row=dict(pair_id=key,origin=origin,decode_complete=validation['decode_complete'],audit_complete=validation['audit_complete'],error=None)
            except Exception as error:
                failed.add(key);row=dict(pair_id=key,origin=origin,decode_complete=False,audit_complete=False,error=str(error))
                (args.output/key/(origin+'_failure.txt')).write_text(str(error)+'\n')
            results.append(row);pending[key]-=1
            if pending[key]==0 and key not in failed:
                try:compare(args.output/key/'R13-1',args.output/key/'R13-2',args.output/key)
                except Exception as error:
                    failed.add(key);(args.output/key/'comparison_failure.txt').write_text(str(error)+'\n')
            save(args.output/'batch_status.json',dict(results=results,failed_pairs=sorted(failed)))
            print(json.dumps(row),flush=True)
    if failed:raise ValueError('Some decoder/comparison tasks failed; see batch_status.json; --resume preserves valid tasks')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--version',action='version',version=REV)
    sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');sources=prep.add_mutually_exclusive_group(required=True);sources.add_argument('--source',type=Path);sources.add_argument('--from-manifest',type=Path);prep.add_argument('--decoder',type=Path,required=True);prep.add_argument('--output',type=Path,required=True)
    inspect=sub.add_parser('inspect');inspect.add_argument('--manifest',type=Path,required=True)
    for name in ('decode-pair','detail','batch'):
        d=sub.add_parser(name);d.add_argument('--manifest',type=Path,required=True);d.add_argument('--pair',required=name!='batch');d.add_argument('--output',type=Path,required=True);d.add_argument('--verify-off',action='store_true')
        d.add_argument('--profile',choices=['summary','standard','detail'],default='detail' if name=='detail' else 'standard')
        d.add_argument('--first-poc',type=int,default=0);d.add_argument('--last-poc',type=int,default=2147483647);d.add_argument('--component',choices=['Y','U','V','all'],default='all');d.add_argument('--tu');d.add_argument('--origin',choices=list(NATIVE))
        d.add_argument('--poc',type=int)
        d.add_argument('--resume',action='store_true')
        if name=='batch':
            d.add_argument('--pairs',default='all');d.add_argument('--jobs',type=int,default=2);d.add_argument('--dry-run',action='store_true')
        for option in ('replays','visits','snapshot-bytes','raw-bytes','core-bytes'):
            d.add_argument('--'+option,type=int,help='Lower the registered observation limit for both origins')
    replay=sub.add_parser('replay');replay.add_argument('--snapshot',type=Path,required=True);replay.add_argument('--decoder',type=Path,required=True);replay.add_argument('--policies',default='KEEP_EQ,KEEP_SP');replay.add_argument('--output',type=Path,required=True)
    comp=sub.add_parser('compare');comp.add_argument('--reference',type=Path,required=True);comp.add_argument('--test',type=Path,required=True);comp.add_argument('--output',type=Path,required=True)
    examples=sub.add_parser('select-examples',help='Filter retained observations; leaves primary statistics unchanged')
    examples.add_argument('--input',type=Path,required=True);examples.add_argument('--output',type=Path,required=True)
    examples.add_argument('--size');examples.add_argument('--loss-sign',choices=['all','positive','negative','zero'],default='all')
    examples.add_argument('--component',choices=['Y','U','V','all'],default='all');examples.add_argument('--max-examples',type=int,default=32)
    examples.add_argument('--first-poc',type=int,default=0);examples.add_argument('--last-poc',type=int,default=2147483647)
    args=p.parse_args()
    if args.command=='prepare':return prepare(args)
    if args.command=='compare':compare(args.reference,args.test,args.output);return
    if args.command=='select-examples':return select_examples(args)
    if args.command=='replay':
        if args.output.exists():raise ValueError('Use a fresh replay output')
        if any(x not in POLICIES for x in args.policies.split(',')):raise ValueError('Unknown policy')
        subprocess.run([str(args.decoder.resolve()),'--ts-audit-replay',str(args.snapshot.resolve()),str(args.output.resolve())],check=True)
        result=read_json(args.output/'replay.json');print(json.dumps({name:result['rates_frac'][POLICIES.index(name)] for name in args.policies.split(',')}));return
    manifest,decoder=inspect_manifest(args.manifest)
    if args.command=='inspect':print(json.dumps(dict(valid=True,pairs=len(manifest['pairs']),streams=sum(len(p['origins']) for p in manifest['pairs']),fixtures=manifest['fixtures']),ensure_ascii=False));return
    if args.poc is not None:args.first_poc=args.last_poc=args.poc
    if args.first_poc<0 or args.last_poc<args.first_poc:raise ValueError('Invalid POC range')
    args.component={'Y':0,'U':1,'V':2,'all':-1}[args.component]
    effective_limits(manifest,args)
    if args.command=='batch':return run_batch(args,manifest,decoder)
    pair=next((x for x in manifest['pairs'] if x['pair_id']==args.pair),None)
    if pair is None:raise ValueError('Unknown pair id')
    if args.output.exists() and not args.resume:raise ValueError('New output directory required unless --resume matches')
    if args.profile=='detail' and (args.first_poc!=args.last_poc or args.component<0 or not args.tu):raise ValueError('detail requires one POC, component and TU')
    origins=[args.origin] if args.origin else list(NATIVE)
    if any(o not in pair['origins'] for o in origins):raise ValueError('Missing paired origin; not silently substituted')
    args.output.mkdir(parents=True,exist_ok=args.resume)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(decode_origin,manifest,args.manifest,decoder,pair,o,args) for o in origins]
        for future in futures:
            origin,result=future.result();print(json.dumps(dict(origin=origin,**{k:result[k] for k in ('decode_complete','audit_complete','native_replay_complete','policy_complete','snapshot_complete','output_complete','on_off_equal')})),flush=True)
    if len(origins)==2:compare(args.output/'R13-1',args.output/'R13-2',args.output)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        print(f'AUDIT ERROR: {error}',file=sys.stderr);sys.exit(2)
