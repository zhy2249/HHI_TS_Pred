"""All 24 pure selectors versus independent specification, including boundaries."""
from itertools import product
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from ts_r8_all_reference import select
from ts_r8_first8_reference import FIRST8, select as frozen


class R8AllFormulaTest(unittest.TestCase):
    def test_cpp_all24(self):
        root = Path(__file__).resolve().parents[1]
        rng = random.Random(20260926)
        cases = []
        for limit in (4, 31, 32768):
            cf = (0,) + tuple(rng.randrange(1 << 40) for _ in range(limit))
            ci = (0,) + tuple((1+v.bit_length()) << 15 for v in range(1,limit+1))
            templates = list(product(range(3),repeat=5)) if limit == 4 else [
                tuple(rng.randrange(limit+1) for _ in range(5)) for j in range(16)]
            templates += [(limit,)*5,(0,0,0,0,0),(limit,limit,0,0,0),(1,limit,1,limit,0)]
            for a in templates:
                for m in range(1,25): cases.append((m,a,cf,ci,limit))
        with tempfile.TemporaryDirectory(prefix='ts-r8-all-formula-') as tmp:
            exe=Path(tmp)/'probe'
            subprocess.run(['g++','-O2','-std=c++17','-I',str(root/'source/Lib'),
                            str(root/'scripts/ts_r8_formula_probe.cpp'),'-o',str(exe)],check=True,capture_output=True)
            # Stream by domain to keep the large-range boundary input bounded.
            for limit in (4,31,32768):
                subset=[x for x in cases if x[-1]==limit]
                text='\n'.join(' '.join(map(str,(m,limit,*a,*cf,*ci))) for m,a,cf,ci,limit in subset)+'\n'
                result=subprocess.run([str(exe)],input=text,text=True,capture_output=True,check=True)
                lines=result.stdout.splitlines()
                self.assertEqual(len(lines),len(subset))
                for line,(m,a,cf,ci,limit) in zip(lines,subset):
                    r=select(m,a,cf,ci,limit)
                    if m in FIRST8: self.assertEqual(r,frozen(m,a,cf,ci,limit))
                    expected=[r.current,r.predictor,r.support,r.raw_winner if r.raw_winner is not None else r.current,
                              r.raw_gain or 0,r.raw_margin or 0,len(r.candidates)]
                    for k,p in enumerate(r.candidates): expected.extend((p,r.scores[k],r.regrets[k] if r.regrets else 0))
                    self.assertEqual(list(map(int,line.split())),expected,(m,a,limit))


if __name__=='__main__': unittest.main()
