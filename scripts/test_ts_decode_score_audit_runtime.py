#!/usr/bin/env python3
"""Decoder-only acceptance against an existing validated 17-frame manifest pair.
Writes derived no-SEI/corrupt fixtures into a new directory; never calls EncoderApp.
"""
import argparse,copy,json,os,re,subprocess
from pathlib import Path
import ts_decode_score_audit as a

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    m,decoder=a.inspect_manifest(args.manifest);pair=next(x for x in m['pairs'] if x['pair_id']=='Johnny_QP32_prefix17')
    out=args.output;out.mkdir(parents=True,exist_ok=False);base=args.manifest.resolve().parent;results=[]
    nohash=copy.deepcopy(m);nohash['decoder']['path']=str(decoder);nohash['pairs']=[copy.deepcopy(pair)];nohash['pairs'][0]['pair_id']='no_SEI_fixture'
    for origin,s in nohash['pairs'][0]['origins'].items():
        data=a.resolved(base,s['path']).read_bytes();starts=list(re.finditer(b'\x00\x00\x00\x01|\x00\x00\x01',data));chunks=[];removed=0
        for i,start in enumerate(starts):
            end=starts[i+1].start() if i+1<len(starts) else len(data);pos=start.end();b=data[pos];ext=(data[pos+1]>>1)&1 if b&1 else 0
            kind=((b>>7)<<4)+(b&8)+(ext<<2)+((b>>1)&3)
            if kind==6:removed+=1
            else:chunks.append(data[start.start():end])
        assert removed==17
        path=out/(origin+'_no_SEI.bin');path.write_bytes(b''.join(chunks));s.update(path=str(path.resolve()),sha256=a.sha(path),bytes=path.stat().st_size,sei_status='removed_in_decoder_only_test')
    a.save(out/'no_SEI_manifest.json',nohash)
    subprocess.run(['python3',str(Path(a.__file__)),'decode-pair','--manifest',str(out/'no_SEI_manifest.json'),'--pair','no_SEI_fixture','--output',str(out/'no_SEI'),'--verify-off'],check=True)
    for origin in a.NATIVE:
        v=a.read_json(out/'no_SEI'/origin/'decode_validation.json');assert v['sei_status']=='SEI_not_available' and v['on_off_equal'];results.append(dict(test='no_SEI_on_off',origin=origin,passed=True))
    # One replay visit is intentionally insufficient: decoder still succeeds,
    # retains reconstruction, and reports omitted audit samples explicitly.
    env={k:v for k,v in os.environ.items() if not k.startswith('TS_')};budget=out/'budget';budget.mkdir()
    source=a.resolved(base,pair['origins']['R13-1']['path']);env.update(TS_FIXED_PREDICTOR='r13_keep_hit_uniform',TS_SCORE_AUDIT=str(budget.resolve()),TS_AUDIT_VISITS='1',TS_AUDIT_HASH=str((budget/'hash.csv').resolve()))
    rc,truncated=a.bounded_run([str(decoder),'-b',str(source),'-o','','-dph','1'],env,budget/'decode.log');v=a.read_json(budget/'native_validation.json')
    assert rc==0 and not truncated and v['skipped_budget']>0 and v['replays']==0
    assert a.hash_frames(budget/'hash.csv')==a.hash_frames(out/'no_SEI/R13-1/reconstruction.csv')
    results.append(dict(test='replay_budget_does_not_change_decode',passed=True,skipped=v['skipped_budget']))
    summary=out/'summary';summary.mkdir();env.update(TS_SCORE_AUDIT=str(summary.resolve()),TS_AUDIT_PROFILE='summary',TS_AUDIT_HASH=str((summary/'hash.csv').resolve()))
    rc,_=a.bounded_run([str(decoder),'-b',str(source),'-o','','-dph','1'],env,summary/'decode.log');v=a.read_json(summary/'native_validation.json');assert rc==0 and v['replays']==0 and v['snapshot_bytes']==0
    results.append(dict(test='summary_no_replay_or_snapshot',passed=True))
    snapshot=next((out/'no_SEI/R13-1/snapshots').glob('*.tsa'));bad=out/'corrupt.tsa';content=bytearray(snapshot.read_bytes());content[-10]^=1;bad.write_bytes(content)
    rc,_=a.bounded_run([str(decoder),'--ts-audit-replay',str(bad),str(out/'bad_replay')],env,out/'corrupt_snapshot.log');assert rc!=0;results.append(dict(test='corrupt_snapshot_rejected',passed=True,returncode=rc))
    badstream=out/'truncated.bin';badstream.write_bytes(source.read_bytes()[:1000]);env={k:v for k,v in env.items() if not k.startswith(('TS_SCORE_AUDIT','TS_AUDIT_'))}
    rc,_=a.bounded_run([str(decoder),'-b',str(badstream),'-o','','-dph','1'],env,out/'truncated.log');assert rc!=0;results.append(dict(test='truncated_stream_rejected',passed=True,returncode=rc))
    broken=copy.deepcopy(nohash);broken['pairs'][0]['origins']['R13-1']['native_policy']='r13_keep_hit_spatial';a.save(out/'bad_manifest.json',broken)
    try:a.inspect_manifest(out/'bad_manifest.json')
    except ValueError:results.append(dict(test='wrong_origin_policy_rejected',passed=True))
    else:raise AssertionError('Invalid source binding accepted')
    a.save(out/'runtime_validation.json',results);print(json.dumps(results))

if __name__=='__main__':main()
