#!/usr/bin/env python3
"""Final-Writer R11 shadow observations on separately labelled quantization trajectories."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from ts_predictor_naming import R11_MODE_NUMBERS
from ts_r9_activity import write

POLICIES={**{name:77+n for name,n in R11_MODE_NUMBERS.items()},
          'r3_risk_guard':13,'r9_expert_integer':66,'r10_integer_then_fractional':73}
DIMENSIONS=('trajectory_policy mode component width height cu_qp intra bdpcm cg_count cg_index n n1 d cutoff '
            'v0_size v3_size v4_size validation_size effective_samples distinct_actions selected_expert '
            'best_target_ci best_target_cf best_target_path').split()

def parse(text, policy):
    header=None; rows=[]
    for line in text.splitlines():
        if line.startswith('TS_R11_STATS_HEADER '):
            if header is not None: raise ValueError('Duplicate R11 statistics section')
            header=line.split(' ',1)[1].split(',')
        elif line.startswith('TS_R11_STATS '):
            values=line.split(' ',1)[1].split(',')
            if header is None or len(header)!=len(values): raise ValueError('Malformed R11 statistics')
            r=dict(zip(header,map(int,values))); m=r['mode']; regular=r['regular_count']
            if r['trajectory_policy']!=policy or not 1<=m<=8 or r['cutoff'] not in (-1,0,2,10):
                raise ValueError('Wrong R11 identity/path')
            if not 0<=r['remap_vs_r10_3']<=r['regular_nonzero']<=regular:
                raise ValueError('Invalid remapping denominator')
            if regular:
                if r['bdpcm'] or r['cutoff'] not in (2,10): raise ValueError('Nonregular predictor observation')
                if not 0<=r['v0_size']<=5 or not r['v0_size']<=r['v3_size']<=r['v4_size']<=8:
                    raise ValueError('Invalid nested validation geometry')
                size=r['v4_size'] if m in (4,8) else r['v3_size'] if m==3 else r['v0_size']
                if r['validation_size']!=size or not 0<=r['effective_samples']<=size:
                    raise ValueError('Invalid effective evidence')
                if not 0<=r['selected_expert']<(4 if m in (5,6) else 3): raise ValueError('Invalid expert')
            if any(v<0 for k,v in r.items() if k not in DIMENSIONS): raise ValueError('Negative count/loss')
            rows.append(r)
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('root',type=Path); p.add_argument('--out',type=Path,required=True)
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
        if runtime in R11_MODE_NUMBERS and f'TS R11 revision=R11-20260929-v1; mode={R11_MODE_NUMBERS[runtime]};' not in content:
            raise ValueError(f'Wrong R11 revision: {log}')
        rows=parse(content,policy)
        meta=dict(job=j['name'],sequence=j['sequence'],qp=j['qp'],trajectory=runtime,encode_log=str(log))
        detail.extend({**meta,**r} for r in rows); status.append({**meta,'stats_present':bool(rows)})
        for mode in sorted({r['mode'] for r in rows}):
            total=Counter()
            for r in rows:
                if r['mode']==mode: total.update({k:v for k,v in r.items() if k not in DIMENSIONS})
            totals.append({**meta,'mode':mode,**dict(total)})
    args.out.mkdir(parents=True,exist_ok=True)
    write(args.out/'final_by_stratum.csv',detail); write(args.out/'final_by_job_mode.csv',totals); write(args.out/'log_status.csv',status)
    audit=dict(jobs=len(jobs),rows=len(detail),input_log_bytes=sum(x.stat().st_size for x in jobs),bdrate_measured=False,
               warnings=['Each final TS population is observed eight times: do not sum populations across modes',
                         'Keep source trajectory separate; not new closed-loop results on all eight modes',
                         'All costs Q15; actual-path CF is frozen-context with actual cutoff, not full CABAC counterfactual',
                         'D is absent in modes other than 5/6; zero D fields are not measured zero loss',
                         'Missing observations mean disabled stats or no TS, not zero activity'])
    (args.out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n'); print(json.dumps(audit,indent=2))

if __name__=='__main__': main()
