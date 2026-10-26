#!/usr/bin/env python3
"""Generate all 61 causal schedules and report native whole-TU results.

Requires TS-RULE-LAB-v1 full-corpus exports and its integrated native decoder.
Will NOT substitute CE01 or synthetic tests for missing formal streams.
This file never launches an encoder.
"""
from __future__ import annotations
import argparse,csv,json,hashlib,math,heapq
from pathlib import Path
from collections import defaultdict
import rule_suite as R
import ts_learning as L
import ts_corpus as P

SCALE=32768


def catalogue_hash():
    return hashlib.sha256(json.dumps(R.catalogue(),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def make_schedules(index, output):
    idx=P.complete_index(index);out=Path(output)
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True);rules=R.catalogue();proof=[]
    P.save(out/'methods.json',dict(revision=R.REV,methods=rules))
    for record in idx['records']:
        task=record['task']; path=out/(task['key']+'.pred');nt=0
        with path.open('w') as f:
            f.write(f'TSCPRED 1 {len(rules)}\n')
            for tu in P.records(record['data']):
                if tu['kind']!='tu':continue
                if not tu.get('native_verified'):raise ValueError('Unverified input TU')
                rr=list(L.causal_rows(tu))
                f.write(' '.join(str(tu[k]) for k in ('poc','component','x','y','w','h','q_hash','entry_hash'))+' '+str(len(tu['q']))+'\n')
                for cfg in rules:
                    pred,_,_=R.predict(tu,cfg,prepared=rr)
                    f.write(' '.join(map(str,pred))+'\n')
                nt+=1
        proof.append(dict(task=task['key'],tu=nt,schedule_sha256=P.sha(path),source_sha256=record['data_sha256']))
        P.save(path.with_suffix('.json'),dict(revision=R.REV,methods=[c['id'] for c in rules],catalogue_sha256=catalogue_hash(),**proof[-1],causal_not_trained=True))
    P.save(out/'schedule_manifest.json',dict(revision=R.REV,source_index_sha256=P.sha(index),streams=proof,
        model_count=len(rules),all_streams_complete=len(proof)==idx['expected_streams'],
        future_native_evaluation_required=True))
    return proof


def aggregate(index, methods=None, extremes=None):
    """Consume true native model_rates_frac; never sum single-position deltas."""
    idx=P.complete_index(index);rules=methods or R.catalogue();M=len(rules);allrows=[]
    for record in idx['records']:
        if methods is None and (record['request'].get('method_ids')!=[c['id'] for c in rules] or record['request'].get('catalogue_sha256')!=catalogue_hash()):
            raise ValueError('Result method identities do not match frozen catalogue')
        t=record['task'];total=[[0]*M for _ in range(3)];fixed=[[0]*10 for _ in range(3)]
        tus=[0]*3;nz=[0]*3
        risk=[[[[0,0,0,0,0] for _ in range(3)] for _ in rules] for _ in range(3)]
        for tu in P.records(record['data']):
            if tu['kind']!='tu':continue
            if not tu.get('native_verified'):raise ValueError('Unverified TU in result')
            rates=tu.get('model_rates_frac')
            if rates is None or len(rates)!=M or any(not isinstance(v,int) or v<0 for v in rates):
                raise ValueError('Missing/invalid method rates; no zero-filling')
            if len(tu.get('rates_frac',[]))!=10:raise ValueError('Missing fixed controls')
            if M>=10 and rates[:10]!=tu['rates_frac']:raise ValueError('Native/Python fixed policy mismatch')
            c=tu['component'];tus[c]+=1;nz[c]+=tu['nonzero']
            for j,v in enumerate(rates):
                total[c][j]+=v
                for b,control in enumerate((0,L.EQ,L.SP)):
                    delta=v-tu['rates_frac'][control];stat=risk[c][j][b]
                    stat[0]+=delta>0;stat[1]+=delta<0;stat[2]+=max(0,delta);stat[3]+=max(0,-delta);stat[4]=max(stat[4],delta)
                    if extremes is not None and delta>0:
                        item=dict(task=t['key'],sequence=t['sequence'],qp=t['nominal_qp'],origin=t['origin'],component=c,
                            method=rules[j]['id'],reference=('Current','EQ','SP')[b],overspend_bits=delta/SCALE,
                            **{k:tu[k] for k in ('poc','x','y','w','h','q_hash','entry_hash')})
                        key=(rules[j]['id'],b);heap=extremes.setdefault(key,[])
                        ident=json.dumps(item,sort_keys=True);entry=(delta,ident)
                        if len(heap)<16:heapq.heappush(heap,entry)
                        elif entry>heap[0]:heapq.heapreplace(heap,entry)
            for j,v in enumerate(tu['rates_frac']):fixed[c][j]+=v
        for c in (0,1,2,'all'):
            cc=(0,1,2) if c=='all' else (c,)
            NN=sum(nz[j] for j in cc);TT=sum(tus[j] for j in cc)
            base=sum(fixed[j][0] for j in cc);eq=sum(fixed[j][L.EQ] for j in cc);sp=sum(fixed[j][L.SP] for j in cc)
            for m,cfg in enumerate(rules):
                rate=sum(total[j][m] for j in cc)
                allrows.append(dict(sequence=t['sequence'],qp=t['nominal_qp'],origin=t['origin'],component=c,
                    method=cfg['id'],family=cfg['family'],tu=TT,nonzero=NN,rate_frac=rate,estimated_bits=rate/SCALE,
                    current_bits=base/SCALE,eq_bits=eq/SCALE,sp_bits=sp/SCALE,
                    gain_vs_current_bits=(base-rate)/SCALE,gain_vs_eq_bits=(eq-rate)/SCALE,gain_vs_sp_bits=(sp-rate)/SCALE,
                    gain_vs_current_pct=100*(base-rate)/base if base else None,
                    gain_bits_per_nonzero=(base-rate)/SCALE/NN if NN else None,
                    scope='sum of complete TU fixed-q fixed-source-entry native replays; not BD-rate'))
                for b,label in enumerate(('current','eq','sp')):
                    stats=[risk[j][m][b] for j in cc]
                    allrows[-1].update({f'costlier_tu_vs_{label}':sum(s[0] for s in stats),
                        f'cheaper_tu_vs_{label}':sum(s[1] for s in stats),
                        f'positive_loss_vs_{label}_bits':sum(s[2] for s in stats)/SCALE,
                        f'gross_gain_vs_{label}_bits':sum(s[3] for s in stats)/SCALE,
                        f'max_tu_loss_vs_{label}_bits':max(s[4] for s in stats)/SCALE})
    return idx,allrows


def describe_and_select(rows,rules):
    # Different source geometries are NOT forced into TU pairs.
    cells=defaultdict(dict)
    for r in rows:
        if r['component']!='all':continue
        key=(r['sequence'],r['qp'],r['method'])
        if r['origin'] in cells[key]:raise ValueError('Duplicate source cell')
        cells[key][r['origin']]=r
    pairs=[];byseq=defaultdict(list)
    for (s,q,m),origins in sorted(cells.items()):
        if set(origins)!={'R13-1','R13-2'}:raise ValueError('Missing origin in paired results')
        valid=all(v['gain_bits_per_nonzero'] is not None for v in origins.values())
        value=sum(v['gain_bits_per_nonzero'] for v in origins.values())/2 if valid else None
        pairs.append(dict(sequence=s,qp=q,method=m,balanced_gain_bits_per_nonzero=value,
            both_origins_supported=valid))
        if valid:byseq[(s,m)].append(value)
    seqs=sorted({r['sequence'] for r in rows})
    expected={(s,q,c['id']) for s in seqs for q in (22,27,32,37) for c in rules}
    if set(cells)!=expected:raise ValueError('Missing or unexpected sequence/QP/method cells')
    seqrows=[]
    for s in seqs:
        for cfg in rules:
            vals=byseq[(s,cfg['id'])]
            seqrows.append(dict(sequence=s,method=cfg['id'],family=cfg['family'],supported_qps=len(vals),
                 balanced_gain_bits_per_nonzero=sum(vals)/len(vals) if vals else None))
    supported={s for s in seqs if all(byseq[(s,c['id'])] for c in rules)}
    ranking=[];lookup={(r['sequence'],r['method']):r['balanced_gain_bits_per_nonzero'] for r in seqrows}
    for cfg in rules:
        vals=[lookup[s,cfg['id']] for s in sorted(supported)]
        ranking.append(dict(method=cfg['id'],family=cfg['family'],supported_sequences=len(vals),
            descriptive_mean_gain_bits_per_nonzero=sum(vals)/len(vals) if vals else None,
            worst_sequence_gain_bits_per_nonzero=min(vals) if vals else None,
            beneficial_sequences=sum(x>0 for x in vals),harmful_sequences=sum(x<0 for x in vals),
            status='descriptive_all_content_ranking_not_unbiased_model_selection'))
    ranking.sort(key=lambda r: -(r['descriptive_mean_gain_bits_per_nonzero'] if r['descriptive_mean_gain_bits_per_nonzero'] is not None else -math.inf))
    folds=[]
    if len(supported)>=4:
        for held in sorted(supported):
            train=sorted(supported-{held})
            chosen=max(rules,key=lambda c:sum(lookup[s,c['id']] for s in train)/len(train))
            folds.append(dict(held_out_sequence=held,selected_method=chosen['id'],training_sequences=';'.join(train),
                train_gain_bits_per_nonzero=sum(lookup[s,chosen['id']] for s in train)/len(train),
                held_out_gain_bits_per_nonzero=lookup[held,chosen['id']],selection_uses_held_out_cost=False))
    return pairs,seqrows,ranking,folds


def report(index, output):
    out=Path(output)
    if out.exists():raise ValueError('Use a fresh report directory')
    extremes={};idx,rows=aggregate(index,extremes=extremes);rules=R.catalogue();out.mkdir(parents=True)
    pairs,seqrows,ranking,folds=describe_and_select(rows,rules)
    for name,records in [('all_methods_by_stream_component.csv',rows),('paired_source_metrics.csv',pairs),
                         ('by_sequence.csv',seqrows),('all_content_descriptive_ranking.csv',ranking),
                         ('leave_one_content_selection.csv',folds)]:P.csvout(out/name,records)
    cases=[json.loads(text) for key,heap in sorted(extremes.items()) for _,text in sorted(heap,reverse=True)]
    P.csvout(out/'worst_TU_cases.csv',cases)
    P.save(out/'methods.json',dict(revision=R.REV,catalogue_sha256=catalogue_hash(),methods=rules))
    P.save(out/'run_receipts.json',dict(revision=L.REV,streams=[dict(task=r['task'],request=r['request'],footer=r['footer'],frames=r['frames'],sei_status=r['sei_status'],on_off_equal=r['on_off_equal'],data_sha256=r['data_sha256']) for r in idx['records']]))
    P.save(out/'report_scope.json',dict(revision=R.REV,input_sha256=P.sha(index),complete_streams=idx['expected_streams'],
      native_whole_TU=True,fixed_q_only=True,encoding_invoked=False,
      no_BDrate=True,best_descriptive=ranking[0]['method'] if ranking and ranking[0]['supported_sequences'] else None,
      held_out_selected_mean_gain_bits_per_nonzero=sum(f['held_out_gain_bits_per_nonzero'] for f in folds)/len(folds) if folds else None,
      limitations=['Known development contents are not a fresh blind test set.',
       'Rule catalogue is predeclared; selecting on all-content ranking is still in-sample selection.',
       'Leave-one-content selection prevents held-out labels from choosing the rule; it does not erase prior human knowledge.',
       'No source-residual/RDOQ or encoder-search counterfactual can be inferred from final-q data.']))
    return ranking


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='cmd',required=True)
    for name in ('schedules','report'):
        q=s.add_parser(name);q.add_argument('--index',required=True);q.add_argument('--output',required=True)
    a=p.parse_args()
    if a.cmd=='schedules':make_schedules(a.index,a.output)
    else:report(a.index,a.output)


if __name__=='__main__':main()
