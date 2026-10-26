#!/usr/bin/env python3
"""Full-sequence TS corpus pipeline. All manifest pairs, both origins, EOF.

Python >=3.10 standard library only; the native decoder has no ML dependency.
No subcommand launches EncoderApp or uses raw source video.
"""
from __future__ import annotations
import argparse,concurrent.futures,csv,gzip,hashlib,json,os,subprocess,sys,time
from collections import Counter,defaultdict
from pathlib import Path
import ts_learning as L


def readj(p):return json.loads(Path(p).read_text())
def save(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()
def csvout(p,rows):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['status']);w.writeheader();w.writerows(rows)
def records(p):
    with gzip.open(p,'rt') as f:
        for line in f:yield json.loads(line)
def tu_key(t):return '_'.join(str(t[k]) for k in ('poc','component','x','y','w','h'))
def origins():return {'R13-1':'r13_keep_hit_uniform','R13-2':'r13_keep_hit_spatial'}


def plan(manifest,out,expected_sequences=None):
    manifest=Path(manifest).resolve();m=readj(manifest);tasks=[];seen=set();cells=set();grid=defaultdict(set)
    for pair in m['pairs']:
        if 'prefix' in pair['pair_id'].lower():continue
        if pair['pair_id'] in seen:raise ValueError('Duplicate pair')
        seen.add(pair['pair_id']);seq=pair['sequence'];qp=pair['nominal_qp']
        if (seq,qp) in cells:raise ValueError('Duplicate content/QP pair')
        cells.add((seq,qp));grid[seq].add(qp)
        if set(pair['origins'])!=set(origins()):raise ValueError('Missing symmetric origin')
        for origin,native in origins().items():
            r=pair['origins'][origin]
            if r['native_policy']!=native or r.get('scope')!='all':raise ValueError('Wrong source policy/scope')
            path=Path(r['path']);path=path if path.is_absolute() else manifest.parent/path
            tasks.append(dict(key=pair['pair_id']+'__'+origin,pair_id=pair['pair_id'],sequence=seq,
               nominal_qp=qp,origin=origin,native_policy=native,stream=str(path.resolve()),stream_sha256=r['sha256'],
               bytes=r['bytes'],expected_frames=pair.get('expected_frames'),encoding_identity_status=pair.get('pairing_status')))
    if not tasks:raise ValueError('Empty manifest')
    if any(q!={22,27,32,37} for q in grid.values()):raise ValueError('Missing/nonregistered QP coverage')
    if expected_sequences is not None and len(grid)!=expected_sequences:raise ValueError('Unexpected sequence count')
    result=dict(revision=L.REV,manifest_sha256=sha(manifest),sequences=sorted(grid),formal_pairs=len(seen),
        streams=len(tasks),observation='all final TSRC TUs; all file frames to EOF; no sample cap',tasks=tasks)
    save(out,result);return result


