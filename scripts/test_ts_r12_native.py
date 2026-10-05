#!/usr/bin/env python3
"""Synthetic TSRC syntax tests ONLY: no EncoderApp/DecoderApp and no video."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
from ts_predictor_naming import R12_MODE_NUMBERS
from ts_r12_activity import parse

def run(executable,quant_executable,out,runtime):
    env={k:v for k,v in os.environ.items() if not k.startswith('TS_')}
    env.update(TS_FIXED_PREDICTOR=runtime,TS_R10_CACHE='0',TS_R10_STATS='0',TS_R11_STATS='0')
    mode=R12_MODE_NUMBERS.get(runtime,0); policy=85+mode if mode else 73
    def call(tag,options):
        process=subprocess.run([str(executable)],env={**env,**options},text=True,capture_output=True,timeout=300)
        (out/(runtime+'_'+tag+'.log')).write_text(process.stdout+process.stderr)
        if process.returncode: raise RuntimeError(f'{runtime}/{tag}: {process.stderr[-3000:]}')
        match=re.search(r'TS_NATIVE_DIGEST (\d+)',process.stdout)
        if not match or 'PASS '+runtime not in process.stdout: raise ValueError('Missing native identity/digest')
        return process,match.group(1)
    quiet,digest=call('off',{})
    observed,digest2=call('observed',dict(TS_R12_STATS='1',TS_R12_TRACE='1',TS_R12_DETAIL_LIMIT='3'))
    if digest!=digest2 or quiet.stdout!=observed.stdout: raise AssertionError('Observation changed native stream/result')
    rows=parse(observed.stderr,policy)
    if not rows or {r['mode'] for r in rows}!={mode}: raise AssertionError('Missing/wrong observation mode')
    traces=[line for line in observed.stderr.splitlines() if line.startswith('TS_R12_TRACE ')]
    # Per TU: all CG encoder traces followed by all CG decoder traces.
    i=0
    while i<len(traces):
        if ' cg=0 ' not in traces[i]: raise AssertionError('Missing TU start')
        j=i+1
        while j<len(traces) and ' cg=0 ' not in traces[j]: j+=1
        n=j-i
        if traces[i:j]!=traces[j:j+n]: raise AssertionError('Writer/Reader trace mismatch')
        i=j+n
    if len(traces)%2: raise AssertionError('Incomplete trace')
    details=sum(line.startswith('TS_R12_DETAIL ') for line in observed.stderr.splitlines())
    if details!=3: raise AssertionError('Unbounded/missing detailed output')
    result=dict(runtime=runtime,native_output=quiet.stdout.strip(),digest=digest,stats_rows=len(rows),
                writer_reader_cg_pairs=len(traces)//2,details=details,observation_bitexact=True)
    if not mode:
        shadow,shadow_digest=call('shadow',dict(TS_R12_STATS='1',TS_R12_SHADOW_MODES='1,7,9'))
        if shadow_digest!=digest or {r['mode'] for r in parse(shadow.stderr,policy)}!={1,7,9}:
            raise AssertionError('Shadow changed trajectory or modes')
        result['three_mode_shadow_bitexact']=True
    quant=subprocess.run([str(quant_executable)],env=env,text=True,capture_output=True,timeout=300)
    (out/(runtime+'_quant.log')).write_text(quant.stdout+quant.stderr)
    if quant.returncode or 'PASS '+runtime not in quant.stdout:
        raise RuntimeError('Native TS-RDOQ failed: '+runtime+' '+quant.stderr[-3000:])
    result['synthetic_quant_output']=quant.stdout.strip()
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exe',type=Path,default=Path('build/ts-r12/bin/TsRateCodecTest'))
    p.add_argument('--quant-exe',type=Path,default=Path('build/ts-r12/bin/TsR12QuantTest'))
    p.add_argument('--out',type=Path,default=Path('runs/ts_r12_native'))
    p.add_argument('--jobs',type=int,default=2)
    args=p.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    modes=['r10_integer_then_fractional',*R12_MODE_NUMBERS]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results=list(pool.map(lambda name:run(args.exe.resolve(),args.quant_exe.resolve(),args.out,name),modes))
    report=dict(revision='R12-POS-01',sequence_encode_decode=False,
        native_exe_sha256=hashlib.sha256(args.exe.read_bytes()).hexdigest(),
        quant_exe_sha256=hashlib.sha256(args.quant_exe.read_bytes()).hexdigest(),results=results)
    (args.out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    for row in results: print(row['runtime'],row['writer_reader_cg_pairs'],'CG pairs PASS')

if __name__=='__main__': main()
