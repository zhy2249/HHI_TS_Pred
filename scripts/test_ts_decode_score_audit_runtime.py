#!/usr/bin/env python3
"""Decoder-only impl2 acceptance on an existing, verified EQ/SP 17-frame pair."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import ts_decode_score_audit as a


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pair',default='Johnny_QP32_prefix17');p.add_argument('--legacy-snapshot',type=Path)
    args=p.parse_args();m,decoder=a.inspect_manifest(args.manifest)
    pair=next(x for x in m['pairs'] if x['pair_id']==args.pair)
    if pair.get('expected_frames')!=17:raise ValueError('This acceptance fixture requires the verified 17-frame pair')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False);results=[]
    script=str(Path(a.__file__).resolve());manifest=args.manifest.resolve();base=manifest.parent
    def command(name,extra=(),source=manifest,pair_id=args.pair):
        cmd=['python3',script,'decode-pair','--manifest',str(source),'--pair',pair_id,'--first-poc','0','--last-poc','16',
             '--verify-off','--output',str(root/name),*extra]
        proc=subprocess.run(cmd,text=True,capture_output=True)
        (root/(name+'_driver.log')).write_text(proc.stdout+proc.stderr)
        if proc.returncode:raise AssertionError((name,proc.returncode,proc.stderr))
        return cmd
    profiles={'standard':[], 'summary':['--profile','summary'], 'limited':['--replays','6'],
              'no_snapshot':['--snapshot-bytes','0'], 'truncated':['--raw-bytes','400'], 'no_replay':['--visits','0']}
    commands={name:command(name,opts) for name,opts in profiles.items()}
    for origin in a.NATIVE:
        values={name:a.read_json(root/name/origin/'decode_validation.json') for name in profiles}
        assert all(v['decode_complete'] and v['on_off_equal'] for v in values.values())
        v=values['standard'];assert v['audit_complete'] and all(v['policy_complete']) and v['native_replay_complete']
        assert v['sei_md5_ok_count']==17
        for name in ('limited','no_snapshot','truncated','no_replay'):assert not values[name]['audit_complete']
        assert any(values['limited']['policy_complete']) and not all(values['limited']['policy_complete'])
        assert values['no_snapshot']['snapshot_complete'] is False and values['no_snapshot']['output_complete']
        assert values['no_snapshot']['native_replay']['snapshot_skipped_budget']>0
        assert not values['truncated']['output_complete'] and values['truncated']['native_replay']['output_dropped_records']>0
        assert values['no_replay']['native_replay']['replays']==0
        summary=values['summary'];assert summary['audit_complete'] is None and summary['native_replay']['replays']==0 and summary['native_replay']['snapshot_bytes']==0
        census_keys=('poc','component','tu','coeff','nz','target_tu','target_coeff','target_nz','eligible_tu','eligible_coeff','eligible_nz',
                     'scoring_eligible_tu','scoring_eligible_nz','slice_cu_counts','amplitude_counts','support_counts')
        rows=[a.read_csv(root/name/origin/'census.csv') for name in ('standard','summary')]
        assert [[r[k] for k in census_keys] for r in rows[0]]==[[r[k] for k in census_keys] for r in rows[1]]
        results.append(dict(test='standard_summary_budget_snapshot_output_states',origin=origin,passed=True,
            native_tu=v['native_replay']['native_verified_tu'],limited_policy_complete=values['limited']['policy_complete'],
            observed_B_slice_intra_TU=sum(json.loads(r['slice_cu_counts'])[0] for r in rows[0])))
        table=a.read_csv(root/'standard'/origin/'tu_policy_matrix.csv')
        for row in table:
            target=root/'offline'/origin/row['id']
            subprocess.run([str(decoder),'--ts-audit-replay',str(root/'standard'/origin/row['snapshot']),str(target)],check=True)
            replay=a.read_json(target/'replay.json')
            assert replay['native_validated'] and replay['rates_frac']==[int(row[n+'_frac']) for n in a.POLICIES]
            assert replay['slice_type']==row['slice_type'] and replay['is_intra_cu']==int(row['is_intra_cu'])
        results.append(dict(test='independent_process_snapshot_all_seven_rates',origin=origin,passed=True,snapshots=len(table)))
    for name in ('limited','truncated','no_replay'):
        comparison=a.read_json(root/name/'pair_comparison.json')
        assert all(r['bits_per_tu'] is None and r['bits_per_nonzero'] is None for r in comparison['rows'] if r['origin']=='balanced')
    results.append(dict(test='incomplete_comparisons_are_NA',passed=True))
    # Construct no-SEI files from actual bitstream bytes; no encoding performed.
    nohash=copy.deepcopy(m);nohash['decoder']['path']=str(decoder);nohash['pairs']=[copy.deepcopy(pair)];nohash['pairs'][0]['pair_id']='no_SEI_fixture'
    for origin,s in nohash['pairs'][0]['origins'].items():
        data=a.resolved(base,s['path']).read_bytes();starts=list(re.finditer(b'\x00\x00\x00\x01|\x00\x00\x01',data));chunks=[];removed=0
        for i,start in enumerate(starts):
            end=starts[i+1].start() if i+1<len(starts) else len(data);pos=start.end();b=data[pos];ext=(data[pos+1]>>1)&1 if b&1 else 0
            kind=((b>>7)<<4)+(b&8)+(ext<<2)+((b>>1)&3)
            if kind==6:removed+=1
            else:chunks.append(data[start.start():end])
        assert removed==17
        path=root/(origin+'_no_SEI.bin');path.write_bytes(b''.join(chunks));s.update(path=str(path),sha256=a.sha(path),bytes=path.stat().st_size)
    a.save(root/'no_SEI_manifest.json',nohash);command('no_SEI',source=root/'no_SEI_manifest.json',pair_id='no_SEI_fixture')
    for origin in a.NATIVE:
        v=a.read_json(root/'no_SEI'/origin/'decode_validation.json')
        assert v['sei_status']=='SEI_not_available' and v['on_off_equal']
        results.append(dict(test='no_SEI_on_off_is_not_encoder_SEI_verification',origin=origin,passed=True))
    env={k:v for k,v in os.environ.items() if not k.startswith('TS_')}
    snapshot=next((root/'standard/R13-1/snapshots').glob('*.tsa'));bad=root/'corrupt.tsa';content=bytearray(snapshot.read_bytes());content[-10]^=1;bad.write_bytes(content)
    rc,_=a.bounded_run([str(decoder),'--ts-audit-replay',str(bad),str(root/'bad_replay')],env,root/'corrupt_snapshot.log')
    assert rc!=0;results.append(dict(test='corrupt_snapshot_rejected',passed=True,returncode=rc))
    for origin in a.NATIVE:
        source=a.resolved(base,pair['origins'][origin]['path']);badstream=root/(origin+'_truncated.bin');badstream.write_bytes(source.read_bytes()[:1000])
        local_env=dict(env,TS_FIXED_PREDICTOR=a.NATIVE[origin])
        rc,_=a.bounded_run([str(decoder),'-b',str(badstream),'-o','','-dph','1'],local_env,root/(origin+'_truncated.log'))
        assert rc!=0;results.append(dict(test='truncated_stream_rejected',origin=origin,passed=True,returncode=rc))
    broken=copy.deepcopy(nohash);broken['pairs'][0]['origins']['R13-1']['native_policy']='r13_keep_hit_spatial';a.save(root/'bad_manifest.json',broken)
    try:a.inspect_manifest(root/'bad_manifest.json')
    except ValueError:results.append(dict(test='wrong_origin_policy_rejected',passed=True))
    else:raise AssertionError('Invalid source binding accepted')
    pointer=root/'pointer.bin';pointer.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:fake\nsize 100\n')
    broken=copy.deepcopy(nohash);broken['pairs'][0]['origins']['R13-1'].update(path=str(pointer),bytes=pointer.stat().st_size,sha256=a.sha(pointer));a.save(root/'lfs_manifest.json',broken)
    try:a.inspect_manifest(root/'lfs_manifest.json')
    except ValueError as e:assert 'LFS pointer' in str(e);results.append(dict(test='LFS_pointer_rejected',passed=True))
    else:raise AssertionError('LFS pointer accepted')
    stamps=[(root/'standard'/o/'decode.log').stat().st_mtime_ns for o in a.NATIVE]
    subprocess.run(commands['standard']+['--resume'],check=True,capture_output=True)
    assert stamps==[(root/'standard'/o/'decode.log').stat().st_mtime_ns for o in a.NATIVE]
    results.append(dict(test='matching_resume_does_not_redecode',passed=True))
    if args.legacy_snapshot:
        target=root/'legacy_replay';subprocess.run([str(decoder),'--ts-audit-replay',str(args.legacy_snapshot.resolve()),str(target)],check=True)
        replay=a.read_json(target/'replay.json');assert replay['native_validated'] and replay['slice_type']=='unknown' and replay['is_inter_cu']==-1
        results.append(dict(test='legacy_snapshot_does_not_invent_slice_type',passed=True))
    a.save(root/'runtime_validation.json',dict(revision=a.REV,decoder_sha256=a.sha(decoder),manifest_sha256=a.sha(manifest),results=results))
    print(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
