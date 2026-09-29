"""Independent selector reference. Native geometry/causality lives in TsRateCodecTest."""
import json
import random
import subprocess
import tempfile
import unittest
from pathlib import Path
from ts_predictor_naming import R11_MODE_NUMBERS, directory_name

ROOT=Path(__file__).resolve().parents[1]

class R11Design(unittest.TestCase):
    def test_selector(self):
        rng=random.Random(110929); lines=[]; expected=[]
        for _ in range(1800):
            for mode in range(1,9):
                n=rng.randrange(9); k=4 if mode in (5,6) else 3
                actions=[rng.randrange(8) for _ in range(k)]
                actions=[a if a>1 else 0 for a in actions]
                effective=rng.randrange(n+1)
                ci=[[rng.randrange(4)*(1<<35) for _ in range(k)] for _ in range(n)]
                cf=[[rng.randrange(1000000) for _ in range(k)] for _ in range(n)]
                si=[sum(r[e] for r in ci) for e in range(k)]; sf=[sum(r[e] for r in cf) for e in range(k)]
                raw=min(range(k),key=lambda e:si[e]); ties=si.count(si[raw]); fallback=False
                win=min(range(k),key=lambda e:(si[e],sf[e],e))
                if len(set(actions))==1 or not n: win=0
                if len(set(actions))>1 and not effective and mode in (1,7,8): win=2; fallback=True
                lines.append(' '.join(map(str,[mode,n,effective,*actions,*[v for a,b in zip(ci,cf) for pair in zip(a,b) for v in pair]])))
                expected.append((win,raw,ties,int(fallback)))
        # A/B/C agree at query, D differs: fourth column must not be skipped.
        for mode in (5,6):
            lines.append(f'{mode} 1 1 5 5 5 0 8 100 8 100 8 100 0 100')
            expected.append((3,3,1,0))
        # Historical losses may differ even when two query actions agree.
        lines.append('5 1 1 4 4 0 2 8 100 0 100 4 100 6 100'); expected.append((1,1,1,0))
        # Equal integer cost, nonzero structural evidence: preserve CF, no R3 fallback.
        lines.append('1 1 1 2 3 4 8 10 8 20 8 30'); expected.append((0,0,3,0))
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'probe'
            subprocess.run(['g++','-std=c++17','-O2','-Isource/Lib','scripts/ts_r11_formula_probe.cpp','-o',str(exe)],cwd=ROOT,check=True)
            r=subprocess.run([str(exe)],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True)
        self.assertEqual([tuple(map(int,r.split())) for r in r.stdout.splitlines()],expected)

    def test_registry_and_resource_scope(self):
        import batch_test
        manifest=json.loads((ROOT/'scripts/ts_r11_experiment_manifest.json').read_text())
        self.assertEqual(manifest['primary_control'],'r10_integer_then_fractional')
        self.assertEqual(manifest['stages']['CE']['all_modes_points'],224)
        self.assertFalse(manifest['stages']['B_sentinel']['automatic_launch'])
        self.assertEqual(set(R11_MODE_NUMBERS.values()),set(range(1,9)))
        for row in manifest['experiments']:
            self.assertEqual(R11_MODE_NUMBERS[row['runtime']],row['mode'])
            self.assertEqual(directory_name(row['runtime']),row['directory'])
            self.assertIn(row['runtime'],batch_test._TS_PREDICTOR_MODES)

    def test_stats_parser(self):
        from ts_r11_activity import parse
        header='trajectory_policy,mode,cutoff,bdpcm,regular_count,regular_nonzero,remap_vs_r10_3,v0_size,v3_size,v4_size,validation_size,effective_samples,selected_expert,target_regret_cf_selected'
        prefix='TS_R11_STATS_HEADER '+header+'\nTS_R11_STATS '
        good='73,4,10,0,1,1,1,2,4,8,8,3,2,99'
        self.assertEqual(parse(prefix+good,73)[0]['validation_size'],8)
        for index,value in ((0,'66'),(1,'9'),(2,'0'),(3,'1'),(6,'2'),(9,'3'),(10,'9'),(11,'9'),(12,'3'),(13,'-1')):
            vals=good.split(','); vals[index]=value
            with self.assertRaises(ValueError): parse(prefix+','.join(vals),73)

if __name__=='__main__': unittest.main()
