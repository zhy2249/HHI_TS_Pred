#!/usr/bin/env python3
"""Small decoder-only acceptance before full 61-rule collection; no encoder.

Uses the existing paired prefix, then rejects malformed external schedules.
Optional JSONL fixtures come from the local Writer/Reader syntax unit test.
"""
import argparse, copy, json, subprocess
from pathlib import Path
import ts_corpus as P
import ts_learning as L
import rule_suite as R
import benchmark_rules as B


def write_schedule(path, task, records):
    rules=R.catalogue(); lines=[f'TSCPRED 1 {len(rules)}']
    for tu in records:
        lines.append(' '.join(str(tu[k]) for k in ('poc','component','x','y','w','h','q_hash','entry_hash'))+' '+str(len(tu['q'])))
        prepared=list(L.causal_rows(tu))
        for cfg in rules:
            pred,_,_=R.predict(tu,cfg,prepared=prepared)
            lines.append(' '.join(map(str,pred)))
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text('\n'.join(lines)+'\n')
    sidecar(path,task)


def sidecar(path,task):
    P.save(path.with_suffix('.json'),dict(task=task['key'],schedule_sha256=P.sha(path),
        methods=[c['id'] for c in R.catalogue()],catalogue_sha256=B.catalogue_hash()))


def validate(args):
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    manifest=P.readj(args.manifest);base=args.manifest.resolve().parent
    pair=next(p for p in manifest['pairs'] if p['pair_id']=='Johnny_QP32_prefix17')
    checks=[];sources=[]
    for origin,native in P.origins().items():
        s=pair['origins'][origin]
        task=dict(key=pair['pair_id']+'__'+origin,pair_id=pair['pair_id'],sequence=pair['sequence'],
            nominal_qp=pair['nominal_qp'],origin=origin,native_policy=native,
            stream=str((base/s['path']).resolve()),stream_sha256=s['sha256'],bytes=s['bytes'],expected_frames=17)
        first=P.run_task(task,args.decoder,root/'corpus',verify_off=True,with_labels=True)
        tus=[t for t in P.records(first['data']) if t['kind']=='tu']
        path=root/'schedules'/(task['key']+'.pred');write_schedule(path,task,tus)
        second=P.run_task(task,args.decoder,root/'evaluation',verify_off=True,schedule_dir=path.parent)
        actual=[t for t in P.records(second['data']) if t['kind']=='tu']
        assert len(actual)==len(tus)>0
        for x,y in zip(tus,actual):
            assert P.tu_key(x)==P.tu_key(y) and x['q_hash']==y['q_hash'] and x['entry_hash']==y['entry_hash']
            assert x['rates_frac']==y['rates_frac']==y['model_rates_frac'][:10]
            assert len(y['model_rates_frac'])==61
        assert first['on_off_equal'] and second['on_off_equal']
        checks.append(dict(test='paired_prefix_fixed_controls_and_61_whole_TU_replays',origin=origin,
            frames=first['frames'],tu=len(tus),labels=first['footer']['labeled_positions'],
            on_off_equal=True,all_61=True,first_ten_exact=True,sei_status=second['sei_status']))
        sources.append((task,path))
    task,path=sources[0];original=path.read_text().splitlines()
    for case in ('wrong_q','wrong_context','wrong_geometry','short_schedule','extra_row','negative_predictor'):
        lines=original[:];header=lines[1].split()
        if case in ('wrong_q','wrong_context','wrong_geometry'):
            field={'wrong_q':6,'wrong_context':7,'wrong_geometry':2}[case]
            header[field]=str(int(header[field])+1);lines[1]=' '.join(header)
        elif case=='short_schedule':lines=lines[:-1]
        elif case=='extra_row':lines.append('unexpected')
        else:
            values=lines[2].split();values[0]='-1';lines[2]=' '.join(values)
        bad=root/'bad_schedules'/case/path.name;bad.parent.mkdir(parents=True)
        bad.write_text('\n'.join(lines)+'\n');sidecar(bad,task)
        try:P.run_task(task,args.decoder,root/'rejections'/case,schedule_dir=bad.parent)
        except ValueError as exc:checks.append(dict(test=case,rejected=True,error=str(exc)))
        else:raise AssertionError('Malformed schedule accepted: '+case)
    fixture_records=0;fixture_positions=0
    for file in args.fixtures:
        for line in file.read_text().splitlines():
            tu=json.loads(line);rows=list(L.causal_rows(tu));fixture_records+=1;fixture_positions+=len(rows)
            for m in range(10):assert [r['pred'][m] for r in rows]==tu['pred'][m],(file,tu['trial'],m)
    if args.fixtures:checks.append(dict(test='native_Python_fixed_prediction_sequences',tu=fixture_records,positions=fixture_positions,all_ten_exact=True))
    result=dict(revision=L.REV,decoder_sha256=P.sha(args.decoder),manifest_sha256=P.sha(args.manifest),
        rules_sha256=P.sha(R.__file__),scoring_sha256=P.sha(L.__file__),checks=checks,passed=True,
        scope='paired 17-frame prefix and optional synthetic syntax fixtures; not full-dataset results',encoding_invoked=False)
    P.save(root/'validation.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--decoder',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fixtures',type=Path,nargs='*',default=[])
    validate(p.parse_args())
