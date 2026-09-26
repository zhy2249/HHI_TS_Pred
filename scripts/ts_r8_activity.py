#!/usr/bin/env python3
"""Extract final-Writer R8 activity; no counterfactual gain or BD-rate claims.

Only completed/pass jobs from summary.csv are included. Overlapping root/group
summaries are deduplicated by absolute encode-log path. Zero TS is not failure.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
from ts_predictor_naming import R8_MODE_NUMBERS


def parse_log(text, mode):
    header = None; rows = []
    for line in text.splitlines():
        if line.startswith('TS_R8_STATS_HEADER '):
            if header is not None: raise ValueError('Multiple stats sections in one log')
            header = line.split(' ',1)[1].split(',')
        elif line.startswith('TS_R8_STATS '):
            values = list(map(int,line.split(' ',1)[1].split(',')))
            if header is None or len(values)!=len(header): raise ValueError('Malformed R8 stats row')
            r = dict(zip(header,values))
            if r['mode']!=mode: raise ValueError('R8 mode differs from summary')
            if r['support']==-1:
                if r['cutoff']!=-1 or r['active_count']!=0: raise ValueError('Invalid census')
            else:
                if r['tu_count'] or r['cg_count']: raise ValueError('Coefficient bins duplicate census')
                if r['cutoff'] not in (0,2,10): raise ValueError('Invalid coding path')
                if r['active_count']!=r['p_current']+r['p_identity']+r['p_other']: raise ValueError('Decision census mismatch')
                if r['cutoff']==0 and r['remap_vs_parent']: raise ValueError('Bypass does not remap')
            rows.append(r)
    return rows


def write_csv(path, rows):
    if not rows: return
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def parse_search_log(text, mode):
    """Separate owner-search population; NEVER add it to final-TU counts."""
    header=None; rows=[]
    for line in text.splitlines():
        if line.startswith('TS_R8_SEARCH_HEADER '):
            if header is not None: raise ValueError('Multiple search sections')
            header=line.split(' ',1)[1].split(',')
        elif line.startswith('TS_R8_SEARCH '):
            values=line.split(' ',1)[1].split(',')
            if header is None or len(header)!=len(values): raise ValueError('Malformed search row')
            r={k:float(v) if k in ('j0_sum','j1_sum','local_gain_sum') else int(v) for k,v in zip(header,values)}
            if r['mode']!=mode or mode not in (23,24): raise ValueError('Wrong paired-search mode')
            if not 0 <= r['chosen_q1'] <= r['pairs'] or r['local_gain_sum'] < 0: raise ValueError('Invalid local minimum')
            if not 0 <= r['q_changed'] <= r['pairs']: raise ValueError('Invalid q-change count')
            rows.append(r)
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run_root',type=Path)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(); jobs={}; excluded=Counter()
    for source in args.run_root.rglob('summary.csv'):
        with source.open(newline='') as f:
            for row in csv.DictReader(f):
                if row.get('fixed_predictor') not in R8_MODE_NUMBERS: continue
                if row.get('error_info')!='pass': excluded['failed_or_incomplete_summary_rows']+=1;continue
                log=Path(row['encode_log'])
                # Preserve same-server paths. Moved datasets must correct metadata,
                # not guess among similarly named logs from different runs.
                if not log.is_file(): raise FileNotFoundError(log)
                jobs[log.resolve()]=row
    detailed=[]; summaries=[]; status=[]; searches=[]; search_jobs=[]
    for log,job in sorted(jobs.items()):
        mode=R8_MODE_NUMBERS[job['fixed_predictor']]
        text=log.read_text(errors='replace')
        if not re.search(r'TS R8 revision=R8-DESIGN-20260925-v2; mode='+str(mode)+r';',text):
            raise ValueError(f'Missing/mismatched revision: {log}')
        rows=parse_log(text,mode); total=Counter()
        meta=dict(job=job['name'],sequence=job['sequence'],qp=job['qp'],runtime=job['fixed_predictor'],encode_log=str(log))
        sr=parse_search_log(text,mode)
        searches.extend({**meta,**r} for r in sr)
        if sr:
            fields=('pairs','extra_up_candidates','q_changed','chosen_q1','ties','both_valid','j0_sum','j1_sum','local_gain_sum')
            search_jobs.append({**meta,**{k:sum(r[k] for r in sr) for k in fields}})
        census=('tu_count','cg_count','empty_cg','coeff_count','nonzero_count')
        dimensions=('mode','component','width','height','cu_qp','intra','bdpcm','cg_count_in_tu','cg_index','support','cutoff')
        for r in rows:
            detailed.append({**meta,**r})
            for k,v in r.items():
                if k in dimensions: continue
                if (k in census)==(r['support']==-1): total[k]+=v
        # Absence may mean no TS or statistics disabled: never fabricate zero activity.
        status.append({**meta,'stats_present':bool(rows),'interpretation':'final_TS_activity_only' if rows else 'no_TS_or_stats_disabled'})
        if rows:
            summaries.append({**meta,**dict(total),
                'remap_vs_parent_ratio':total['remap_vs_parent']/total['active_count'] if total['active_count'] else None})
    args.out.mkdir(parents=True,exist_ok=True)
    write_csv(args.out/'by_stratum.csv',detailed)
    write_csv(args.out/'by_job.csv',summaries)
    write_csv(args.out/'log_status.csv',status)
    write_csv(args.out/'search_by_stratum.csv',searches)
    write_csv(args.out/'search_by_job.csv',search_jobs)
    result=dict(jobs=len(jobs),strata=len(detailed),with_stats=len(summaries),excluded=dict(excluded),
                paired_search_jobs=len(search_jobs),
                caveat='Final-TS selection bias; scores are not actual rate savings. Separate C03/C04 search q_changed is NOT final-TS q change. DeltaR/DeltaD and final survival are not measured.')
    (args.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
