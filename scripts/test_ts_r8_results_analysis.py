import math
import unittest
from ts_fixed_analyze import SEQUENCES
from ts_r8_results_analysis import MODES, PRIMARY, factorial, summarize


class R8ResultsTests(unittest.TestCase):
    def test_scope_excludes_unfinished_19(self):
        self.assertEqual(MODES,(1,4,8,13,15,16,17))
        self.assertEqual(PRIMARY[15],'R7-1')
        self.assertEqual(PRIMARY[16],'R8-1')

    def test_equal_sequences_not_classes(self):
        rows=[dict(sequence=s,weighted=-1 if c=='C' else 1,Y=0,U=0,V=0) for s,(c,_) in SEQUENCES.items()]
        self.assertAlmostEqual(summarize(rows)['mean'],-1/7)
        with self.assertRaises(ValueError): summarize(rows+rows[:1])

    def test_factorial_separable_log_rates(self):
        base=[[100*math.exp(i),30+2*i,35+i,32+1.5*i] for i in (3,2,1,0)]
        scale=lambda k:[[r*k,y,u,v] for r,y,u,v in base]
        d=factorial(base,scale(.97),scale(1.02),scale(.97*1.02))
        self.assertAlmostEqual(d['interaction_log_pp_weighted'],0,places=10)
        self.assertAlmostEqual(d['sparse_with_second_weighted'],2,places=9)
        self.assertAlmostEqual(d['second_with_sparse_weighted'],-3,places=9)
        e=factorial(base,scale(.97),scale(1.02),scale(.97*1.02*.99))
        self.assertAlmostEqual(e['interaction_log_pp_weighted'],100*math.log(.99),places=9)

    def test_factorial_rejects_no_common_quality(self):
        base=[[100*math.exp(i),30+i,35+i,32+i] for i in (3,2,1,0)]
        other=[[r,y+10,u+10,v+10] for r,y,u,v in base]
        with self.assertRaises(ValueError): factorial(base,base,base,other)


if __name__=='__main__': unittest.main()
