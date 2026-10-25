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

REV = 'R13-DUAL-DECODE-AUDIT-impl1'
SPEC = 'R13-DUAL-DECODE-AUDIT-v1'
POLICIES = ['CURRENT', 'STATIC_EQ', 'STATIC_SP', 'KEEP_EQ', 'KEEP_SP', 'KEEP_EQ_H', 'KEEP_SP_H']
NATIVE = {'R13-1': 'r13_keep_hit_uniform', 'R13-2': 'r13_keep_hit_spatial'}
DEFAULTS = dict(seed=20261025, tus_per_frame_component=2, uniform_positions=2,
                disagreement_positions=2, replays_per_frame=96, visits_per_frame=125000,
                snapshot_cache_bytes=64*1024**2, snapshot_disk_bytes=64*1024**2,
                core_bytes=32*1024**2, log_bytes=8*1024**2)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def csv_write(path, rows, fields=None):
    fields = fields or (list(rows[0]) if rows else ['status'])
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader(); w.writerows(rows)


def read_csv(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def read_json(path):
    return json.loads(Path(path).read_text())


def resolved(base, value):
    p = Path(value)
    return p if p.is_absolute() else (base/p).resolve()


def prepare(args):
    if args.output.exists():
        raise ValueError('Use a new bundle directory; existing bundles are never overwritten')
    files = sorted(args.source.glob('13_[12]/*.bin'))
    if not files:
        raise ValueError('No 13_1/13_2 .bin files')
    args.output.mkdir(parents=True)
    (args.output/'bin').mkdir()
    binary = args.output/'bin/DecoderAppAudit'
    shutil.copy2(args.decoder, binary)
    version = subprocess.check_output([str(binary.resolve()), '--ts-audit-version'], text=True).strip()
    if version != REV:
        raise ValueError('Decoder does not implement the declared audit revision')
    pairs, inventory = {}, []
    for src in files:
        match = re.fullmatch(r'(.+)_(22|27|32|37)\.bin', src.name)
        if not match:
            raise ValueError(f'Unknown stream name: {src}')
        sequence, qp = match[1], int(match[2]); key = f'{sequence}_QP{qp}'
        origin = 'R13-'+src.parent.name[-1]
        dst = args.output/'streams'/key/(origin.replace('-', '_')+'.bin')
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
        digest = sha(src)
        if sha(dst) != digest:
            raise ValueError(f'Copy hash mismatch: {src}')
        pair = pairs.setdefault(key, dict(pair_id=key, sequence=sequence, nominal_qp=qp,
            configuration=None, configuration_hint='LB half-frame (historical experiment convention; unverified for these files)',
            width=None, height=None, bit_depth=None, chroma_format=None, frame_rate=None,
            frame_skip=None, temporal_subsample=None, expected_frames=None, source_content_sha256=None,
            pairing_status='unverified_encoding_identity', unknown=['encoder source/binary/config/input identity', 'frame range'], origins={}))
        pair['origins'][origin] = dict(path=dst.relative_to(args.output).as_posix(), sha256=digest,
            bytes=dst.stat().st_size, native_policy=NATIVE[origin], scope='all',
            binding_source='user supplied 13_1/13_2 directory', encoder_commit=None, encoder_sha256=None,
            config_sha256=None, sei_status='uninspected')
        inventory.append(dict(pair_id=key, origin=origin, source=str(src), destination=dst.relative_to(args.output).as_posix(), bytes=dst.stat().st_size, sha256=digest))
    patch = subprocess.check_output(['git', 'diff', '--', 'source'])
    new = subprocess.check_output(['git','ls-files','--others','--exclude-standard','source'],text=True).splitlines()
    build = dict(source_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                 source_patch_sha256=hashlib.sha256(patch).hexdigest(), untracked_source_sha256={p:sha(p) for p in new},
                 binary_sha256=sha(binary), platform=platform.platform(), machine=platform.machine(),
                 compiler=subprocess.check_output(['c++','--version'],text=True).splitlines()[0],
                 minimum_isa='x86_64 SSE4.1; runtime SSE4.2/AVX/AVX2 dispatch; no -march=native',
                 runtime_dependencies=subprocess.check_output(['ldd',str(binary)],text=True), build_type='Release',
                 gpu_required=False)
    save(args.output/'build_info.json', build)
    manifest = dict(schema=1, spec_version=SPEC, implementation_revision=REV, scoring_revision='R13-KH-168-v1',
        score_scale=168, rate_scale=32768, decoder=dict(path='bin/DecoderAppAudit',sha256=sha(binary)),
        policies=POLICIES, limits=DEFAULTS, pairs=list(pairs.values()), fixtures={
        'CE01': dict(status='missing_fixture', population='SEARCH_FIXTURE',
                     reason='Existing q and old context CSV omit stateUsed; not a restorable true snapshot. No encoding started.')})
    save(args.output/'manifest.json', manifest); csv_write(args.output/'copy_inventory.csv', inventory)
    (args.output/'scripts').mkdir()
    shutil.copy2(__file__, args.output/'scripts'/Path(__file__).name)
    (args.output/'README_run.md').write_text('''# R13 双源审计本地包

从包目录执行；不需要原始YUV，不调用编码器，默认无重建文件。

```bash
python3 scripts/ts_decode_score_audit.py inspect --manifest manifest.json
python3 scripts/ts_decode_score_audit.py decode-pair --manifest manifest.json --pair Johnny_QP32 --output results/j32 --first-poc 0 --last-poc 31 --verify-off
```

POC过滤只限制观察，解码仍完整读取码流及必要参考。source/input/config未知身份在manifest中保留null；目录绑定不等于服务器revision已认证。
`--verify-off`逐来源额外解码一次；没有SEI时只称on/off重建一致，不称编码端MD5通过。
CE01是落选TS，最终码流无法恢复；缺少真实stateUsed快照，标为missing_fixture。
所有.bin、二进制和大快照仅在本地保存。源码与构建说明见仓库docs/experiments/TS_Predictor_Dual_Decoder_Audit_Implementation.md。
''')
    print(json.dumps(dict(pairs=len(pairs), streams=len(files), bytes=sum(x['bytes'] for x in inventory), output=str(args.output))))


def inspect_manifest(path):
    m=read_json(path); base=path.resolve().parent
    if m.get('schema')!=1 or m.get('implementation_revision')!=REV or m.get('spec_version')!=SPEC or m.get('policies')!=POLICIES:
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


def hash_frames(path):
    if not path.exists(): return {}
    out={}
    with path.open() as stream:
        for row in csv.reader(stream):
            if len(row)!=4 or int(row[0]) in out: raise ValueError('Missing/duplicate reconstruction hash record')
            out[int(row[0])]=row[1:]
    return out


def percentile(values,p):
    if not values: return None
    x=sorted(values); f=(len(x)-1)*p; i=int(f); return x[i]+(x[min(i+1,len(x)-1)]-x[i])*(f-i)


def paired_frame_intervals(summaries, common, valid, draws=2000):
    """Circular blocks of eight POCs, paired across origins; never coefficients."""
    result=[]
    for component in range(3):
        indexed=[{int(r['poc']):r for r in rows if r['policy']=='KEEP_SP' and int(r['component'])==component}
                 for rows in summaries]
        samples=[[],[],[]]; rng=random.Random(DEFAULTS['seed']); complete=all(v['audit_complete'] for v in valid)
        support=[sum(int(x.get(p,{}).get('target_nz',0))>0 for p in common) for x in indexed]
        if complete and common and min(support)>=2:
            for _ in range(draws):
                positions=[]
                while len(positions)<len(common):
                    start=rng.randrange(len(common));positions.extend(common[(start+j)%len(common)] for j in range(8))
                ratios=[]
                for origin in range(2):
                    chosen=[indexed[origin][p] for p in positions[:len(common)] if p in indexed[origin]]
                    den=sum(int(x['target_nz']) for x in chosen)
                    usable=den>0 and all(x['ht_minus_eq_frac'] for x in chosen)
                    value=sum(float(x['ht_minus_eq_frac']) for x in chosen)/den/32768 if usable else None
                    ratios.append(value)
                    if value is not None:samples[origin].append(value)
                if None not in ratios:samples[2].append(sum(ratios)/2)
        for origin,values in zip(('R13-1','R13-2','balanced'),samples):
            result.append(dict(component=component,origin=origin,metric='SP_minus_EQ_estimated_bits_per_nonzero',
                method='paired circular POC-block bootstrap, block length 8',seed=DEFAULTS['seed'],requested_draws=draws,
                valid_draws=len(values),support_frames_EQ=support[0],support_frames_SP=support[1],
                ci95=[percentile(values,.025),percentile(values,.975)] if values else None,
                status='conditional_small_content_sample' if values else 'insufficient_support_or_incomplete'))
    return result


def summarize(out,identity):
    rows=[json.loads(line) for line in (out/'audit.jsonl').read_text().splitlines()]
    frames=[r for r in rows if r['kind']=='frame']; tus=[r for r in rows if r['kind']=='tu']; points=[r for r in rows if r['kind']=='point']
    common=dict(pair_id=identity['pair_id'],origin=identity['origin'],nominal_qp=identity['nominal_qp'])
    matrix=[]
    for r in tus:
        weight=r['tu_population']/r['tu_selected']
        row={**common,**{k:v for k,v in r.items() if k not in ('kind','rates_frac')}}
        row['inclusion_probability']=1/weight
        for i,name in enumerate(POLICIES): row[name+'_frac']=r['rates_frac'][i] if r['rates_frac'][i]>=0 else None
        row['SP_minus_EQ_frac']=r['rates_frac'][4]-r['rates_frac'][3] if min(r['rates_frac'][3:5])>=0 else None
        matrix.append(row)
    csv_write(out/'tu_policy_matrix.csv',matrix)
    frame_rows=[]
    for f in frames:
        population=[t for t in tus if (t['poc'],t['component'])==(f['poc'],f['component'])]
        samples=[p for p in points if (p['poc'],p['component'])==(f['poc'],f['component']) and p['sample']=='uniform']
        for m,name in enumerate(POLICIES):
            valid=[p for p in samples if p.get('distinguishable_plus',p['distinguishable'])] if m>=5 else [p for p in samples if p['distinguishable']]
            def weight(p): return p['tu_population']/p['tu_selected']*p['position_population']/p['position_selected']
            den=sum(weight(p) for p in valid)
            comparable=population and all(t['rates_frac'][m]>=0 and t['rates_frac'][3]>=0 for t in population)
            target_tu=f['tu']-f['bdpcm_tu']
            rate=sum(t['rates_frac'][m]*t['tu_population']/t['tu_selected'] for t in population) if comparable else (0 if not target_tu else None)
            delta=sum((t['rates_frac'][m]-t['rates_frac'][3])*t['tu_population']/t['tu_selected'] for t in population) if comparable else (0 if not target_tu else None)
            frame_rows.append({**common,'poc':f['poc'],'component':f['component'],'policy':name,'seen_tu':f['tu'],'seen_coeff':f['coeff'],'seen_nz':f['nz'],'target_tu':f['tu']-f['bdpcm_tu'],'target_nz':f.get('target_nz',f['nz']),'oracle_set':'Cplus' if m>=5 else 'C0','bdpcm_tu':f['bdpcm_tu'],
                'selected_tu':f['selected_tu'],'audited_tu':len(population),'uniform_positions':len(samples),'distinguishable_positions':len(valid),'tie_positions':len(samples)-len(valid),
                'ht_distinguishable_population':den,'ht_correct':sum(weight(p)*(p['regret_frac'][m]==0) for p in valid),
                'ht_regret_frac':sum(weight(p)*p['regret_frac'][m] for p in valid),
                'sample_predictor_changes_vs_EQ':sum(p['pred'][m]!=p['pred'][3] for p in samples),'sample_score_ties':sum(len(p['scores168'][m])>1 and p['scores168'][m].count(min(p['scores168'][m]))>1 for p in samples),'sample_wrong_distinguishable':sum(p['regret_frac'][m]>0 for p in valid),
                'accuracy':sum(weight(p)*(p['regret_frac'][m]==0) for p in valid)/den if den else None,
                'mean_regret_bits':sum(weight(p)*p['regret_frac'][m] for p in valid)/den/32768 if den else None,
                'positive_regret_mean_bits':sum(p['regret_frac'][m] for p in valid if p['regret_frac'][m]>0)/sum(p['regret_frac'][m]>0 for p in valid)/32768 if any(p['regret_frac'][m]>0 for p in valid) else None,
                'sample_regret_median_bits':percentile([p['regret_frac'][m]/32768 for p in valid],.5),'sample_regret_p95_bits':percentile([p['regret_frac'][m]/32768 for p in valid],.95),
                'ht_policy_rate_frac':rate,'ht_minus_eq_frac':delta,
                'sampling_complete':len(population)==f['selected_tu'] and bool(comparable) if f['tu']-f['bdpcm_tu'] else True})
    csv_write(out/'frame_summary.csv',frame_rows)
    strata=defaultdict(lambda:dict(count=0,distinguishable=0,regret_frac=0,correct=0))
    history=defaultdict(lambda:Counter())
    for r in points:
        conflict=(max(r['H'][:2])>1 and sum(a==1 for a in r['H'][2:])>=2)
        margins=[]
        for m in (3,4):
            scores=sorted(r['scores168'][m]); gap=(scores[1]-scores[0])/(168*r['weight_sum'][m]) if len(scores)>1 else None
            margins.append('single' if gap is None else '0' if gap==0 else '<=1/64' if gap<=1/64 else '<=1/16' if gap<=1/16 else '<=1/4' if gap<=1/4 else '<=1' if gap<=1 else '>1')
        dimensions={'amplitude':str(r['a']) if r['a']<=2 else '3-4' if r['a']<=4 else '>=5','support':str(r['n']), 'slice':'I' if r['intra'] else 'B/inter', 'native_path':'regular' if r.get('regular_active',True) else 'bypass', 'missing_neighbors':str(r.get('missing_neighbors','unrecorded')),
                    'area':'<=16' if r['area']<=16 else '<=64' if r['area']<=64 else '<=256' if r['area']<=256 else '>256',
                    'margin_EQ':margins[0],'margin_SP':margins[1],'near_far_conflict':str(conflict),
                    'low_n_conflict_margin':f'{min(r["a"],3)}|{r["n"]}|{int(conflict)}|{margins[1]}'}
        for m,name in enumerate(POLICIES):
            distinguishable=r['distinguishable_plus'] if m>=5 else r['distinguishable']
            for dimension,bucket in dimensions.items():
                acc=strata[(r['sample'],r['component'],name,dimension,bucket)];acc['count']+=1;acc['distinguishable']+=distinguishable;acc['regret_frac']+=r['regret_frac'][m];acc['correct']+=bool(distinguishable and not r['regret_frac'][m])
        for m in (5,6):
            h=history[(r['sample'],r['component'],POLICIES[m])];h['samples']+=1;h['hist_valid']+=r['history_nz']>0;h['hist_one']+=r['hist']==1;h['hist_ge2']+=r['hist']>=2
            h['candidate_added']+=len(r['cplus'])>len(r['c0']);h['selected_new']+=r['pred'][m] not in r['c0'];h['coverage_frac']+=r['coverage_frac'];h['selection_minus_parent_frac']+=r['cost_frac'][m]-r['cost_frac'][m-2]
            def remap(a,p): return 1 if a==p else a+1 if a<p else a
            h['new_mapping_added']+=bool(set(remap(r['a'],p) for p in r['cplus'])-set(remap(r['a'],p) for p in r['c0']))
            h['mapping_changed']+=remap(r['a'],r['pred'][m])!=remap(r['a'],r['pred'][m-2])
    for frame in frames:
        for dimension,labels in (('amplitude',['0','1','2','3-4','>=5']),('support',['0','1','2','3','4','5'])):
            for label,count in zip(labels,frame[dimension]):
                strata[('all_final_TS_including_BDPCM',frame['component'],'ALL',dimension,label)]['count']+=count
    csv_write(out/'strata.csv',[{**common,'sample':k[0],'component':k[1],'policy':k[2],
        'oracle_set':'Cplus' if k[2].endswith('_H') else 'C0' if k[2]!='ALL' else None,
        'dimension':k[3],'bucket':k[4],**v} for k,v in sorted(strata.items())])
    csv_write(out/'history_summary.csv',[{**common,'sample':k[0],'component':k[1],'policy':k[2],**v} for k,v in sorted(history.items())])
    # Keep balanced directions, with no effect on representative metrics.
    rng=random.Random(DEFAULTS['seed']); random_examples=rng.sample(points,min(128,len(points)))
    examples=[dict(r,example_kind='uniform_record_reservoir') for r in random_examples]
    for component in range(3):
        p=[r for r in points if r['component']==component]
        for sign in (-1,1):
            eligible=[r for r in p if sign*(r['cost_frac'][4]-r['cost_frac'][3])>0]
            eligible.sort(key=lambda r:sign*(r['cost_frac'][4]-r['cost_frac'][3]),reverse=True)
            examples.extend(dict(r,example_kind='negative_extreme' if sign<0 else 'positive_extreme') for r in eligible[:32])
    with (out/'examples.jsonl').open('w') as f:
        for r in examples: f.write(json.dumps({**common,**r},allow_nan=False)+'\n')
    size=sum(p.stat().st_size for p in out.glob('*') if p.is_file() and p.name not in ('decode.log','off.log'))
    if size>DEFAULTS['core_bytes']: raise ValueError('Core output budget exceeded; audit invalid')
    return dict(final_tu=sum(f['tu'] for f in frames),sampled_tu=len(tus),points=len(points),examples=len(examples),core_bytes=size,
                strata_scope='conditional sampled positions; uniform/disagreement kept separate',confidence_intervals='paired frame-block intervals for TU policy delta in pair_uncertainty.json; no coefficient independence assumption')


def decode_origin(m,manifest,decoder,pair,origin,args):
    out=args.output/origin;out.mkdir(parents=True,exist_ok=False)
    stream=pair['origins'][origin]; path=resolved(manifest.resolve().parent,stream['path'])
    env={k:v for k,v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=stream['native_policy'],TS_R13_DIAG_SCOPE='all',TS_R13_STATS='0',TS_R13_TRACE='0',TS_AUDIT_HASH=str((out/'reconstruction.csv').resolve()))
    command=[str(decoder),'-b',str(path),'-o','','-dph','1']
    identity=dict(schema=1,spec_version=SPEC,implementation_revision=REV,pair_id=pair['pair_id'],origin=origin,native_policy=stream['native_policy'],nominal_qp=pair['nominal_qp'],
        manifest_sha256=sha(manifest),decoder_sha256=sha(decoder),stream_sha256=sha(path),command=command,profile=args.profile,first_poc=args.first_poc,last_poc=args.last_poc,
        component=args.component,tu_filter=args.tu,policies=POLICIES,limits=m['limits'],pairing_status=pair['pairing_status'],source_identity=stream,population='FINAL_SELECTED')
    build_info=manifest.resolve().parent/'build_info.json'
    identity['build_identity']=read_json(build_info) if build_info.exists() else None
    env.update(TS_SCORE_AUDIT=str(out.resolve()),TS_AUDIT_PROFILE=args.profile,TS_AUDIT_FIRST=str(args.first_poc),TS_AUDIT_LAST=str(args.last_poc),TS_AUDIT_COMPONENT=str(args.component))
    if args.profile=='detail': env['TS_AUDIT_TU']=args.tu
    identity['observer_env']={k:v for k,v in env.items() if k.startswith('TS_')};save(out/'run.json',identity)
    start=time.monotonic();rc,truncated=bounded_run(command,env,out/'decode.log')
    identity.update(returncode=rc,elapsed_seconds=time.monotonic()-start)
    hashes=hash_frames(out/'reconstruction.csv');text=(out/'decode.log').read_text(errors='replace')
    sei_lines=[line for line in text.splitlines() if re.match(r'POC\s+\d+',line)]
    # Native app format may use [MD5:...,OK]; recognize both explicitly.
    sei_ok=sum(bool(re.search(r'MD5:.*(?:\(OK\)|,OK\]|\(OK\)\])',line)) for line in sei_lines)
    sei_present=any('MD5:' in line or 'CRC:' in line or 'Checksum:' in line for line in sei_lines)
    validation=dict(returncode=rc,expected_frames=pair.get('expected_frames'),actual_frames=len(hashes),sei_status='SEI_present_decode_returncode_verified' if sei_present and rc==0 else 'SEI_not_available',
                    sei_md5_ok_count=sei_ok,log_truncated=truncated,on_off_equal=None,native_replay=None)
    native_path=out/'native_validation.json'
    if native_path.exists(): validation['native_replay']=read_json(native_path)
    if rc or not hashes or truncated or not validation['native_replay'] or not validation['native_replay']['valid']:
        save(out/'decode_validation.json',validation);save(out/'run.json',identity);raise ValueError(f'{origin} decode/audit invalid; see {out}')
    if sei_present and sei_ok!=len(hashes):
        validation['sei_status']='SEI_partial_or_non_MD5'; save(out/'decode_validation.json',validation)
        # A successful return code checks present hashes; missing MD5s do not
        # certify a complete encoder-to-decoder MD5 population.
    if pair.get('expected_frames') is not None and len(hashes)!=pair['expected_frames']: raise ValueError('Frame count differs from manifest')
    if args.verify_off:
        off_env={k:v for k,v in env.items() if not k.startswith(('TS_SCORE_AUDIT','TS_AUDIT_'))};off_env['TS_AUDIT_HASH']=str((out/'reconstruction_off.csv').resolve())
        off_rc,off_truncated=bounded_run(command,off_env,out/'off.log')
        validation.update(off_returncode=off_rc,on_off_equal=off_rc==0 and not off_truncated and hashes==hash_frames(out/'reconstruction_off.csv'))
        if not validation['on_off_equal']:save(out/'decode_validation.json',validation);raise ValueError('Audit on/off reconstruction mismatch')
    identity['aggregation']=summarize(out,identity)
    validation['detail_status']='not_in_final_bitstream' if args.profile=='detail' and not identity['aggregation']['sampled_tu'] else 'ok'
    validation['audit_complete']=not validation['native_replay']['core_truncated'] and validation['native_replay']['skipped_budget']==0
    save(out/'decode_validation.json',validation);save(out/'run.json',identity)
    return origin,validation


def compare(reference,test,output):
    r,t=read_json(reference/'run.json'),read_json(test/'run.json')
    if r['origin']=='R13-2': reference,test,r,t=test,reference,t,r
    if r['origin']!='R13-1' or t['origin']!='R13-2' or r['pair_id']!=t['pair_id']:
        raise ValueError('Compare requires matched EQ/SP origin pair')
    for key in ('first_poc','last_poc','component','tu_filter','profile','policies','limits'):
        if r.get(key)!=t.get(key):raise ValueError('Asymmetric observation settings')
    valid=[read_json(p/'decode_validation.json') for p in (reference,test)]
    frames=[hash_frames(p/'reconstruction.csv') for p in (reference,test)]
    common_decoded=sorted(set(frames[0])&set(frames[1]))
    summaries=[read_csv(p/'frame_summary.csv') for p in (reference,test)]
    common=sorted(set(common_decoded)&{int(x['poc']) for x in summaries[0]}&{int(x['poc']) for x in summaries[1]});common_set=set(common)
    matrix=[read_csv(p/'tu_policy_matrix.csv') for p in (reference,test)]
    table=[]
    for component in range(3):
        values=[]
        for origin,rows,v in zip(('R13-1','R13-2'),summaries,valid):
            bypolicy={policy:[x for x in rows if x.get('policy')==policy and int(x['component'])==component and int(x['poc']) in common_set] for policy in ('KEEP_EQ','KEEP_SP')}
            eq,sp=bypolicy['KEEP_EQ'],bypolicy['KEEP_SP']; nz=sum(int(x['target_nz']) for x in sp);tu=sum(int(x['target_tu']) for x in sp)
            complete=r['profile']=='standard' and v['audit_complete'] and all(x['sampling_complete']=='True' for x in sp)
            rates=[sum(float(x['ht_policy_rate_frac']) for x in z) if complete and tu and z and all(x['ht_policy_rate_frac'] for x in z) else None for z in (eq,sp)]
            delta=(rates[1]-rates[0])/32768 if None not in rates else None
            row=dict(pair_id=r['pair_id'],origin=origin,component=component,common_frames=len(common),seen_tu=tu,seen_nz=nz,
                EQ_estimated_frac=rates[0],SP_estimated_frac=rates[1],SP_minus_EQ_estimated_bits=delta,
                bits_per_nonzero=delta/nz if delta is not None and nz else None,bits_per_tu=delta/tu if delta is not None and tu else None,
                audit_complete=complete,estimand='HT TU-total estimate / complete origin denominator; no BD-rate')
            values.append(row);table.append(row)
        table.append(dict(pair_id=r['pair_id'],origin='balanced',component=component,common_frames=len(common),seen_tu=None,seen_nz=None,
            EQ_estimated_frac=None,SP_estimated_frac=None,SP_minus_EQ_estimated_bits=None,
            bits_per_nonzero=sum(v['bits_per_nonzero'] for v in values)/2 if all(v['bits_per_nonzero'] is not None for v in values) else None,
            bits_per_tu=sum(v['bits_per_tu'] for v in values)/2 if all(v['bits_per_tu'] is not None for v in values) else None,
            audit_complete=all(v['audit_complete'] for v in values),estimand='equal origin mean, not pooled coefficients'))
    geometry=[{(x['poc'],x['component'],x['x'],x['y'],x['w'],x['h']):x for x in rows if x.get('id')} for rows in matrix]
    shared=set(geometry[0])&set(geometry[1])
    report=dict(pair_id=r['pair_id'],population='FINAL_SELECTED',common_observed_frames=common,common_decoded_frames=common_decoded,origin_only_frames=[sorted(set(f)-set(common_decoded)) for f in frames],
        encoding_identity_status=r['pairing_status'],sampled_geometry_intersection=len(shared),sampled_geometry_only_EQ=len(set(geometry[0])-shared),sampled_geometry_only_SP=len(set(geometry[1])-shared),
        shared_q_and_entry=sum(geometry[0][k]['q_hash']==geometry[1][k]['q_hash'] and geometry[0][k]['entry_hash']==geometry[1][k]['entry_hash'] for k in shared),
        rows=table,limitations=['Comparison is conditional on final-selected TS and each origin q/context.', 'Unknown server input/config identities remain unverified.', 'TU and coefficient samples are dependent; no independent-coefficient significance claim.', 'POC-block intervals condition on retained samples and a small content set; no cross-content generalization.'])
    output.mkdir(parents=True,exist_ok=True);save(output/'pair_comparison.json',report);csv_write(output/'pair_comparison.csv',table)
    scores=[]
    for component in range(3):
        for policy in POLICIES:
            group=[]
            for origin,rows,validation in zip(('R13-1','R13-2'),summaries,valid):
                chosen=[x for x in rows if x['policy']==policy and int(x['component'])==component and int(x['poc']) in common_set]
                den=sum(float(x['ht_distinguishable_population']) for x in chosen)
                correct=sum(float(x['ht_correct']) for x in chosen)
                regret=sum(float(x['ht_regret_frac']) for x in chosen)
                qualified=r['profile']=='standard' and validation['audit_complete'] and den>0
                row=dict(pair_id=r['pair_id'],component=component,policy=policy,origin=origin,
                         oracle_set='Cplus' if policy.endswith('_H') else 'C0',
                         ht_distinguishable_population=den,accuracy=correct/den if qualified else None,
                         mean_regret_bits=regret/den/32768 if qualified else None,
                         status='complete_conditional_sample' if qualified else 'no_distinguishable_samples_or_incomplete')
                group.append(row);scores.append(row)
            scores.append(dict(pair_id=r['pair_id'],component=component,policy=policy,origin='balanced',oracle_set=group[0]['oracle_set'],
                ht_distinguishable_population=None,accuracy=sum(x['accuracy'] for x in group)/2 if all(x['accuracy'] is not None for x in group) else None,
                mean_regret_bits=sum(x['mean_regret_bits'] for x in group)/2 if all(x['mean_regret_bits'] is not None for x in group) else None,
                status='equal_origin_mean' if all(x['accuracy'] is not None for x in group) else 'missing_origin_support'))
    csv_write(output/'score_comparison.csv',scores)
    save(output/'pair_uncertainty.json',paired_frame_intervals(summaries,common,valid))
    return report


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
    selected=[]
    for row in records:
        if row['kind']!='point' or not args.first_poc<=row['poc']<=args.last_poc:continue
        if component>=0 and row['component']!=component:continue
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
        saved=min(len(selected),args.max_examples),order='descending absolute SP-minus-EQ cost',
        population='retained sampled positions only; selection is for explanation, not representative frequencies'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--version',action='version',version=REV)
    sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--source',type=Path,required=True);prep.add_argument('--decoder',type=Path,required=True);prep.add_argument('--output',type=Path,required=True)
    inspect=sub.add_parser('inspect');inspect.add_argument('--manifest',type=Path,required=True)
    for name in ('decode-pair','detail'):
        d=sub.add_parser(name);d.add_argument('--manifest',type=Path,required=True);d.add_argument('--pair',required=True);d.add_argument('--output',type=Path,required=True);d.add_argument('--verify-off',action='store_true')
        d.add_argument('--profile',choices=['summary','standard','detail'],default='detail' if name=='detail' else 'standard')
        d.add_argument('--first-poc',type=int,default=0);d.add_argument('--last-poc',type=int,default=2147483647);d.add_argument('--component',choices=['Y','U','V','all'],default='all');d.add_argument('--tu');d.add_argument('--origin',choices=list(NATIVE))
        d.add_argument('--poc',type=int)
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
    pair=next((x for x in manifest['pairs'] if x['pair_id']==args.pair),None)
    if pair is None:raise ValueError('Unknown pair id')
    if args.output.exists():raise ValueError('New output directory required')
    if args.poc is not None:args.first_poc=args.last_poc=args.poc
    if args.first_poc<0 or args.last_poc<args.first_poc:raise ValueError('Invalid POC range')
    args.component={'Y':0,'U':1,'V':2,'all':-1}[args.component]
    if args.profile=='detail' and (args.first_poc!=args.last_poc or args.component<0 or not args.tu):raise ValueError('detail requires one POC, component and TU')
    origins=[args.origin] if args.origin else list(NATIVE)
    if any(o not in pair['origins'] for o in origins):raise ValueError('Missing paired origin; not silently substituted')
    args.output.mkdir(parents=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(decode_origin,manifest,args.manifest,decoder,pair,o,args) for o in origins]
        for future in futures:print(json.dumps(future.result(),ensure_ascii=False),flush=True)
    if len(origins)==2:compare(args.output/'R13-1',args.output/'R13-2',args.output)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        print(f'AUDIT ERROR: {error}',file=sys.stderr);sys.exit(2)
