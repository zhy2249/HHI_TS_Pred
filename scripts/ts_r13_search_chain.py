#!/usr/bin/env python3
"""Extract the validated Johnny32 POC16/CTU36 SBT-gate diagnostic chain.

This is a named case study, not an adaptive algorithm or BD-rate calculator.
The 1.07 predicate is reconstructed from recorded inputs and source, not an
independent intervention or a direct predicate log in this observer revision.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from ts_r13_search_analysis import parse, locator, payload

PARENT = '/768_384_128_128_0_0#1/832_384_64_64_0_1#1/832_384_32_32_0_2#1'
TARGET = PARENT + '/848_384_16_32_0_3#1/856_384_8_32_0_4#1'


def one(rows, description):
    if len(rows)!=1:
        raise ValueError(f'{description}: expected one observation, found {len(rows)}')
    return rows[0]


def case(rows):
    if {(r['poc'],r['ctu']) for r in rows}!={(16,36)}:
        raise ValueError('This case study requires POC16/CTU36 only')
    node=[r for r in rows if r['node_path']==TARGET]
    start=one([r for r in node if r['event']=='sbt_read' and r['sse_key']==58], 'target key58 lookup')
    next_read=next(r for r in node if r['event']=='sbt_read' and r['seq']>start['seq'])
    episode=[r for r in node if start['seq']<=r['seq']<next_read['seq']]
    entry=one([r for r in episode if r['event']=='transform_entry' and
               r.get('component')==0 and r.get('tr')==4], 'target TS entry')
    trial=one([r for r in episode if r['event']=='transform_trial' and
               r.get('component')==0 and r.get('tr')==4], 'target TS trial')
    sbt_off=one([r for r in episode if r['event']=='mode_result' and r['sbt']==0], 'SBT-off result')
    previous_best=[r for r in node if r['seq']<start['seq'] and r['event']=='mode_result' and r['accepted']][-1]
    previous_write=[r for r in node if r['seq']<start['seq'] and r['event']=='sbt_write' and r['best_changed']][-1]
    if previous_write['local_best_cost']!=previous_best['cost'] or previous_best['sbt']==0:
        raise ValueError('Saved-cost reconstruction prerequisites differ from diagnosed case')
    threshold=previous_best['cost']*(1.07*(previous_write['sbt_off_cost']/previous_write['local_best_cost']))
    selected=one([r for r in node if r['event']=='cu_selected'],'completed child search')
    sbt_results=[r for r in episode if r['event']=='mode_result' and r['sbt']!=0]
    parent_rows=[r for r in rows if r['node_path']==PARENT]
    parent_modes=[r for r in parent_rows if r['event']=='mode_result' and r['mode'] in (5,6,7,8,9)]
    parent_selected=one([r for r in parent_rows if r['event']=='cu_selected'],'completed parent search')
    parent_winner=[r for r in parent_modes if r['accepted']][-1]
    if parent_winner['cost']!=parent_selected['cost']:
        raise ValueError('Last accepted parent split does not match parent selected cost')
    events=[('previous_best',previous_best),('saved_cost_update',previous_write),
            ('key58_lookup',start),('key58_ts_entry',entry),('key58_ts_trial',trial),
            ('key58_sbt_off_result',sbt_off)]
    events += [('key58_sbt_result',r) for r in sbt_results]
    events += [('child_selected',selected)]
    events += [('parent_split_result',r) for r in parent_modes]
    events += [('parent_selected',parent_selected)]
    values={
        'target_node_path':TARGET,'sse_key':58,
        'previous_best_cost':previous_best['cost'],'previous_best_sbt':previous_best['sbt'],
        'saved_off_cost':previous_write['sbt_off_cost'],
        'saved_best_cost':previous_write['local_best_cost'],
        'threshold_formula':'bestCost * (1.07 * (savedOffCost / savedBestCost))',
        'derived_threshold':threshold,'current_sbt_off_cost':sbt_off['cost'],
        'derived_gate_skips':sbt_off['cost']>threshold,
        'observed_key58_sbt_candidates':[r['sbt'] for r in sbt_results],
        'ts_fractional_bits':trial['frac_bits'],'ts_dist':trial['dist'],
        'ts_q_hash':trial['q_hash'],'ts_abs_sum':trial['abs_sum'],
        'child_selected_cost':selected['cost'],'child_selected_dist':selected['dist'],
        'child_selected_frac_bits':selected['frac_bits'],'child_reco_y_hash':selected['reco_y_hash'],
        'parent_winner_mode':parent_winner['mode'],
        'parent_winner_cost':parent_winner['cost'],
        'parent_winner_db_offset':parent_winner['db_offset'],
        'parent_winner_comparison_cost':parent_winner['cost']+parent_winner['db_offset'],
        'parent_selected_cu_count':parent_selected['cu_count'],
    }
    return values,events,entry


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference',type=Path,required=True)
    ap.add_argument('--test',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    args=ap.parse_args()
    refs= parse(args.reference),parse(args.test)
    cases=[case(r) for r in refs]
    entry_changes={k:[payload(cases[0][2]).get(k),payload(cases[1][2]).get(k)]
                   for k in payload(cases[0][2]).keys()|payload(cases[1][2]).keys()
                   if payload(cases[0][2]).get(k)!=payload(cases[1][2]).get(k)}
    if entry_changes:
        raise ValueError(f'Target TS logged entry differs: {entry_changes}')
    a,b=cases[0][0],cases[1][0]
    for k in ('ts_dist','ts_q_hash','ts_abs_sum','derived_threshold'):
        if a[k]!=b[k]: raise ValueError(f'Diagnosed same-entry mechanism changed: {k}')
    if a['derived_gate_skips'] or not b['derived_gate_skips']:
        raise ValueError('Diagnosed crossing of the SBT cost gate was not reproduced')
    rows=[]
    for name,case_data in zip(('EQ','SP'),cases):
        for role,r in case_data[1]:
            rows.append(dict(trajectory=name,role=role,**locator(r),
                fields=json.dumps(payload(r),sort_keys=True,separators=(',',':'))))
    out={
        'schema':1,'case':'Johnny32, POC16, CTU36; EQ versus SP',
        'raw_sources':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in (args.reference,args.test)],
        'trace_status':'Complete strict JSON; no formatter recovery or truncation permission',
        'recorded_input_equality':True,
        'recorded_input_scope':'Transform entry residual/prediction/CABAC-accessor hashes, QP, lambda and mode ancestry; not all encoder private caches',
        'predicate_status':'Reconstructed from logged inputs plus EncCu::xEncodeInterResidual source; predicate was not directly instrumented and no control intervention was run',
        'EQ':a,'SP':b,
        'difference':{
            'ts_fractional_bits':b['ts_fractional_bits']-a['ts_fractional_bits'],
            'ts_estimated_bits':(b['ts_fractional_bits']-a['ts_fractional_bits'])/32768,
            'sbt_off_cost':b['current_sbt_off_cost']-a['current_sbt_off_cost'],
            'child_selected_cost':b['child_selected_cost']-a['child_selected_cost'],
            'child_selected_dist':b['child_selected_dist']-a['child_selected_dist'],
            'child_selected_frac_bits':b['child_selected_frac_bits']-a['child_selected_frac_bits'],
        },
        'source_contract':{
            'gate':'EncCu::xEncodeInterResidual: bestCost captures bestCS->cost at entry; th=1.07, multiplied by m_sbtCostSave[0]/[1] when prevBestSbt!=0; skip when sbtOffCost > bestCost*th',
            'saved_costs':'At end of residual search, m_sbtCostSave stores sbtOffCost/currBestCost only if bestCostBegin != bestCS->cost',
            'db_offset':'The SBT gate uses raw bestCS->cost, without costDbOffset. Parent split comparison uses cost+costDbOffset when enc_db_opt=1',
            'cache':'SaveLoadEncInfoSbt is keyed by CTU-relative x/y, width/height and quantized SSE; capacity10, no overwrite when full. This local key58 gate chain does not require the earlier key92/cache-capacity chain to explain it',
        },
        'interpretation_limits':[
            'A completed child search node is not necessarily in the final CU tree; SP rejects this BT parent in favor of QT.',
            'The first observed numerical/control difference occurs earlier; it is not asserted to be the cause of this later local gate crossing.',
            'This establishes an observed selected-search difference with source-reconstructed gate inputs, not a completed gate-disable causal intervention.',
            'Short 17-frame prefixes and local RD costs do not explain the full 300-frame BD-rate loss.',
        ],
        'recommended_single_control':{
            'status':'planned, not implemented or executed',
            'scope':{'poc':16,'ctu':36,'node_path':TARGET,'mode':1,'opts':0,'residual_pass':0,'sse_key':58},
            'change':'Bypass only the sbtOffCost > bestCost*th pruning gate for this one candidate in both EQ and SP; keep all other tools/caches unchanged.',
            'required_checks':'Record exact eligible/applied counts and predicate operands; decode both; check no earlier output divergence; inspect whether the candidate and parent-tree difference disappears, persists or migrates.',
        },
    }
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'selected_search_chain.json').write_text(json.dumps(out,indent=2)+'\n')
    with (args.output_dir/'selected_search_chain.csv').open('w',newline='') as h:
        writer=csv.DictWriter(h,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(out['difference'],indent=2))


if __name__=='__main__':main()
