#!/usr/bin/env python3
"""Validate and extract final-Writer R12 observations; never infer BD-rate."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from ts_predictor_naming import R12_MODE_NUMBERS
from ts_r9_activity import write

POLICIES={**{name:85+n for name,n in R12_MODE_NUMBERS.items()},'r10_integer_then_fractional':73}
DIMENSIONS='trajectory_policy mode component width height cu_qp intra bdpcm cutoff n'.split()

def parse(text, policy):
    header=None; rows=[]
    for line in text.splitlines():
        if line.startswith('TS_R12_STATS_HEADER '):
            if header is not None: raise ValueError('Duplicate R12 section')
            header=line.split(' ',1)[1].split(',')
            if header[:10]!=DIMENSIONS or len(header)!=len(set(header)): raise ValueError('Invalid R12 columns')
        elif line.startswith('TS_R12_STATS '):
            values=line.split(' ',1)[1].split(',')
            if header is None or len(header)!=len(values): raise ValueError('Malformed R12 statistics')
            r=dict(zip(header,map(int,values))); m=r['mode']; regular=r['regular_count']
            if r['trajectory_policy']!=policy or not 0<=m<=12 or r['cutoff'] not in (-1,0,2,10):
                raise ValueError('Wrong R12 identity/path')
            if not 0<=r['remap_vs_r10_3']<=r['action_vs_r10_3']<=regular<=r['coeff_count']:
                raise ValueError('Invalid activity denominator')
            if not 0<=r['remap_vs_r10_3']<=r['nonzero_count']<=r['coeff_count']:
                raise ValueError('Invalid nonzero population')
            if regular and (r['bdpcm'] or r['cutoff'] not in (2,10) or not 0<=r['n']<=5):
                raise ValueError('Nonregular predictor observation')
            if sum(r['selected_'+e] for e in 'ABCD')!=regular or (m!=3 and r['selected_D']):
                raise ValueError('Invalid expert counts')
            if r['ci_unique']+r['ci_tie']!=regular or r['gap_Q']+r['gap_gt_Q']!=r['ci_unique']:
                raise ValueError('Invalid CI partition')
            if sum(r['slot_'+s] for s in ('L','U','D','LL','UU'))!=r['validation_sum']:
                raise ValueError('Lost spatial slot')
            if not 0<=r['effective_sum']<=r['validation_sum']<=5*regular:
                raise ValueError('Invalid evidence population')
            if not 0<=r['inner_full_accept']<=r['inner_soft_accept']<=r['inner_raw_accept']<=r['inner_count']:
                raise ValueError('Non-nested weighted guard')
            for key,value in r.items():
                if key not in DIMENSIONS and not key.startswith('delta_') and value<0:
                    raise ValueError('Negative count/loss: '+key)
            rows.append(r)
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path); p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(); jobs={}
    for summary in args.root.rglob('summary.csv'):
        with summary.open(newline='') as f:
            for r in csv.DictReader(f):
                if r.get('fixed_predictor') in POLICIES and r.get('error_info')=='pass':
                    jobs[Path(r['encode_log']).resolve()]=r
    detail=[]; totals=[]; status=[]
    for log,j in sorted(jobs.items()):
        content=log.read_text(errors='replace'); runtime=j['fixed_predictor']; policy=POLICIES[runtime]
        if f'EXPERIMENT: TS_FIXED_PREDICTOR={runtime};' not in content: raise ValueError(f'Wrong executable: {log}')
        if runtime in R12_MODE_NUMBERS and f'TS R12 revision=R12-POS-01; mode={R12_MODE_NUMBERS[runtime]};' not in content:
            raise ValueError(f'Wrong R12 revision: {log}')
        rows=parse(content,policy)
        meta=dict(job=j['name'],sequence=j['sequence'],qp=j['qp'],trajectory=runtime,encode_log=str(log))
        detail.extend({**meta,**r} for r in rows); status.append({**meta,'stats_present':bool(rows)})
        for mode in sorted({r['mode'] for r in rows}):
            total=Counter()
            for r in rows:
                if r['mode']==mode: total.update({k:v for k,v in r.items() if k not in DIMENSIONS})
            totals.append({**meta,'mode':mode,**dict(total)})
    args.out.mkdir(parents=True,exist_ok=True)
    write(args.out/'final_by_stratum.csv',detail); write(args.out/'final_by_job_mode.csv',totals)
    write(args.out/'log_status.csv',status)
    audit=dict(jobs=len(jobs),rows=len(detail),input_log_bytes=sum(x.stat().st_size for x in jobs),bdrate_measured=False,
        warnings=['Do not sum duplicate TS populations across shadow modes or quantization trajectories',
                  'Q15 target loss uses frozen probabilities; actual-path cutoff is observation only',
                  'D is measured only in mode 3; zero D fields elsewhere are absent, not zero loss',
                  'Final-TS selection bias remains; shadow is not new closed-loop coding',
                  'Missing stats means disabled observations or no TS, not measured zero activity'])
    (args.out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n'); print(json.dumps(audit,indent=2))

if __name__=='__main__': main()
