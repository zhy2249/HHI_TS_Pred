#!/usr/bin/env python3
"""Derived comparisons of a COMPLETE frozen-rule report. No codec invocation.

Positive gain means fewer conditional TSRC estimated bits. Not BD-rate.
The primary mean follows source -> QP within content -> content balancing.
"""
import argparse, csv, json
from collections import defaultdict
from pathlib import Path
import ts_corpus as P


def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))


def value(s):return None if s in ('',None) else float(s)
def avg(xs):
    xs=[x for x in xs if x is not None]
    return sum(xs)/len(xs) if xs else None


def summarize(report,output):
    scope=P.readj(report/'report_scope.json')
    if not scope['native_whole_TU'] or not scope['fixed_q_only']:raise ValueError('Whole-TU report required')
    methods=P.readj(report/'methods.json')['methods'];rows=read(report/'all_methods_by_stream_component.csv')
    seqrows=read(report/'by_sequence.csv');pairs=read(report/'paired_source_metrics.csv')
    seq={(r['sequence'],r['method']):value(r['balanced_gain_bits_per_nonzero']) for r in seqrows}
    sequences=sorted({s for s,m in seq});lookup={(r['sequence'],r['qp'],r['method']):value(r['balanced_gain_bits_per_nonzero']) for r in pairs}
    summary=[];qps=[];components=[];signatures=defaultdict(list)
    indexed={(r['sequence'],r['qp'],r['origin'],r['component'],r['method']):r for r in rows}
    for cfg in methods:
        m=cfg['id'];record=dict(method=m,family=cfg['family'])
        selected=[r for r in rows if r['method']==m and r['component']=='all']
        for base,name in [('CURRENT','current'),('KEEP_F4','eq'),('KEEP_F2','sp')]:
            delta=[seq[s,m]-seq[s,base] for s in sequences if seq[s,m] is not None and seq[s,base] is not None]
            record[name+'_balanced_gain_bits_per_nonzero']=avg(delta)
            record[name+'_supported_sequences']=len(delta)
            record[name+'_better_sequences']=sum(v>0 for v in delta)
            record[name+'_worse_sequences']=sum(v<0 for v in delta)
            record[name+'_worst_sequence_gain']=min(delta) if delta else None
            record[name+'_summed_gain_bits']=sum(float(r['gain_vs_'+name+'_bits']) for r in selected)
            record[name+'_costlier_tu']=sum(int(r['costlier_tu_vs_'+name]) for r in selected)
            record[name+'_gross_positive_loss_bits']=sum(float(r['positive_loss_vs_'+name+'_bits']) for r in selected)
            record[name+'_max_tu_loss_bits']=max(float(r['max_tu_loss_vs_'+name+'_bits']) for r in selected)
        for origin in ('R13-1','R13-2'):
            content=[]
            for s in sequences:
                content.append(avg([value(r['gain_bits_per_nonzero']) for r in selected if r['sequence']==s and r['origin']==origin]))
            record[origin+'_current_gain_bits_per_nonzero']=avg(content)
        summary.append(record)
        signatures[tuple(int(r['rate_frac']) for r in sorted(selected,key=lambda r:(r['sequence'],r['qp'],r['origin'])))].append(m)
        for q in ('22','27','32','37'):
            item=dict(qp=q,method=m)
            for base,name in [('CURRENT','current'),('KEEP_F4','eq'),('KEEP_F2','sp')]:
                values=[lookup[s,q,m]-lookup[s,q,base] for s in sequences if lookup[s,q,m] is not None and lookup[s,q,base] is not None]
                item[name+'_gain_bits_per_nonzero']=avg(values);item[name+'_supported_sequences']=len(values)
            qps.append(item)
        for c in ('0','1','2','all'):
            vals=[];cells=0
            for s in sequences:
                content=[]
                for q in ('22','27','32','37'):
                    source=[value(indexed[s,q,o,c,m]['gain_bits_per_nonzero']) for o in ('R13-1','R13-2')]
                    if None not in source:content.append(sum(source)/2);cells+=1
                if content:vals.append(sum(content)/len(content))
            components.append(dict(component=c,method=m,balanced_gain_bits_per_nonzero=avg(vals),supported_sequences=len(vals),supported_content_qp_cells=cells))
    ranking=read(report/'all_content_descriptive_ranking.csv')
    for r in ranking:
        found=next(x for x in summary if x['method']==r['method'])['current_balanced_gain_bits_per_nonzero']
        expected=value(r['descriptive_mean_gain_bits_per_nonzero'])
        assert (found is None and expected is None) or abs(found-expected)<1e-12
    def best(items):
        eligible=[r for r in items if r['current_balanced_gain_bits_per_nonzero'] is not None]
        return max(eligible,key=lambda r:r['current_balanced_gain_bits_per_nonzero']) if eligible else None
    folds=read(report/'leave_one_content_selection.csv');fold_metrics={}
    for base,name in [('CURRENT','current'),('KEEP_F4','eq'),('KEEP_F2','sp')]:
        delta=[float(f['held_out_gain_bits_per_nonzero'])-seq[f['held_out_sequence'],base] for f in folds if seq[f['held_out_sequence'],base] is not None]
        fold_metrics[name]=dict(mean_gain_bits_per_nonzero=avg(delta),better_contents=sum(x>0 for x in delta),worse_contents=sum(x<0 for x in delta),supported_contents=len(delta))
    state_increments=[]
    for cfg in methods:
        if cfg['family']!='state':continue
        m=cfg['id'];base='KEEP_F'+str(4*cfg['initial']//cfg['k'])
        delta=[seq[s,m]-seq[s,base] for s in sequences if seq[s,m] is not None and seq[s,base] is not None]
        selected=[r for r in rows if r['method']==m and r['component']=='all']
        raw=sum((int(indexed[r['sequence'],r['qp'],r['origin'],'all',base]['rate_frac'])-int(r['rate_frac']))/32768 for r in selected)
        state_increments.append(dict(method=m,matched_static_initial_rule=base,
            balanced_increment_bits_per_nonzero=avg(delta),summed_increment_bits=raw,
            better_sequences=sum(v>0 for v in delta),worse_sequences=sum(v<0 for v in delta),
            worst_sequence_increment=min(delta) if delta else None,supported_sequences=len(delta)))
    output.mkdir(parents=True,exist_ok=False)
    P.csvout(output/'method_comparison.csv',summary);P.csvout(output/'qp_comparison.csv',qps);P.csvout(output/'component_comparison.csv',components)
    P.csvout(output/'pure_state_increment.csv',state_increments)
    groups=[v for v in signatures.values() if len(v)>1]
    P.save(output/'observed_rate_equal_groups.json',dict(groups=groups,meaning='same per-stream summed rate in this corpus; not proof of identical predictor/state or general algebraic equivalence'))
    result=dict(primary_units='balanced conditional TSRC estimated bits saved per nonzero; positive is better; not BD-rate',
        best_descriptive=best(summary),best_by_family={family:best([r for r in summary if r['family']==family]) for family in sorted({r['family'] for r in summary})},
        leave_one_content=fold_metrics,all_streams=scope['complete_streams'],source_report_sha256=P.sha(report/'report_scope.json'),
        best_pure_state_increment=max((r for r in state_increments if r['balanced_increment_bits_per_nonzero'] is not None),key=lambda r:r['balanced_increment_bits_per_nonzero'],default=None))
    P.save(output/'analysis_summary.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();summarize(a.report,a.output)
