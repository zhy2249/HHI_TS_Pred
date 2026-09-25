import math
import unittest
from ts_r3_results_analysis import common_bands


class CommonBandTests(unittest.TestCase):
    def setUp(self):
        self.a = [[100*math.exp(i),30+2*i,35+i,32+1.5*i] for i in (3,2,1,0)]

    def test_identity(self):
        for row in common_bands(self.a,self.a,self.a):
            for key in ('parent_weighted','test_weighted','direct_weighted','delta_weighted_pp'):
                self.assertEqual(row[key],0)

    def test_scaling_and_delta_not_direct_bd(self):
        p = [[r*.98,y,u,v] for r,y,u,v in self.a]
        t = [[r*.97,y,u,v] for r,y,u,v in self.a]
        for row in common_bands(self.a,p,t):
            self.assertAlmostEqual(row['parent_weighted'],-2,places=9)
            self.assertAlmostEqual(row['test_weighted'],-3,places=9)
            self.assertAlmostEqual(row['delta_weighted_pp'],-1,places=9)
            self.assertAlmostEqual(row['direct_weighted'],100*(.97/.98-1),places=9)

    def test_common_clipping_and_component_weight(self):
        p = [[r,y+.1,u+.2,v-.1] for r,y,u,v in self.a]
        t = [[r,y-.2,u+.1,v+.3] for r,y,u,v in self.a]
        rows = common_bands(self.a,p,t)
        self.assertAlmostEqual(rows[0]['Y_low_db'],30.1)
        self.assertAlmostEqual(rows[-1]['Y_high_db'],35.8)
        for row in rows:
            for key in ('parent','test','direct'):
                expected = (6*row[key+'_Y']+row[key+'_U']+row[key+'_V'])/8
                self.assertEqual(row[key+'_weighted'],expected)


if __name__=='__main__':
    unittest.main()
