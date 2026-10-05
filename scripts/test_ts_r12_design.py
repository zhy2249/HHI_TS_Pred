"""Pure functions only; compare production C++ to the independently uploaded spec."""
import importlib.util
import itertools
import json
import random
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ts_predictor_naming import R12_MODE_NUMBERS, directory_name

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('r12_reference',ROOT/'docs/external_inputs/r12_position/r12_rule_reference.py')
ref=importlib.util.module_from_spec(spec); spec.loader.exec_module(ref)
Q=1<<15

class R12Design(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.exe=Path(cls.tmp.name)/'probe'
        subprocess.run(['g++','-std=c++17','-O2','-Isource/Lib','scripts/ts_r12_formula_probe.cpp',
                        '-o',str(cls.exe)],cwd=ROOT,check=True)
        cls.options=Path(cls.tmp.name)/'options'
        subprocess.run(['g++','-std=c++17','-Isource/Lib/CommonLib','scripts/ts_fixed_mode_probe.cpp',
                        '-o',str(cls.options)],cwd=ROOT,check=True)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def probe(self, lines):
        result=subprocess.run([str(self.exe)],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True)
        return [tuple(map(int,line.split())) for line in result.stdout.splitlines()]

    def test_outer_reference(self):
        rng=random.Random(1201001); lines=[]; expected=[]
        for _ in range(4000):
            n=rng.randrange(6); positions=rng.sample(range(5),n)
            ef=[bool(rng.randrange(2)) for _ in range(n)]
            # Include narrow integer gaps and 64-bit losses; absolute totals can be huge.
            offset=rng.choice((0,1<<35)); ci=[[offset+rng.randrange(5)*Q for _ in range(4)] for _ in range(n)]
            cf=[[offset+rng.randrange(8)*17000 for _ in range(4)] for _ in range(n)]
            for mode in range(13):
                k=4 if mode==3 else 3
                equivalent=9 if mode==12 else 0 if mode in (0,7,8,11) else mode
                winner=ref.select(equivalent,ci,cf,positions,ef,q=Q) if equivalent else ref.baseline(ci,cf)
                li=ref.totals(ci,3); ties=len(ref.argmins(li))
                base=ref.baseline(ci,cf); legal=sum(ef) if sum(ef)>=2 else 0
                rows=[v for j in range(n) for v in [positions[j],int(ef[j]),*[v for e in range(k) for v in (ci[j][e],cf[j][e])]]]
                lines.append(' '.join(map(str,['S',mode,n,*rows]))); expected.append((winner,base,ties,legal))
        self.assertEqual(self.probe(lines),expected)

    def test_weighted_small_exhaustive(self):
        lines=[]; expected=[]; costs=[ref.small_ci(a)*Q for a in range(10)]
        for h in itertools.product(range(6),repeat=5):
            for mode,policy in ((7,'raw'),(8,'full'),(11,'soft'),(12,'raw')):
                lines.append(' '.join(map(str,['I',mode,*h,*ref.W])))
                expected.append(ref.weighted_predict(h,costs,policy))
        self.assertEqual(self.probe(lines),expected)

    def test_uniform_and_axis_symmetry(self):
        rng=random.Random(1201002); lines=[]; expected=[]; costs=[ref.small_ci(a)*Q for a in range(10)]
        for _ in range(2000):
            h=[rng.randrange(8) for _ in range(5)]
            for mode,policy in ((7,'raw'),(8,'full')):
                for weights in ((1,1,1,1,1),ref.W,tuple(2*v for v in ref.W)):
                    lines.append(' '.join(map(str,['I',mode,*h,*weights])))
                    expected.append(ref.weighted_predict(h,costs,policy,weights))
        self.assertEqual(self.probe(lines),expected)

    def test_registry_and_scope(self):
        import batch_test
        manifest=json.loads((ROOT/'scripts/ts_r12_experiment_manifest.json').read_text())
        self.assertEqual(manifest['revision'],'R12-POS-01')
        self.assertEqual(manifest['default_modes'],[1,2,4,7,8,9])
        self.assertEqual(manifest['primary_control'],'r10_integer_then_fractional')
        self.assertFalse(manifest['stages']['B_sentinel']['automatic_launch'])
        self.assertEqual(set(R12_MODE_NUMBERS.values()),set(range(1,13)))
        for row in manifest['experiments']:
            self.assertEqual(row['mode'],R12_MODE_NUMBERS[row['runtime']])
            self.assertEqual(row['directory'],directory_name(row['runtime']))
            self.assertIn(row['runtime'],batch_test._TS_PREDICTOR_MODES)

    def test_probe_excludes_observers(self):
        import batch_test
        import os
        from types import SimpleNamespace
        with patch.dict(os.environ,dict(TS_R12_STATS='1',TS_R12_TRACE='1',TS_R12_SHADOW_MODES='1,7,9',TS_R12_DETAIL_LIMIT='3')):
            with patch.object(batch_test.os,'access',return_value=True), patch.object(batch_test.subprocess,'run',return_value=SimpleNamespace(stdout='EXPERIMENT: TS_FIXED_PREDICTOR=current;')) as call:
                self.assertIn('current',batch_test._detect_experiment_line(ROOT/'scripts/batch_test.py',ROOT))
                self.assertFalse(any(k.startswith('TS_R12_') for k in call.call_args.kwargs['env']))

    def test_axis_and_guard_nesting(self):
        rng=random.Random(1201003); lines=[]
        for _ in range(2000):
            h=[rng.randrange(8) for _ in range(5)]; swapped=[h[1],h[0],h[2],h[4],h[3]]
            for mode in (7,8,11):
                for support in (h,swapped): lines.append(' '.join(map(str,['I',mode,*support,*ref.W])))
        output=self.probe(lines)
        for row in range(0,len(output),6):
            for offset in (0,2,4): self.assertEqual(output[row+offset],output[row+offset+1])
            raw,full,soft=output[row],output[row+2],output[row+4]
            self.assertEqual(raw[1:3],full[1:3]); self.assertEqual(raw[1:3],soft[1:3])
            self.assertGreaterEqual(full[3],soft[3]); self.assertGreaterEqual(soft[3],raw[3])

    def test_observation_options_fail_closed(self):
        import os
        env={k:v for k,v in os.environ.items() if not k.startswith('TS_')}
        env['TS_FIXED_PREDICTOR']='r12_ci_near1'
        valid=({'TS_R12_STATS':'1'}, {'TS_R12_TRACE':'1'},
               {'TS_R12_STATS':'1','TS_R12_SHADOW_MODES':'1,7,9','TS_R12_DETAIL_LIMIT':'3'})
        invalid=({'TS_R12_STATS':'yes'}, {'TS_R12_TRACE':'2'}, {'TS_R12_DETAIL_LIMIT':'1'},
                 {'TS_R12_STATS':'1','TS_R12_DETAIL_LIMIT':'1025'},
                 {'TS_R12_SHADOW_MODES':'1'}, {'TS_R12_STATS':'1','TS_FIXED_PREDICTOR':'current'})
        invalid+=tuple({'TS_R12_STATS':'1','TS_R12_SHADOW_MODES':s} for s in ('0','13','1,1','1,2,3,4','1,','1 2','1,,2','-1'))
        for options in valid:
            self.assertEqual(subprocess.run([str(self.options)],env={**env,**options},capture_output=True).returncode,0)
        for options in invalid:
            self.assertNotEqual(subprocess.run([str(self.options)],env={**env,**options},capture_output=True).returncode,0)

    def test_stats_parser_rejects_invalid_identity(self):
        from ts_r12_activity import parse
        self.assertEqual(parse('',86),[])
        for text in ('TS_R12_STATS 86,1', 'TS_R12_STATS_HEADER mode,mode',
                     'TS_R12_STATS_HEADER mode\nTS_R12_STATS 1'):
            with self.assertRaises(ValueError): parse(text,86)

if __name__=='__main__': unittest.main()
