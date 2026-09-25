"""C++ versus independent reference: exhaustive small domain and boundary cases."""
from itertools import product
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from ts_r8_first8_reference import FIRST8, select


class R8CodecFormulaTest(unittest.TestCase):
    def test_cpp_matches_frozen_reference(self):
        root = Path(__file__).resolve().parents[1]
        ci = tuple(v << 15 for v in (0, 1, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 8))
        profiles = (ci, (0,) + (32768,) * 12,
                    (0,) + tuple((1 + (v*v+7*v+3) % 19) << 15 for v in range(1,13)))
        cases = [(m, a, cf, ci, 12) for cf in profiles for a in product(range(4),repeat=5) for m in FIRST8]
        rng = random.Random(20260925)
        for limit in (2, 8, 64, 32768):
            # Large integral costs expose accidental int32 loss/margin overflow.
            cf = (0,) + tuple(rng.randrange(1 << 40) for _ in range(limit))
            integer = (0,) + tuple((1 + v.bit_length()) << 15 for v in range(1,limit+1))
            for a in ((limit,)*5, (1,limit,1,limit,0), (limit,limit-1,limit-2,1,2)):
                for m in FIRST8: cases.append((m,a,cf,integer,limit))
        lines = [' '.join(map(str,(m,limit,*a,*cf,*integer))) for m,a,cf,integer,limit in cases]
        with tempfile.TemporaryDirectory(prefix='ts-r8-formula-') as tmp:
            exe = Path(tmp)/'probe'
            subprocess.run(['g++','-O2','-std=c++17','-I',str(root/'source/Lib'),
                            str(root/'scripts/ts_r8_formula_probe.cpp'),'-o',str(exe)],check=True,capture_output=True)
            result = subprocess.run([str(exe)],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True)
        output = result.stdout.splitlines()
        self.assertEqual(len(output),len(cases))
        for line,(m,a,cf,integer,limit) in zip(output,cases):
            r = select(m,a,cf,integer,limit)
            actual = list(map(int,line.split()))
            expected = [r.current,r.predictor,r.support,
                        r.raw_winner if r.raw_winner is not None else r.current,
                        r.raw_gain or 0,r.raw_margin or 0,len(r.candidates)]
            for i,p in enumerate(r.candidates):
                expected += [p,r.scores[i],r.regrets[i] if r.regrets else 0]
            self.assertEqual(actual,expected,(m,a,limit))


if __name__ == '__main__': unittest.main()
