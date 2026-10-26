#!/usr/bin/env python3
"""R15 pure/native acceptance and independent selector timing. No EncoderApp.

Compile DecoderApp first with the TypeDef.h observer macro enabled. Test
programs use the existing common/decoder libraries and only BinEncoder.cpp
for local syntax fixtures. They do not link or run a video encoder.
"""
import argparse,json,os,platform,random,subprocess,sys,time
from pathlib import Path
import run as M
import reference as R
from test_r15 import cross_language
P=M.P;ROOT=M.ROOT


def compile_tests(build,out):
    out.mkdir(parents=True,exist_ok=True)
    common=['g++','-std=c++17','-O2','-DENABLE_TRACING=0','-DENABLE_CABAC_DUMP=0','-DTARGET_SIMD_X86',
            '-I'+str(ROOT/'source/Lib'),'-I'+str(ROOT/'source/Lib/CommonLib'),'-I'+str(ROOT/'thirdparty/sadl'),'-I'+str(ROOT/'thirdparty')]
    commands=[common+[str(ROOT/'tests/ts_multi_mapping/selectors.cpp'),'-o',str(out/'selectors')],
              common+[str(ROOT/'tests/ts_multi_mapping/syntax.cpp'),str(ROOT/'source/Lib/EncoderLib/BinEncoder.cpp'),
              str(build/'lib/libDecoderLib.a'),str(build/'lib/libCommonLib.a'),'-lpthread','-o',str(out/'syntax')]]
    for i,cmd in enumerate(commands):
        with (out/f'compile_{i}.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    P.save(out/'build_commands.json',dict(commands=commands,compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0]))


def validate_bundle(bundle):
    if bundle['protocol']!='TS-MG-ACTION-v1' or bundle['revision']!=R.REV or bundle['native_policy'] not in (98,99):raise ValueError('Action protocol/source mismatch')
    q=bundle['q'];scan=bundle['scan'];tu=bundle['tu'];dictionary=bundle['dictionary'];ids=bundle['action_ids'];n=len(q);maximum=1<<bundle['range']
    if len(ids)!=21 or any(len(v)!=n for v in ids) or sorted(scan)!=list(range(n)) or n!=tu['w']*tu['h']:raise ValueError('Action geometry/method mismatch')
    def hash_numbers(values):
        h=14695981039346656037
        for v in values:
            v=v%2**64
            for _ in range(8):h=((h^(v&255))*1099511628211)%2**64;v>>=8
        return h
    if str(hash_numbers(q))!=tu['q_hash'] or str(hash_numbers(scan))!=tu['scan_hash']:raise ValueError('Action q/scan identity mismatch')
    for action in dictionary:
        if len(action)>6 or len(set(action))!=len(action) or any(not isinstance(v,int) or v<1 or v>maximum for v in action):raise ValueError('Invalid action target')
        if tuple(action)!=R.canonical(action):raise ValueError('Noncanonical final action')
    inverse={p:i for i,p in enumerate(scan)};w=tu['w'];checked=0
    for i,pos in enumerate(scan):
        x,y=pos%w,pos//w;offsets=[-1 if x else 0,-w if y else 0,-w-1 if x and y else 0,-2 if x>1 else 0,-2*w if y>1 else 0]
        h=[abs(q[pos+o]) if o else 0 for o in offsets]
        assert all(inverse[pos+o]<i for o in offsets if o)
        for m,method in enumerate(R.METHODS):
            index=ids[m][i]
            if not isinstance(index,int) or not 0<=index<len(dictionary):raise ValueError('Action ID out of range')
            action,_=R.choose(h,method,bundle['rice'],bundle['range'])
            if tuple(dictionary[index])!=action:raise ValueError('Action differs from independent Python selector')
            checked+=1
    for m in range(21):
        values=[]
        for index in ids[m]:values += [len(dictionary[index]),*dictionary[index]]
        if hash_numbers(values)!=tu['action_hashes'][m]:raise ValueError('Action sequence digest mismatch')
    return checked


def validate(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);build=args.build_dir.resolve()
    compile_tests(build,out/'bin')
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'scripts/ts_multi_mapping'),'-p','test_r15.py','-v'],capture_output=True,text=True)
    (out/'python_tests.log').write_text(tests.stdout+tests.stderr)
    if tests.returncode:raise ValueError('Python tests failed')
    math=json.loads(subprocess.check_output([str(out/'bin/selectors')],text=True))
    native=json.loads(subprocess.check_output([str(out/'bin/syntax')],text=True))
    independent=cross_language(out/'bin/selectors')
    result=dict(revision=R.REV,math=math,native=native,independent=independent,encoding_invoked=False,
        source_sha256={s:P.sha(ROOT/s) for s in M.SOURCES},tests_sha256={p.name:P.sha(p) for p in (ROOT/'tests/ts_multi_mapping').glob('*.cpp')})
    P.save(out/'fast_equivalence.json',math);P.save(out/'native_validation.json',result)
    print(json.dumps(dict(validated=True,syntax_roundtrips=native['syntax_roundtrips'],method_triples=math['method_triples'],output=str(out))))


