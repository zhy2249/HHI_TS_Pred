#!/usr/bin/env python3
"""Extract R9 final-Writer and owner-search populations separately; no BD claims."""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from ts_predictor_naming import R9_MODE_NUMBERS

def parse(text,mode,kind):
    prefix='TS_R9_'+kind; header=None; rows=[]
    for line in text.splitlines():
        if line.startswith(prefix+'_HEADER '):
            if header is not None: raise ValueError('Duplicate section')
            header=line.split(' ',1)[1].split(',')
        elif line.startswith(prefix+' '):
            values=line.split(' ',1)[1].split(',')
            if header is None or len(values)!=len(header): raise ValueError('Malformed R9 row')
            r={k:float(v) if k=='local_gain_sum' else int(v) for k,v in zip(header,values)}
            if r['mode']!=mode: raise ValueError('Wrong R9 mode')
            if kind=='STATS':
                if r['cutoff']==0 and (r['remap_vs_r8_12'] or r['regular_count']): raise ValueError('Bypass remapping')
                if r['cutoff'] not in (-1,0,2,10): raise ValueError('Invalid cutoff')
                if r['regular_nonzero']>r['regular_count']: raise ValueError('Invalid denominator')
                if r['remap_vs_r8_12']>r['regular_nonzero']: raise ValueError('Invalid remap count')
                if r.get('validation_regret_selected_q15_sum',0): raise ValueError('Expert failed to minimize validation loss')
            elif not math.isfinite(r['local_gain_sum']) or r['local_gain_sum']<0: raise ValueError('Invalid owner gain')
            rows.append(r)
    return rows

def write(path,rows):
    if not rows:
        path.write_text('') # Never leave an earlier population's stale CSV.
        return
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('root',type=Path); p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(); jobs={}
    for path in args.root.rglob('summary.csv'):
        with path.open(newline='') as f:
            for r in csv.DictReader(f):
                if r.get('fixed_predictor') in R9_MODE_NUMBERS and r.get('error_info')=='pass':
                    log=Path(r['encode_log']).resolve()
                    if not log.is_file(): raise FileNotFoundError(log)
                    jobs[log]=r
    detailed=[]; searches=[]; byjob=[]; status=[]
    dimensions={'mode','component','width','height','cu_qp','intra','bdpcm','cg_count','cg_index','n','n1','d','cutoff','target_bucket',
                'current_magnitude','current_repeats','validation_size','distinct_experts','selected_expert'}
    for log,j in sorted(jobs.items()):
        m=R9_MODE_NUMBERS[j['fixed_predictor']]; text=log.read_text(errors='replace')
        if f'TS R9 revision=R9-20260927-v1; mode={m};' not in text: raise ValueError(f'Wrong executable: {log}')
        meta=dict(job=j['name'],sequence=j['sequence'],qp=j['qp'],runtime=j['fixed_predictor'],encode_log=str(log))
        rows=parse(text,m,'STATS'); sr=parse(text,m,'SEARCH')
        detailed.extend({**meta,**r} for r in rows); searches.extend({**meta,**r} for r in sr)
        status.append({**meta,'stats_present':bool(rows),'search_present':bool(sr)})
        if rows:
            total=Counter()
            for r in rows:
                for k,v in r.items():
                    if k not in dimensions: total[k]+=v
            byjob.append({**meta,**dict(total),'remap_fraction_regular':total['remap_vs_r8_12']/total['regular_count'] if total['regular_count'] else None})
    args.out.mkdir(parents=True,exist_ok=True)
    write(args.out/'final_by_stratum.csv',detailed); write(args.out/'final_by_job.csv',byjob)
    write(args.out/'search_by_stratum.csv',searches); write(args.out/'log_status.csv',status)
    audit=dict(jobs=len(jobs),final_rows=len(detailed),search_rows=len(searches),
      input_log_bytes=sum(log.stat().st_size for log in jobs),bdrate_measured=False,
      caveats=['Final TS selection bias remains','Fractional target delta is a fixed-state local proxy',
               'owner=-1 final edit survival; owner>=0 search trials; never merge their denominators',
               'Absent statistics means no TS or stats disabled, not zero measured activity'])
    (args.out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n'); print(json.dumps(audit,indent=2))

if __name__=='__main__': main()
