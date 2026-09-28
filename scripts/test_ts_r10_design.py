"""Independent local validation matrix reference; arbitrary, nonmonotone costs."""
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from ts_predictor_naming import R10_MODE_NUMBERS, directory_name

ROOT=Path(__file__).resolve().parents[1]

class R10Design(unittest.TestCase):
    def test_reference(self):
        rng=random.Random(20260928)
        lines, expected = [], []
        for _ in range(1600):
            for mode in range(1,8):
                n=rng.randrange(6); k=4 if mode==6 else 3; distinct=rng.randint(1,k)
                ci=[[rng.randrange(4)*32768 for e in range(k)] for j in range(n)]
                cf=[[rng.randrange(300000) for e in range(k)] for j in range(n)]
                weights=[rng.randint(1,2) if mode==4 else 1 for j in range(n)]
                si=[sum(weights[j]*ci[j][e] for j in range(n)) for e in range(k)]
                sf=[sum(cf[j][e] for j in range(n)) for e in range(k)]
                raw=min(range(k),key=lambda e:si[e]); ties=si.count(si[raw])
                winner=min(range(k),key=lambda e:(si[e],sf[e])) if mode in (3,7) else raw
                reject=False
                if mode==5 and winner:
                    gains=[row[0]-row[winner] for row in ci]
                    reject=sum(gains)-max([0]+gains)<=0
                    if reject: winner=0
                if distinct==1 or n==0: winner=0; reject=False
                tokens=[mode,n,distinct]
                for j in range(n):
                    tokens.append(weights[j])
                    for e in range(k): tokens.extend((ci[j][e],cf[j][e]))
                lines.append(' '.join(map(str,tokens)))
                expected.append((winner,raw,ties,int(reject)))
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'probe'
            subprocess.run(['g++','-std=c++17','-O2','-Isource/Lib','scripts/ts_r10_formula_probe.cpp','-o',str(exe)],cwd=ROOT,check=True)
            r=subprocess.run([str(exe)],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True)
        self.assertEqual([tuple(map(int,row.split())) for row in r.stdout.splitlines()],expected)

    def test_registry(self):
        import batch_test
        manifest=json.loads((ROOT/'scripts/ts_r10_experiment_manifest.json').read_text())
        self.assertEqual(set(R10_MODE_NUMBERS.values()),set(range(1,8)))
        for row in manifest['experiments']:
            self.assertEqual(R10_MODE_NUMBERS[row['runtime']],row['mode'])
            self.assertEqual(directory_name(row['runtime']),row['directory'])
            self.assertIn(row['runtime'],batch_test._TS_PREDICTOR_MODES)

    def test_parser(self):
        from ts_r10_activity import parse
        fields='mode,cutoff,bdpcm,regular_count,regular_nonzero,remap_vs_r9_9,validation_size,effective_samples,selected_expert,target_regret_ci_selected'
        prefix='TS_R10_STATS_HEADER '+fields+'\nTS_R10_STATS '
        self.assertEqual(parse(prefix+'6,10,0,1,1,1,3,2,3,44',6)[0]['target_regret_ci_selected'],44)
        for bad in ('6,0,0,1,1,1,3,2,3,44','6,10,1,1,1,1,3,2,3,44',
                    '6,10,0,1,1,1,2,3,3,44','6,10,0,1,1,1,2,1,4,44',
                    '6,10,0,1,1,1,3,2,3,-1','7,10,0,1,1,1,3,2,3,0'):
            with self.assertRaises(ValueError): parse(prefix+bad,6)

    def test_capability_probe_ignores_cache_override(self):
        import batch_test
        with patch.dict('os.environ',{'TS_R10_CACHE':'1'}), patch('batch_test.os.access',return_value=True), \
                patch('batch_test.subprocess.run') as run:
            run.return_value.stdout='EXPERIMENT: TS_FIXED_PREDICTOR=current; syntax=experimental-v1\n'
            self.assertIn('current',batch_test._detect_experiment_line(ROOT/'scripts/batch_test.py',ROOT))
            self.assertEqual(run.call_args.kwargs['env']['TS_R10_CACHE'],'0')

if __name__=='__main__': unittest.main()
