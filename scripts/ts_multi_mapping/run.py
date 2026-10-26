#!/usr/bin/env python3
"""R15 decoder-only plan/replay/report. Streaming aggregation, no TU/bin dumps.

Use bounded_run.py around replay. Source streams are always decoded in their
native R13 mode. One worker is the default; two is the hard maximum.
"""
from __future__ import annotations
import argparse,collections,concurrent.futures,fcntl,hashlib,json,math,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ts_rule_lab'))
import ts_corpus as P
from reference import METHODS,REV

ROOT=Path(__file__).resolve().parents[2]
FIELDS=('number','mg','name','search','depth','spatial')
CATALOG=[dict(zip(FIELDS,m)) for m in METHODS]
IDS=[m[1] for m in METHODS]
SOURCES=['source/Lib/CommonLib/TsMultiMapping.h','source/Lib/CommonLib/TsRateReplay.h','source/Lib/CommonLib/TypeDef.h',
         'source/Lib/CommonLib/TsFixedPrediction.h','source/Lib/DecoderLib/tsaudit/MultiMapping.h',
         'source/Lib/DecoderLib/tsaudit/Replay.h','source/Lib/DecoderLib/tsaudit/Manager.h',
         'source/App/DecoderApp/decmain.cpp','scripts/ts_multi_mapping/run.py','scripts/ts_multi_mapping/reference.py',
         'scripts/ts_rule_lab/ts_corpus.py']


def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def catalog():
    return dict(revision=REV,protocol='TS-MG-ACTION-v1',methods=CATALOG,cost='TsFixedPrediction::syntaxCost; COEF_REMAIN_BIN_REDUCTION=5',
        candidates='1 plus distinct positive H; nonzero position n; fallback Current if n<3 except identity',
        priority='Current>1 first, 1, other positives ascending',weights=['11111','22111'],
        tie='strict first in priority; X score, mapping==B, canonical length, priority lexicographic',
        engine='PREFIX',new_subexperiments=18,existing_controls=[0,2,3])


def plan(args):
    raw=P.readj(args.manifest);base=args.manifest.resolve().parent
    if args.prefix:
        pairs=[p for p in raw['pairs'] if p['pair_id']=='Johnny_QP32_prefix17']
        tasks=[]
        if len(pairs)!=1:raise ValueError('Paired prefix not found')
        for p in pairs:
            for origin,mode in P.origins().items():
                r=p['origins'][origin]
                tasks.append(dict(key=p['pair_id']+'__'+origin,pair_id=p['pair_id'],sequence=p['sequence'],nominal_qp=p['nominal_qp'],origin=origin,
                    native_policy=mode,stream=str((base/r['path']).resolve()),stream_sha256=r['sha256'],bytes=r['bytes'],expected_frames=17))
        out=dict(tasks=tasks,sequences=[p['sequence'] for p in pairs],streams=2,formal_pairs=1)
    else:
        # Existing manifest pairing/4-QP/native-policy validation is reused.
        out=P.plan(args.manifest,args.output,12)
    out.update(revision=REV,manifest_sha256=P.sha(args.manifest),methods_sha256=digest(catalog()),
               scope='paired_prefix17' if args.prefix else 'full96_EOF',read_to_eof=True)
    P.save(args.output,out);P.save(args.output.parent/'methods.json',catalog())
    print(json.dumps(dict(plan=str(args.output),streams=out['streams'],scope=out['scope'],new_subexperiments=18)))


def validate_plan(plan):
    if plan['revision']!=REV or plan['methods_sha256']!=digest(catalog()):raise ValueError('Plan is not the frozen R15 catalogue')
    tasks=plan['tasks'];keys=[t['key'] for t in tasks]
    if not tasks or len(keys)!=len(set(keys)) or len(tasks)!=plan['streams']:raise ValueError('Missing/duplicate planned tasks')
    grid=collections.defaultdict(set)
    for t in tasks:
        if t['origin'] not in P.origins() or t['native_policy']!=P.origins()[t['origin']]:raise ValueError('Invalid source policy')
        point=(t['nominal_qp'],t['origin'])
        if point in grid[t['sequence']]:raise ValueError('Duplicate sequence/QP/origin')
        grid[t['sequence']].add(point)
    if plan['scope']=='full96_EOF':
        expected={(q,o) for q in (22,27,32,37) for o in P.origins()}
        if len(grid)!=12 or len(tasks)!=96 or any(v!=expected for v in grid.values()):raise ValueError('Incomplete full96 paired grid')
    elif plan['scope']=='paired_prefix17':
        if len(tasks)!=2 or set(grid)!={'Johnny'} or grid['Johnny']!={(32,'R13-1'),(32,'R13-2')} or any(t['expected_frames']!=17 for t in tasks):raise ValueError('Incomplete prefix pair')
    else:raise ValueError('Unknown observation scope')


