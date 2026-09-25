#!/usr/bin/env python3
"""Read final-Writer shadow and separately labelled encoder-search probes.

No BD-rate is inferred from short tests or fixed-q CG simulations. Input is the
existing batch_test.py summary.csv (completed, hash-checked old-R3 tasks).
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from collections import defaultdict


def parse_table(text, prefix):
    headers = re.findall(r'^'+prefix+r'_HEADER (.+)$', text, re.M)
    lines = re.findall(r'^'+prefix+r' (.+)$', text, re.M)
    if not headers and not lines:
        return [], []
    if len(headers)!=1:
        raise ValueError(f'{prefix}: missing/duplicate schema')
    fields=headers[0].strip().split(',')
    if len(fields)!=len(set(fields)):
        raise ValueError(f'{prefix}: duplicate column')
    rows=[]
    for line in lines:
        values=line.strip().split(',')
        if len(values)!=len(fields):
            raise ValueError(f'{prefix}: truncated row')
        rows.append(dict(zip(fields,map(int,values))))
    return fields,rows


def div(a,b):
    return a/b if b else None


def metrics(v):
    def pct(a,b='eligible'): return div(100*v[a],v[b])
    return dict(eligible=v['eligible'],winner_disagree_pct=pct('winner_disagree'),
        selected_disagree_pct=pct('selected_disagree'),raw_remap_diff_pct=pct('raw_remap_diff'),
        guard_remap_diff_pct=pct('guard_remap_diff'),current_tie_positions=v['current_tie'],
        ties_broken_pct=pct('current_tie_broken','current_tie'),new_winner_from_tie=v['new_winner_from_current_tie'],
        old_accept_new_reject=v['old_accept_new_reject'],old_reject_new_accept=v['old_reject_new_accept'],
        r6_region=v['r6_region'],
        **{k:v[k] for k in ('r6_old_raw_identity','r6_old_raw_nonzero','r6_new_current','r6_new_identity',
                           'r6_new_old_winner','r6_new_other')},
        cost_pairs=v['cost_pairs'],old_delta_mae_bits=div(v['old_delta_abs_error_q15'],32768*v['cost_pairs']),
        new_delta_mae_bits=div(v['new_delta_abs_error_q15'],32768*v['cost_pairs']),
        old_cost_inversion_pct=pct('old_cost_inversion','cost_pairs'),
        new_cost_inversion_pct=pct('new_cost_inversion','cost_pairs'),
        old_cost_tie_real_diff=v['old_cost_tie_real_diff'],new_cost_tie_real_diff=v['new_cost_tie_real_diff'],
        isolated_raw_delta_bits=v['raw_real_delta_q15']/32768,
        isolated_guard_delta_bits=v['guard_real_delta_q15']/32768,
        path_oracle_delta_mae_bits=div(v.get('path_oracle_delta_abs_error_q15',0),32768*v['cost_pairs']) if 'path_oracle_delta_abs_error_q15' in v else None,
        path_oracle_inversion_pct=div(100*v.get('path_oracle_cost_inversion',0),v['cost_pairs']) if 'path_oracle_cost_inversion' in v else None,
        new_identity_guard_rejected=v.get('new_identity_guard_rejected'),
        identity_reject_override_delta_bits=v['identity_reject_override_delta_q15']/32768 if 'identity_reject_override_delta_q15' in v else None)


def write(path, rows):
    if not rows:return
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def compare_streams(jobs, reference_summary):
    """Validate observational bit-exactness against retained old-R3 tasks."""
    with reference_summary.open() as f:
        reference=list(csv.DictReader(f))
    key=lambda r:(r['sequence'],int(r['qp']),int(r['frames']))
    index={key(r):r for r in reference}
    if len(index)!=len(reference):raise ValueError('Duplicate reference task key')
    checked=[]
    for job in jobs:
        ref=index.get(key(job))
        if not ref or ref.get('error_info')!='pass' or ref.get('fixed_predictor')!='r3_risk_guard':
            raise ValueError(f'Missing successful old-R3 reference: {key(job)}')
        a,b=Path(job['bitstream']),Path(ref['bitstream'])
        ha,hb=(hashlib.sha256(p.read_bytes()).hexdigest() for p in (a,b))
        if ha!=hb:raise ValueError(f'Shadow changed bitstream: {key(job)}')
        checked.append(dict(sequence=job['sequence'],qp=int(job['qp']),frames=int(job['frames']),
                            shadow=str(a),reference=str(b),sha256=ha))
    return checked


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('summary',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--reference-summary',type=Path,help='Matching retained old-R3 tasks for SHA256 bit-exact check')
    args=p.parse_args()
    with args.summary.open() as f: jobs=list(csv.DictReader(f))
    if not jobs:raise ValueError('Empty batch summary')
    data,cgs,rdq,sources=[],[],[],[]
    for job in jobs:
        if job.get('error_info')!='pass':raise ValueError(f'Incomplete task: {job.get("name")}')
        if job.get('fixed_predictor')!='r3_risk_guard':raise ValueError('Only unchanged R3 shadow tasks accepted')
        path=Path(job['encode_log']);text=path.read_text(errors='strict')
        if 'TS RATE shadow=RATE-20260924-v1; actual-decisions=R3-old;' not in text:
            raise ValueError(f'No shadow identity: {path}')
        decode=Path(job['decode_log']).read_text(errors='strict')
        if job.get('decode_status')!='ok' or 'MD5' not in decode:
            raise ValueError(f'Decoder verification missing: {job.get("name")}')
        meta=dict(sequence=job['sequence'],input_qp=int(job['qp']),frames=int(job['frames']))
        for prefix,target in [('TS_RATE_SHADOW',data),('TS_RATE_CG',cgs),('TS_RATE_RDOQ',rdq)]:
            _,rows=parse_table(text,prefix);target.extend({**meta,**r} for r in rows)
        sources.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),**meta))
    if not data:raise ValueError('No final-Writer TS shadow coverage; do not launch full CTC')
    dims=['overall','sequence','input_qp','cu_qp','component','support','cutoff','size','old_raw_kind','new_raw_kind','old_guard_kind','new_guard_kind']
    counters=[k for k in data[0] if k not in {'sequence','input_qp','frames','component','width','height','cu_qp','support','cutoff',
                                           'old_raw_kind','new_raw_kind','old_guard_kind','new_guard_kind'}]
    aggregates={}
    for dim in dims:
        groups=defaultdict(lambda:defaultdict(int))
        for r in data:
            label='all' if dim=='overall' else f"{r['width']}x{r['height']}" if dim=='size' else str(r[dim])
            for k in counters:groups[label][k]+=r[k]
        for label,values in groups.items():aggregates[dim,label]=dict(values)
    summary=[dict(dimension=d,value=v,**metrics(s)) for (d,v),s in aggregates.items()]
    cgout=[]
    for dim in ('overall','sequence','input_qp','component'):
        groups=defaultdict(lambda:defaultdict(int))
        for r in cgs:
            label='all' if dim=='overall' else str(r[dim])
            for k in ('cgs','old_rate_q15','new_raw_rate_q15','new_guard_rate_q15'):groups[label][k]+=r[k]
            if 'old_raw_rate_q15' in r:groups[label]['old_raw_rate_q15']+=r['old_raw_rate_q15']
        for label,r in groups.items():
            cgout.append(dict(dimension=dim,value=label,**r,
                raw_conditional_gain_pct=div(100*(r['old_rate_q15']-r['new_raw_rate_q15']),r['old_rate_q15']),
                guard_conditional_gain_pct=div(100*(r['old_rate_q15']-r['new_guard_rate_q15']),r['old_rate_q15']),
                raw_vs_old_raw_gain_pct=div(100*(r['old_raw_rate_q15']-r['new_raw_rate_q15']),r['old_raw_rate_q15']) if 'old_raw_rate_q15' in r else None))
    args.out.mkdir(parents=True,exist_ok=True)
    for name,rows in [('final_writer_counts',data),('summary',summary),('conditional_cg',cgs),('conditional_cg_summary',cgout),('rdoq_search_probes',rdq)]:
        write(args.out/(name+'.csv'),rows)
    bit_exact=compare_streams(jobs,args.reference_summary) if args.reference_summary else []
    audit=dict(sources=sources,reference_bit_exact=bit_exact,raw_counts={f'{d}:{v}':s for (d,v),s in aggregates.items()},
        denominator='eligible = final nonzero, regular-remapped, support>=3, non-BDPCM positions',
        kind='0 Current (including identity-equivalent Current), 1 NoPred, 2 other magnitude',
        limitations=['CG simulation holds anchor q and anchor CG-entry contexts; not BD-rate',
                     'Cost fidelity uses true target only for evaluation, never predictor selection',
                     'Isolated coefficient CG deltas overlap; cannot sum as whole-bitstream saving',
                     'RDOQ probes are encoder search trials before all-zero-CG/final-mode decisions',
                     'Short predetermined content is not full CTC'])
    (args.out/'audit.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(next(r for r in summary if r['dimension']=='overall'),indent=2))
    print(json.dumps(next(r for r in cgout if r['dimension']=='overall'),indent=2))
    if rdq:
        print('RDOQ SEARCH (not final decisions):', {k:sum(r[k] for r in rdq) for k in
              ('trial_positions','regular_positions','predictor_diff','candidate_set_diff','provisional_level_diff')})


if __name__=='__main__':main()