def run_task(task,decoder,root,verify_off=False,schedule_dir=None,max_gib=8,resume=False,with_labels=False):
    out=Path(root)/task['key'];out.mkdir(parents=True,exist_ok=True)
    stream=Path(task['stream']);decoder=Path(decoder).resolve()
    if stream.stat().st_size!=task['bytes'] or sha(stream)!=task['stream_sha256']:raise ValueError('Stream SHA/length mismatch')
    with stream.open('rb') as f:
        if f.read(50).startswith(b'version https://git-lfs'):raise ValueError('LFS pointer, not bitstream')
    schedules=Path(schedule_dir)/f'{task["key"]}.pred' if schedule_dir else None
    if schedules:
        meta=readj(schedules.with_suffix('.json'))
        if meta.get('task')!=task['key'] or meta.get('schedule_sha256')!=sha(schedules):
            raise ValueError('Schedule sidecar identity/hash mismatch')
    else:meta=None
    request=dict(revision=L.REV,stream_sha256=sha(stream),decoder_sha256=sha(decoder),
      driver_sha256=sha(__file__),scoring_sha256=sha(L.__file__),verify_off=verify_off,with_labels=with_labels,
      schedule_sha256=sha(schedules) if schedules else None,native_policy=task['native_policy'],full_file=True,
      method_ids=meta.get('methods') if meta else None,catalogue_sha256=meta.get('catalogue_sha256') if meta else None)
    done=out/'done.json';data=out/'corpus.jsonl.gz'
    if resume and done.exists():
        old=readj(done)
        if old['request']==request and old['complete'] and data.exists() and sha(data)==old['data_sha256']:return dict(old,data=str(data.resolve()))
        raise ValueError('Resume fingerprint or output mismatch; use fresh output')
    if done.exists() or data.exists():raise ValueError(f'Output exists: {out}')
    old_request=out/'request.json'
    if old_request.exists():
        if not resume or readj(old_request)['request']!=request:raise ValueError('Incomplete output requires matching --resume or a fresh directory')
        for name in ('corpus.partial.gz','reconstruction.csv','reconstruction_off.csv','decode.log','failure.json'):
            (out/name).unlink(missing_ok=True)
    if subprocess.check_output([str(decoder),'--ts-corpus-version'],text=True).strip()!=L.REV:
        raise ValueError('Rebuild corpus decoder; old impl2 cannot run this full rule benchmark')
    env={k:v for k,v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=task['native_policy'],TS_R13_DIAG_SCOPE='all',TS_CORPUS='1',
      TS_CORPUS_POINTS='1' if with_labels else '0',TS_AUDIT_HASH=str((out/'reconstruction.csv').resolve()))
    if schedules:env['TS_CORPUS_SCHEDULE']=str(schedules.resolve())
    command=[str(decoder),'-b',str(stream),'-o','','-dph','1']
    save(out/'request.json',dict(task=task,request=request,command=command))
    part=out/'corpus.partial.gz';footer=None;headers=0;tus=0;points=0;logsize=0;total_raw=0;sei_ok=0;sei_present=0
    started=time.monotonic();proc=None
    try:
        proc=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='strict')
        with gzip.open(part,'wt',compresslevel=3) as output,(out/'decode.log').open('w') as log:
            for line in proc.stdout:
                if line.startswith('@TS_CORPUS '):
                    text=line[len('@TS_CORPUS '):];r=json.loads(text)
                    if footer is not None:raise ValueError('Record after corpus footer')
                    if r['kind']=='header':
                        headers+=1
                        if r['actions']!=L.ACTIONS or r['revision']!=L.REV or r['mode']!=('evaluate' if schedules else 'labels') or bool(r['all_point_labels'])!=with_labels:raise ValueError('Corpus schema mismatch')
                    elif r['kind']=='tu':tus+=1;points+=len(r.get('points',[]))
                    elif r['kind']=='footer':footer=r
                    else:raise ValueError('Unknown corpus record')
                    output.write(text);total_raw+=len(text.encode())
                    if total_raw>max_gib*(1<<30):raise ValueError('Corpus raw-size hard limit reached; rerun with larger bound')
                else:
                    if line.startswith('POC') and 'MD5:' in line:
                        sei_present+=1;sei_ok+=',OK]' in line or '(OK)' in line
                    if logsize<8*(1<<20):log.write(line);logsize+=len(line.encode())
        proc.stdout.close()
        rc=proc.wait()
        if rc or headers!=1 or not footer or not footer['complete'] or footer['verified_tu']!=tus or footer['labeled_positions']!=points:
            raise ValueError(f'Incomplete decode/corpus: exit={rc}, footer={footer}')
        hashes=(out/'reconstruction.csv').read_text().splitlines()
        pocs=[int(x.split(',')[0]) for x in hashes]
        if not hashes or len(pocs)!=len(set(pocs)):raise ValueError('Empty/duplicate frame hash census')
        if task['expected_frames'] is not None and len(hashes)!=task['expected_frames']:raise ValueError('Expected frame count mismatch')
        off_equal=None
        if verify_off:
            env2={k:v for k,v in env.items() if k not in ('TS_CORPUS','TS_CORPUS_SCHEDULE','TS_CORPUS_POINTS')}
            env2['TS_AUDIT_HASH']=str((out/'reconstruction_off.csv').resolve())
            off=subprocess.run(command,env=env2,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
            off_equal=off.returncode==0 and (out/'reconstruction.csv').read_bytes()==(out/'reconstruction_off.csv').read_bytes()
            if not off_equal:raise ValueError('Corpus on/off reconstruction mismatch')
        part.rename(data)
        result=dict(task=task,request=request,complete=True,footer=footer,frames=len(hashes),
            sei_status='all_frames_MD5_verified' if sei_present==sei_ok==len(hashes) else 'partial_or_unavailable_SEI',
            on_off_equal=off_equal,data_sha256=sha(data),elapsed_seconds=time.monotonic()-started,
            data=str(data.resolve()),raw_bytes=total_raw,compressed_bytes=data.stat().st_size)
        save(done,result);return result
    except BaseException as e:
        if proc and proc.poll() is None:proc.kill();proc.wait()
        save(out/'failure.json',dict(error=str(e),request=request,footer=footer,complete=False));raise


def collect(args):
    p=readj(args.plan);results=[];failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures={pool.submit(run_task,t,args.decoder,args.output,args.verify_off,args.schedule_dir,args.max_gib,args.resume,args.with_labels):t for t in p['tasks']}
        for f in concurrent.futures.as_completed(futures):
            try:r=f.result();results.append(r);print('OK',r['task']['key'],r['frames'],r['footer']['verified_tu'],flush=True)
            except Exception as e:failures.append(dict(task=futures[f]['key'],error=str(e)));print('FAIL',failures[-1],flush=True)
    index=dict(revision=L.REV,plan_sha256=sha(args.plan),sequences=p['sequences'],expected_streams=p['streams'],
               completed_streams=len(results),complete=not failures and len(results)==p['streams'],
               records=sorted(results,key=lambda r:r['task']['key']),failures=failures)
    save(Path(args.output)/'dataset_index.json',index)
    if not index['complete']:raise ValueError('Not all formal streams completed; no complete-dataset conclusion allowed')


def complete_index(p):
    index=readj(p)
    if not index['complete'] or index['completed_streams']!=index['expected_streams']:raise ValueError('Corpus coverage incomplete')
    if index.get('revision')!=L.REV:raise ValueError('Unexpected corpus revision')
    if len(index['records'])!=index['expected_streams']:raise ValueError('Index record count mismatch')
    keys=[r['task']['key'] for r in index['records']]
    if len(set(keys))!=len(keys):raise ValueError('Duplicate stream, not full coverage')
    grid=defaultdict(set);cells=set()
    for r in index['records']:
        if not r.get('complete') or not r.get('footer',{}).get('complete'):raise ValueError('Incomplete stream footer')
        if sha(r['data'])!=r['data_sha256']:raise ValueError('Corpus changed since completion')
        t=r['task'];cell=(t['sequence'],t['nominal_qp'],t['origin'])
        if cell in cells:raise ValueError('Duplicate content/QP/origin record')
        cells.add(cell);grid[t['sequence']].add((t['nominal_qp'],t['origin']))
    expected={(q,o) for q in (22,27,32,37) for o in origins()}
    if set(grid)!=set(index['sequences']) or any(v!=expected for v in grid.values()):raise ValueError('Incomplete content/QP/origin Cartesian coverage')
    return index


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    q=sub.add_parser('plan');q.add_argument('--manifest',type=Path,required=True);q.add_argument('--output',type=Path,required=True);q.add_argument('--expect-sequences',type=int,default=12)
    q=sub.add_parser('collect');q.add_argument('--plan',type=Path,required=True);q.add_argument('--decoder',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    q.add_argument('--schedule-dir',type=Path);q.add_argument('--jobs',type=int,default=4);q.add_argument('--max-gib',type=float,default=16)
    q.add_argument('--verify-off',action='store_true');q.add_argument('--resume',action='store_true');q.add_argument('--with-labels',action='store_true')
    a=p.parse_args()
    if a.cmd=='plan':
        result=plan(a.manifest,a.output,a.expect_sequences);print(json.dumps({'sequences':result['sequences'],'streams':result['streams']}))
    else:
        if a.jobs<1 or a.max_gib<=0:raise ValueError('Positive jobs and size bound required')
        collect(a)


if __name__=='__main__':main()