def metric():
    return dict(tu=0,positions=0,nonzero=0,rate_frac=0,native_rate_frac=0,current_frac=0,static_eq_frac=0,static_sp_frac=0,
                improved_tu=0,equal_tu=0,worse_tu=0,positive_loss_frac=0,negative_loss_frac=0,
                score_lower_rate_lower=0,score_lower_rate_equal=0,score_lower_rate_higher=0,
                score_equal_rate_lower=0,score_equal_rate_equal=0,score_equal_rate_higher=0,
                score_higher_rate_lower=0,score_higher_rate_equal=0,score_higher_rate_higher=0,
                positive_loss_hist=[0]*32)


def percentile_bounds(hist,q):
    total=sum(hist)
    if not total:return None,None
    target=max(1,math.ceil(total*q));cumulative=0
    for b,count in enumerate(hist):
        cumulative+=count
        if cumulative>=target:return 2**b/32768,None if b==31 else 2**(b+1)/32768
    raise ValueError('Invalid loss histogram')


class Aggregate:
    def __init__(self):
        self.rows={};self.worst={};self.activity=[];self.header=None;self.footer=None;self.tus=0;self.positions=0;self.nz=0
    def accept(self,r):
        if self.footer is not None:raise ValueError('Record after footer')
        kind=r['kind']
        if kind=='header':
            if self.header or r['revision']!=REV or r['action_protocol']!='TS-MG-ACTION-v1' or r['method_mg_ids']!=IDS or r['rate_scale']!=32768:raise ValueError('Header/catalogue mismatch')
            self.header=r;return
        if self.header is None:raise ValueError('Missing header')
        if kind=='activity':
            if len(self.activity)>=63:raise ValueError('Too many activity rows')
            self.activity.append(r);return
        if kind=='footer':self.footer=r;return
        if kind!='tu':raise ValueError('Unknown record')
        if any(len(r[k])!=21 for k in ('rates_frac','scores','action_hashes')):raise ValueError('Missing method')
        if any(not isinstance(x,int) or x<0 for x in r['rates_frac']):raise ValueError('Invalid/missing rate')
        if r['rates_frac'][4]!=r['rates_frac'][8] or r['action_hashes'][4]!=r['action_hashes'][8]:raise ValueError('G2/N2 mismatch')
        if r['positions']!=r['w']*r['h'] or not 0<=r['nonzero']<=r['positions']:raise ValueError('Bad population')
        if r['slice_type'] not in ('I','P','B','L') or r['is_intra_cu'] not in (0,1):raise ValueError('Slice/CU schema')
        self.tus+=1;self.positions+=r['positions'];self.nz+=r['nonzero']
        strata=[('component',str(r['component'])),('slice_type',r['slice_type']),('is_intra_cu',str(r['is_intra_cu'])),('size',f"{r['w']}x{r['h']}")]
        for m,mg in enumerate(IDS):
            loss=r['rates_frac'][m]-r['rates_frac'][1]
            score_ref=2 if METHODS[m][5] else 1
            ds=r['scores'][m]-r['scores'][score_ref]
            score_loss=r['rates_frac'][m]-r['rates_frac'][score_ref]
            sign=lambda x:'lower' if x<0 else 'higher' if x>0 else 'equal'
            for dimension,value in strata:
                key=(dimension,value,mg)
                a=self.rows.get(key)
                if a is None:a=metric();self.rows[key]=a
                a['tu']+=1;a['positions']+=r['positions'];a['nonzero']+=r['nonzero']
                a['rate_frac']+=r['rates_frac'][m];a['native_rate_frac']+=r['native_rate_frac']
                a['current_frac']+=r['rates_frac'][0];a['static_eq_frac']+=r['rates_frac'][1];a['static_sp_frac']+=r['rates_frac'][2]
                a['improved_tu']+=loss<0;a['equal_tu']+=loss==0;a['worse_tu']+=loss>0
                a['positive_loss_frac']+=max(0,loss);a['negative_loss_frac']+=min(0,loss)
                a[f'score_{sign(ds)}_rate_{sign(score_loss)}']+=1
                if loss>0:a['positive_loss_hist'][min(31,loss.bit_length()-1)]+=1
            # Three adverse and three favorable cases per method/stream, fixed cap.
            if not loss:continue
            key=(mg,'loss' if loss>=0 else 'saving');items=self.worst.setdefault(key,[])
            if len(items)==3 and abs(loss)<=abs(items[-1]['loss_frac']):continue
            case={k:r[k] for k in ('poc','component','x','y','w','h','slice_type','is_intra_cu','nonzero','q_hash','entry_hash','scan_hash')}
            case.update(mg=mg,loss_frac=loss,score_delta=ds,action_hash=r['action_hashes'][m],rate_frac=r['rates_frac'][m],reference_frac=r['rates_frac'][1])
            items.append(case);items.sort(key=lambda x:(abs(x['loss_frac']),-x['poc']),reverse=True);del items[3:]
    def finish(self):
        f=self.footer
        if not f or not f['complete'] or f['methods_complete']!=21 or f['verified_tu']!=self.tus or f['target_tu']!=self.tus or f['positions']!=self.positions or f['nonzero']!=self.nz:raise ValueError('Incomplete replay/population')
        if {(a['component'],a['mg']) for a in self.activity}!={(c,m) for c in range(3) for m in IDS}:raise ValueError('Incomplete activity')
        if f['all_ts_tu']!=f['target_tu']+f['bdpcm_tu']+f['unsupported_tu']:raise ValueError('Filter denominator mismatch')
        for mg in IDS:
            observed=[a for a in self.activity if a['mg']==mg]
            if sum(a['positions'] for a in observed)!=self.positions or sum(a['nonzero'] for a in observed)!=self.nz:raise ValueError('Activity denominator mismatch')
        return dict(header=self.header,footer=f,
            aggregates=[dict(dimension=k[0],value=k[1],mg=k[2],**v) for k,v in sorted(self.rows.items())],
            mapping_activity=self.activity,worst_cases=[v for rows in self.worst.values() for v in rows])


