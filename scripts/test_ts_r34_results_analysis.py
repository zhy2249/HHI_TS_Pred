import csv
from pathlib import Path
import tempfile
import unittest

from ts_r34_results_analysis import csv_points, groups, measured_three_point, resolve_point
from ts_predictor_cross_round_analysis import compare, weighted


class R34AnalysisTest(unittest.TestCase):
    def setUp(self):
        self.key = 'MarketPlace.Q22.ecm.lb'
        self.anchor = {self.key: ([100,30,31,32], 'pass')}

    def test_imputation_requires_explicit_opt_in(self):
        with self.assertRaises(ValueError):
            resolve_point('r3_risk_guard','MarketPlace',22,{},self.anchor)
        value, filled = resolve_point('r3_risk_guard','MarketPlace',22,{},self.anchor,True)
        self.assertTrue(filled)
        self.assertEqual(value,self.anchor[self.key][0])
        value[0]=1
        self.assertEqual(self.anchor[self.key][0][0],100)

    def test_never_overwrite_measured_qp22(self):
        point=([99,30,31,32],'pass')
        value,filled=resolve_point('r3_risk_guard_y','MarketPlace',22,{self.key:point},self.anchor,True)
        self.assertEqual(value,point[0]); self.assertFalse(filled)

    def test_no_other_missing_points_filled(self):
        for mode,seq,qp in [('r4_identity_only','MarketPlace',22),
                            ('r3_risk_guard','MarketPlace',27),
                            ('r3_risk_guard','BQMall',22),
                            ('nopred','MarketPlace',22)]:
            anchor={f'{seq}.Q{qp}.ecm.lb':([100,30,31,32],'pass')}
            with self.subTest(mode=mode,seq=seq,qp=qp), self.assertRaises(ValueError):
                resolve_point(mode,seq,qp,{},anchor,True)

    def test_failed_measured_point_not_filled(self):
        with self.assertRaises(ValueError):
            resolve_point('r3_risk_guard','MarketPlace',22,
                          {self.key:([100,30,31,32],'fail')},self.anchor,True)

    def test_csv_template_and_header_not_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data.csv'
            with path.open('w',newline='') as f:
                csv.writer(f).writerows([['sequence','kbps','Y','U','V'],[self.key],
                    ['MarketPlace.Q27.ecm.lb',100,30,31,32,1,1,1,1,'pass']])
            self.assertEqual(len(csv_points(path)),1)

    def test_csv_partial_or_failed_or_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data.csv'
            for rows in [[[self.key,100]],[[self.key,100,30,31,32,1,1,1,1,'fail']],
                         [[self.key],[self.key]]]:
                with path.open('w',newline='') as f:
                    csv.writer(f).writerows(rows)
                with self.subTest(rows=rows),self.assertRaises(ValueError):
                    csv_points(path)

    def test_three_point_scale_and_identity(self):
        a=[[100,30,31,32],[200,35,36,37],[400,40,41,42]]
        t=[[p[0]*.999,*p[1:]] for p in a]
        self.assertAlmostEqual(measured_three_point(a,t)['weighted'],-.1,places=9)
        self.assertAlmostEqual(measured_three_point(a,a)['weighted'],0,places=12)
        with self.assertRaises(ValueError):
            measured_three_point(a[:2],t[:2])

    def test_component_first_weighting(self):
        a=[[100,30,31,32],[200,33,36,38],[400,36,41,44],[800,39,46,50]]
        t=[[p[0]*.999,p[1]+.01,p[2]+.05,p[3]-.01] for p in a]
        result=compare(a,t)
        self.assertEqual(result['weighted'],weighted([result[c] for c in 'YUV']))
        self.assertAlmostEqual(result['weighted'],(6*result['Y']+result['U']+result['V'])/8)

    def test_missing_sequence_cannot_become_complete_class_mean(self):
        rr=[dict(sequence='MarketPlace',**{'class':'B'})]
        self.assertEqual(list(groups(rr)),[])


if __name__=='__main__':
    unittest.main()
