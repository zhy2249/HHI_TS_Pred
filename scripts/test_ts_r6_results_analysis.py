import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ts_r6_results_analysis import check_columns, csv_columns, required_points, summarize
from ts_fixed_analyze import QPS, SEQUENCES
from ts_predictor_cross_round_analysis import compare, weighted


class R6AnalysisTests(unittest.TestCase):
    def test_missing_never_imputed(self):
        with self.assertRaisesRegex(ValueError, 'imputation forbidden'):
            required_points({}, ['BasketballDrill'])

    def test_failed_and_nonfinite_rejected(self):
        d = {f'BasketballDrill.Q{q}.ecm.lb': ([100, 30, 31, 32], 'pass') for q in QPS}
        self.assertEqual(len(required_points(d, ['BasketballDrill'])), 4)
        for value in (([100,30,31,32], 'fail'), ([float('nan'),30,31,32], 'pass')):
            d['BasketballDrill.Q22.ecm.lb'] = value
            with self.assertRaises(ValueError):
                required_points(d, ['BasketballDrill'])

    def test_sequence_not_class_weight(self):
        rows = [dict(sequence=s, weighted=-1 if c=='C' else 1, Y=0,U=0,V=0)
                for s,(c,_) in SEQUENCES.items()]
        self.assertAlmostEqual(summarize(rows)['mean'], -1/7)
        with self.assertRaises(ValueError):
            summarize(rows+rows[:1])

    def test_components_then_weight_and_direct_comparison(self):
        a = [[100*math.exp(i), 30+2*i,35+i,32+1.5*i] for i in (3,2,1,0)]
        p = [[r*.98,y,u,v] for r,y,u,v in a]
        t = [[r*.97,y,u,v] for r,y,u,v in a]
        self.assertAlmostEqual(compare(p,t)['weighted'], 100*(.97/.98-1), places=9)
        self.assertNotAlmostEqual(compare(p,t)['weighted'], compare(a,t)['weighted']-compare(a,p)['weighted'])
        self.assertAlmostEqual(weighted([-1,2,3]), -.125)

    def test_csv_rejects_partial_failed_duplicate(self):
        key = 'BasketballDrill.Q22.ecm.lb'
        valid = key+',100,30,31,32,10,1,1000,200,pass\n'
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'input.csv'
            for content in (key+',100\n', valid.replace('pass','fail'), valid+valid):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    csv_columns(path)
            path.write_text('BasketballDrill.Q27.ecm.lb\n'+valid)
            self.assertEqual(len(csv_columns(path)), 1)

    def test_workbook_csv_checks_timing_and_scope_too(self):
        key = 'BasketballDrill.Q22.ecm.lb'
        cells = dict(zip(('A1','B1','C1','D1','E1','F1','G1','H1','I1','J1'),
                         (key,100,30,31,32,10,1,1000,200,'pass')))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'input.csv'
            path.write_text(key+',100,30,31,32,10,1,1000,200,pass\n')
            with patch('ts_r6_results_analysis.sheet_values', return_value=cells):
                check_columns(Path('unused.xlsm'), [path], {key})
                cells['F1'] = 11
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    check_columns(Path('unused.xlsm'), [path], {key})
                with self.assertRaisesRegex(ValueError, 'Overlapping'):
                    check_columns(Path('unused.xlsm'), [path, path], {key})


if __name__ == '__main__':
    unittest.main()