def run_task(task,args,scope):
    root=args.output/task['key'];root.mkdir(parents=True,exist_ok=True)
    stream=Path(task['stream']);decoder=args.decoder.resolve()
    if stream.stat().st_size!=task['bytes'] or P.sha(stream)!=task['stream_sha256']:raise ValueError('Input SHA/length mismatch')
    with stream.open('rb') as f:
        if f.read(64).startswith(b'version https://git-lfs'):raise ValueError('LFS pointer is not a stream')
    request=dict(revision=REV,catalogue_sha256=digest(catalog()),decoder_sha256=P.sha(decoder),stream_sha256=task['stream_sha256'],
        native_policy=task['native_policy'],scope=scope,verify_off=args.verify_off,fixtures=args.fixtures,max_output_mib=args.max_output_mib,
        source_sha256={s:P.sha(ROOT/s) for s in SOURCES},runner_sha256=P.sha(__file__),full_file=True)
    request['source_manifest_sha256']=digest(request['source_sha256'])
    request['compiled_observer']=True
    done=root/'done.json';data=root/'summary.json'
    if done.exists():
        old=P.readj(done)
        if args.resume and old['complete'] and old['request']==request and data.exists() and old['data_sha256']==P.sha(data):return old
        raise ValueError('Existing result/resume identity mismatch; use a new output directory')
    attempt=0
    while (root/f'attempt_{attempt:02d}').exists():attempt+=1
    if attempt and not args.resume:raise ValueError('Incomplete prior attempt; use --resume or new output')
    if attempt and P.readj(root/'request.json')!=request:raise ValueError('Retry fingerprint mismatch')
    P.save(root/'request.json',request);run=root/f'attempt_{attempt:02d}';run.mkdir()
    env={k:v for k,v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=task['native_policy'],TS_R13_DIAG_SCOPE='all',TS_R15_AUDIT='1',TS_AUDIT_HASH=str((run/'reconstruction.csv').resolve()),MALLOC_ARENA_MAX='2')
    if args.fixtures:env['TS_R15_FIXTURES']=str((run/'fixtures').resolve())
    cmd=[str(decoder),'-b',str(stream),'-o','','-dph','1'];start=time.monotonic();proc=None;agg=Aggregate();sei=ok=log_bytes=0
    try:
        proc=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='strict')
        with (run/'decode.log').open('w') as log:
            while True:
                line=proc.stdout.readline(65537)
                if not line:break
                if len(line)>65536:raise ValueError('Overlong output record')
                if line.startswith('@TS_R15 '):agg.accept(json.loads(line[8:]))
                else:
                    if line.startswith('POC') and 'MD5:' in line:sei+=1;ok+=',OK]' in line or '(OK)' in line
                    if log_bytes+len(line.encode())<=1<<20:log.write(line);log_bytes+=len(line.encode())
        proc.stdout.close();rc=proc.wait()
        if rc:raise ValueError(f'Decoder failed: {rc}')
        result=agg.finish()
        if agg.header['native_policy']!=({'R13-1':98,'R13-2':99}[task['origin']]):raise ValueError('Wrong source mode')
        hashes=(run/'reconstruction.csv').read_text().splitlines();pocs=[int(x.split(',')[0]) for x in hashes]
        if not pocs or len(pocs)!=len(set(pocs)):raise ValueError('Empty/duplicate frame hash census')
        if task.get('expected_frames') is not None and len(pocs)!=task['expected_frames']:raise ValueError('Frame coverage differs')
        if sei!=ok:raise ValueError('Encoder SEI hash mismatch')
        off_equal=None
        if args.verify_off:
            env.pop('TS_R15_AUDIT');env.pop('TS_R15_FIXTURES',None);env['TS_AUDIT_HASH']=str((run/'reconstruction_off.csv').resolve())
            # Consume off-log into a capped file, never retain the whole output in RAM.
            proc=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            count=0
            with (run/'off.log').open('w') as f:
                for line in proc.stdout:
                    if count+len(line.encode())<=1<<20:f.write(line);count+=len(line.encode())
            proc.stdout.close();rc=proc.wait()
            off_equal=rc==0 and (run/'reconstruction.csv').read_bytes()==(run/'reconstruction_off.csv').read_bytes()
            if not off_equal:raise ValueError('Observer changed reconstruction')
        encoded=json.dumps(result,separators=(',',':'),allow_nan=False)+'\n'
        if len(encoded.encode())>args.max_output_mib*(1<<20):raise ValueError('Summary exceeds output limit')
        data.write_text(encoded)
        record=dict(task=task,request=request,complete=True,frames=len(pocs),sei_status='all_frames_MD5_verified' if sei==ok==len(pocs) else 'partial_or_absent_SEI',
                    on_off_equal=off_equal,data_sha256=P.sha(data),summary=str(data.resolve()),footer=agg.footer,elapsed_seconds=time.monotonic()-start,
                    reconstruction_sha256=P.sha(run/'reconstruction.csv'),summary_bytes=len(encoded.encode()),attempt=attempt)
        record['source_base_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        P.save(done,record);return record
    except BaseException as e:
        if proc and proc.poll() is None:proc.kill();proc.wait()
        P.save(run/'failure.json',dict(complete=False,error=str(e),request=request,footer=agg.footer));raise


def replay(args):
    plan=P.readj(args.plan)
    validate_plan(plan)
    if args.dry_run:
        print(json.dumps(dict(streams=len(plan['tasks']),jobs=args.jobs,scope=plan['scope'],methods=21,commands='DecoderApp only; EOF; no reconstruction video',max_summary_mib_per_stream=args.max_output_mib)));return
    if subprocess.check_output([str(args.decoder.resolve()),'--ts-r15-version'],text=True).strip()!=REV:raise ValueError('Wrong/disabled R15 decoder')
    args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/'.r15.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        good=[];bad=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures={pool.submit(run_task,t,args,plan['scope']):t for t in plan['tasks']}
            for future in concurrent.futures.as_completed(futures):
                task=futures[future]
                try:
                    r=future.result();good.append(r);print('OK',task['key'],'frames',r['frames'],'TU',r['footer']['target_tu'],flush=True)
                except Exception as e:bad.append(dict(key=task['key'],error=str(e)));print('FAIL',task['key'],str(e),flush=True)
        index=dict(revision=REV,scope=plan['scope'],plan=plan,plan_sha256=P.sha(args.plan),methods_sha256=digest(catalog()),expected_streams=len(plan['tasks']),
                   complete=not bad and len(good)==len(plan['tasks']),records=sorted(good,key=lambda r:r['task']['key']),failures=bad)
        P.save(args.output/'dataset_index.json',index)
        if not index['complete']:raise ValueError('Incomplete data; failed methods/streams are not zero')


def report(args):
    index=P.readj(args.index)
    if not index['complete'] or index['revision']!=REV or index['methods_sha256']!=digest(catalog()):raise ValueError('Incomplete/wrong-version dataset')
    validate_plan(index['plan'])
    if {r['task']['key'] for r in index['records']}!={t['key'] for t in index['plan']['tasks']}:raise ValueError('Missing/extra completed task')
    if len(index['records'])!=index['expected_streams']:raise ValueError('Incomplete record list')
    out=args.output;out.mkdir(parents=True,exist_ok=False);rows=[];activity=[];worst=[];coverage=[];strata=[]
    for record in index['records']:
        if not record['complete'] or not record['footer']['complete'] or P.sha(record['summary'])!=record['data_sha256']:raise ValueError('Changed/incomplete summary')
        data=P.readj(record['summary']);t=record['task'];identity={k:t[k] for k in ('key','sequence','nominal_qp','origin')}
        coverage.append(dict(**identity,frames=record['frames'],**record['footer'],on_off_equal=record['on_off_equal'],sei_status=record['sei_status']))
        for row in data['aggregates']:
            v=dict(**identity,**row,score_reference='STATIC_SP' if next(m for m in METHODS if m[1]==row['mg'])[5] else 'STATIC_EQ')
            method=next(m for m in CATALOG if m['mg']==row['mg']);v.update(number=method['number'],name=method['name'])
            v['rate_bits']=row['rate_frac']/32768
            v['rate_bits_per_tu']=row['rate_frac']/32768/row['tu'] if row['tu'] else None
            v['rate_bits_per_nz']=row['rate_frac']/32768/row['nonzero'] if row['nonzero'] else None
            for ref in ('current','static_eq','static_sp'):
                delta=(row[ref+'_frac']-row['rate_frac'])/32768
                v[ref+'_saving_bits']=delta
                v[ref+'_saving_bits_per_tu']=delta/row['tu'] if row['tu'] else None
                v[ref+'_saving_bits_per_nz']=delta/row['nonzero'] if row['nonzero'] else None
            for pct in (50,90,99):
                low,high=percentile_bounds(row['positive_loss_hist'],pct/100)
                v[f'positive_loss_p{pct}_lower_bits']=low;v[f'positive_loss_p{pct}_upper_bits_exclusive']=high
            # Exact sums, coarse bounded histogram: do not label these exact percentiles.
            v['positive_loss_hist']=json.dumps(v['positive_loss_hist'],separators=(',',':'))
            strata.append(v)
            if row['dimension']=='component':rows.append(v)
        for r in data['mapping_activity']:activity.append(dict(**identity,**{k:json.dumps(v,separators=(',',':')) if isinstance(v,list) else v for k,v in r.items()}))
        for r in data['worst_cases']:worst.append(dict(**identity,**r))
    totals={}
    for r in rows:
        key=(r['sequence'],r['nominal_qp'],r['origin'],r['mg']);a=totals.setdefault(key,collections.Counter())
        for name in ('rate_frac','current_frac','static_eq_frac','static_sp_frac','positions','nonzero','tu','positive_loss_frac','improved_tu','equal_tu','worse_tu'):a[name]+=r[name]
    pairs=[];seqs={};summary=[]
    contents=sorted({t[0] for t in totals})
    for seq in contents:
        qps=sorted({t[1] for t in totals if t[0]==seq})
        for qp in qps:
            for method in CATALOG:
                mg=method['mg'];origins=[totals.get((seq,qp,o,mg)) for o in ('R13-1','R13-2')]
                valid=all(v and v['nonzero']>0 for v in origins)
                row=dict(sequence=seq,qp=qp,mg=mg,number=method['number'],name=method['name'],both_sources=valid)
                for ref in ('current','static_eq','static_sp'):
                    row[ref+'_saving_bits_per_nz']=sum((v[ref+'_frac']-v['rate_frac'])/v['nonzero']/32768 for v in origins)/2 if valid else None
                pairs.append(row)
                for ref in ('current','static_eq','static_sp'):
                    values=[r[ref+'_saving_bits_per_nz'] for r in pairs if r['sequence']==seq and r['mg']==mg]
                    if set(qps)=={22,27,32,37} and len(values)==4 and all(v is not None for v in values):seqs[(seq,mg,ref)]=sum(values)/4
    for method in CATALOG:
        mg=method['mg'];r=dict(**method,scope=index['scope'],contents=len(contents),streams=len(index['records']))
        for ref in ('current','static_eq','static_sp'):
            vals=[seqs.get((s,mg,ref)) for s in contents]
            r[ref+'_balanced_bits_per_nz']=sum(vals)/len(vals) if len(contents)==12 and all(v is not None for v in vals) else None
            r[ref+'_pooled_saving_bits']=sum(v[ref+'_frac']-v['rate_frac'] for k,v in totals.items() if k[3]==mg)/32768
        summary.append(r)
    P.csvout(out/'coverage.csv',coverage);P.csvout(out/'by_stream_component.csv',rows);P.csvout(out/'strata.csv',strata)
    P.csvout(out/'by_sequence_qp.csv',pairs);P.csvout(out/'method_summary.csv',summary);P.csvout(out/'mapping_activity.csv',activity)
    P.csvout(out/'score_rate_disagreement.csv',[{k:v for k,v in r.items() if k.startswith('score_') or k in ('key','sequence','nominal_qp','origin','mg','value','tu','positions','nonzero')} for r in rows])
    P.csvout(out/'worst_cases.csv',worst)
    # Descriptive whole-content ranking + leave-one-content selection (not blind validation).
    selection=[]
    if len(contents)==12 and all((s,m['mg'],'static_eq') in seqs for s in contents for m in CATALOG):
        for held in contents:
            ranked=sorted((m for m in CATALOG if m['number']),key=lambda m:(-sum(seqs[(s,m['mg'],'static_eq')] for s in contents if s!=held)/11,m['number']))
            best=ranked[0];selection.append(dict(held_out=held,selected_r15=best['number'],mg=best['mg'],training_mean=sum(seqs[(s,best['mg'],'static_eq')] for s in contents if s!=held)/11,held_out_value=seqs[(held,best['mg'],'static_eq')],worst_content=min(seqs[(s,best['mg'],'static_eq')] for s in contents),status='development-corpus descriptive holdout; not blind'))
    P.csvout(out/'selection_report.csv',selection)
    census=dict(frames=sum(r['frames'] for r in coverage),target_tu=sum(r['target_tu'] for r in coverage),
                positions=sum(r['positions'] for r in coverage),nonzero=sum(r['nonzero'] for r in coverage))
    historical=dict(frames=26000,target_tu=754151,positions=125949812,nonzero=3856051)
    P.save(out/'population_check.json',dict(observed=census,historical_full96=historical,
        scope=index['scope'],matches_historical=census==historical if index['scope']=='full96_EOF' else None,
        status='acceptance_prefix_not_full_population' if index['scope']!='full96_EOF' else 'match' if census==historical else 'REQUIRES_INPUT_OR_FILTER_EXPLANATION'))
    P.save(out/'methods.json',catalog());P.save(out/'run_receipts.json',index)
    P.save(out/'manifest.json',dict(revision=REV,scope=index['scope'],files={p.name:P.sha(p) for p in sorted(out.iterdir()) if p.is_file()}))
    (out/'README.md').write_text(f'# R15 conditional replay\n\nScope: `{index["scope"]}`; {len(index["records"])} streams. Full21 methods, final-q conditional TSRC fractional costs; not BD-rate. YUV costs add directly. Balanced estimate requires both origins, four QPs and all 12 contents; otherwise blank. Loss histograms use exact fractional-bit sums and logarithmic bins `[2^b,2^(b+1)) / 32768`, with final bucket b=31 open-ended. Percentiles are bounds, not exact values. No per-position oracle or full sampling inference. Selector observation timing includes instrumentation; it is not codec complexity. Full production encoder time remains unmeasured.\n')
    print(json.dumps(dict(output=str(out),scope=index['scope'],streams=len(index['records']))))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    q=sub.add_parser('plan');q.add_argument('--manifest',type=Path,default=ROOT/'deliveries/r13_decode_audit_impl2/manifest.json');q.add_argument('--output',type=Path,required=True);q.add_argument('--prefix',action='store_true')
    q=sub.add_parser('replay');q.add_argument('--plan',type=Path,required=True);q.add_argument('--decoder',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    q.add_argument('--jobs',type=int,choices=(1,2),default=1);q.add_argument('--max-output-mib',type=int,default=4);q.add_argument('--verify-off',action='store_true');q.add_argument('--fixtures',action='store_true',help='at most two small TU/action snapshots per stream; for validation only');q.add_argument('--resume',action='store_true');q.add_argument('--dry-run',action='store_true')
    q=sub.add_parser('report');q.add_argument('--index',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.cmd=='replay' and args.max_output_mib<=0:p.error('Positive output limit required')
    {'plan':plan,'replay':replay,'report':report}[args.cmd](args)

if __name__=='__main__':main()