def snapshots(args):
    output=args.output;output.mkdir(parents=True,exist_ok=False);checked=[]
    files=sorted(args.input.rglob('*.actions.json'))
    if not files:raise ValueError('No captured action fixtures; replay --fixtures on the short prefix first')
    for i,file in enumerate(files):
        b=P.readj(file);positions=validate_bundle(b);snapshot=file.with_name(file.name.replace('.actions.json','.tsa'))
        target=output/f'replayed_{i}.json'
        subprocess.run([str(args.native.resolve()),'--snapshot',str(snapshot.resolve()),str(target.resolve())],check=True)
        r=P.readj(target)
        if r['q_hash']!=b['tu']['q_hash'] or r['entry_hash']!=b['tu']['entry_hash']:raise ValueError('Snapshot identity differs from action bundle')
        if [m['mg'] for m in r['methods']]!=M.IDS:raise ValueError('Snapshot missing method')
        if [m['rate_frac'] for m in r['methods']]!=b['tu']['rates_frac']:raise ValueError('Fresh-process rate differs')
        if [int(m['action_hash']) for m in r['methods']]!=b['tu']['action_hashes']:raise ValueError('Fresh-process actions differ')
        checked.append(dict(file=str(file),snapshot_sha256=P.sha(snapshot),action_sha256=P.sha(file),checks=positions,rate_exact=True))
    # Malformed external bundles are rejected; the live observer does not read
    # any external schedules at all, including the obsolete TSCPRED protocol.
    import copy
    bad=[];original=P.readj(files[0])
    for case in ('protocol','q','scan','target','missing_method','id'):
        b=copy.deepcopy(original)
        if case=='protocol':b['protocol']='TSCPRED'
        elif case=='q':b['q'][0]+=1
        elif case=='scan':b['scan'].reverse()
        elif case=='target':b['dictionary'][0]=[0]
        elif case=='missing_method':b['action_ids'].pop()
        else:b['action_ids'][0][0]=len(b['dictionary'])
        try:validate_bundle(b)
        except (ValueError,AssertionError):bad.append(case)
        else:raise AssertionError('Malformed bundle accepted: '+case)
    result=dict(revision=R.REV,complete=True,fixtures=checked,rejected_cases=bad,methods=21,encoder_app_invoked=False)
    P.save(output/'snapshot_validation.json',result);print(json.dumps(dict(complete=True,fixtures=len(checked),rejections=len(bad))))


def benchmark(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    allowed=sorted(os.sched_getaffinity(0));cpu=allowed[0] if args.cpu is None else args.cpu
    if cpu not in allowed:raise ValueError('Requested CPU is outside the allowed affinity')
    # A fixed synthetic H trace, no gate based on the unknown current magnitude.
    # All supports n=0..5, frequent plateaus, and some large Rice levels.
    rng=random.Random(20261026);trace=[]
    for i in range(args.positions):
        h=[rng.randrange(1,65) if j<i%6 else 0 for j in range(5)]
        rng.shuffle(h);trace.append(' '.join(map(str,[*h,1+i%8,15])))
    path=out/'trace.txt';path.write_text('\n'.join(trace)+'\n')
    with (out/'measurements.jsonl').open('w') as f:subprocess.run([str(args.native.resolve()),'--benchmark',str(path.resolve()),str(args.repeats)],stdout=f,check=True,preexec_fn=lambda:os.sched_setaffinity(0,{cpu}))
    rows=[json.loads(line) for line in (out/'measurements.jsonl').read_text().splitlines()];checks={}
    for r in rows:
        if r['engine']<3:
            key=r['mg'];checks.setdefault(key,set()).add(r['checksum'])
        r['ns_per_position']=r['nanoseconds']/r['positions'];r['operations']=json.dumps(r['operations'],separators=(',',':'))
    if any(len(v)!=1 for v in checks.values()):raise ValueError('Benchmark changed engine output')
    P.csvout(out/'complexity.csv',rows)
    P.save(out/'manifest.json',dict(revision=R.REV,trace='fixed synthetic H; not a video-population estimate',trace_sha256=P.sha(path),program_sha256=P.sha(args.native),
        platform=platform.platform(),cpu=platform.processor(),cpu_affinity=[cpu],repeats=args.repeats,warmups=1,rotating_engine_order=True,
        selectors=['NAIVE','PREFIX','FAST'],separate_kernels=['map','unmap'],operations='instrumented core search operations, not complete machine-instruction counts',checksums_equal=True))
    print(json.dumps(dict(output=str(out),rows=len(rows),checksums_equal=True)))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    q=sub.add_parser('validate');q.add_argument('--build-dir',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('snapshots');q.add_argument('--input',type=Path,required=True);q.add_argument('--native',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('benchmark');q.add_argument('--native',type=Path,required=True);q.add_argument('--output',type=Path,required=True);q.add_argument('--repeats',type=int,choices=range(5,21),default=5);q.add_argument('--positions',type=int,default=1024);q.add_argument('--cpu',type=int,help='pin helper to this CPU (default: first allowed CPU)')
    a=p.parse_args()
    if a.cmd=='benchmark' and not 1<=a.positions<=20000:p.error('positions must be 1..20000')
    dict(validate=validate,snapshots=snapshots,benchmark=benchmark)[a.cmd](a)

if __name__=='__main__':main()
