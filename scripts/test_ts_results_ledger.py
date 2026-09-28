import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from ts_fixed_analyze import QPS
from ts_results_ledger import (BD, METRICS, R9_MODES, catalog, csv_sources, csv_text, imputation_allowed,
                               point_values, read_sheet, sequence_result)


def curve(scale=1):
    rows = []
    for qp, i in zip(QPS, (3, 2, 1, 0)):
        anchor = [100 * 2**i, 30 + 2*i, 32 + i, 33 + 3*i]
        test = [anchor[0] * scale, *anchor[1:]]
        rows.append(dict(qp=qp, status='measured', anchor_record_status='pass',
                         **dict(zip(('anchor_' + k for k in METRICS), anchor)),
                         **dict(zip(('test_' + k for k in METRICS), test))))
    return rows


class ResultsLedgerTests(unittest.TestCase):
    def test_r9_registration_preserves_mode_numbering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            r8 = root / 'experiments/ts_predictor_r8'
            r8.mkdir(parents=True)
            for i in range(1, 25):
                (r8 / f'R8_{i}_JVET-hhi.xlsm').touch()
            specs = [s for s in catalog(root) if s['round'] == 'r9']
        self.assertEqual(len(specs), 13)
        self.assertEqual(len(set(R9_MODES)), 13)
        self.assertEqual([s['experiment'] for s in specs], [f'R9-{i}' for i in range(1, 14)])
        self.assertEqual(specs[0]['mode'], 'r9_p10')
        self.assertEqual(specs[10]['mode'], 'r9_quant_down')
        self.assertEqual(specs[11]['mode'], 'r9_quant_down_up')
        self.assertEqual(specs[12]['mode'], 'r9_axis_feature')
        self.assertTrue(all(s['expected_lb'] == 'CE' for s in specs))

    def test_r9_numbered_csv_pairing(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            for name in ('1.csv', '2.csv', '10.csv', '11.csv', '13.csv'):
                (p / name).touch()
            for i in (1, 11, 13):
                self.assertEqual([x.name for x in csv_sources(dict(round='r9', experiment=f'R9-{i}'), p/f'R9_{i}_JVET-hhi.xlsm')],
                                 [f'{i}.csv'])
            self.assertEqual(csv_sources(dict(round='r9', experiment='R9-3'), p/'R9_3_JVET-hhi.xlsm'), [])

    def test_r9_missing_points_are_not_imputed(self):
        for i in range(1, 14):
            self.assertFalse(imputation_allowed(f'R9-{i}', 'lb', 'PartyScene', 22))

    def test_shared_folder_pairing_does_not_mix_experiments(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            for name in ('R6_1.csv', 'R6_2.csv', 'R6_2_B.csv', 'R6_20.csv', 'R6_3.csv'):
                (p / name).touch()
            self.assertEqual([x.name for x in csv_sources(dict(round='r6', experiment='R6-2'), p/'R6_2_JVET-hhi.xlsm')],
                             ['R6_2.csv', 'R6_2_B.csv'])

    def test_historical_imputation_is_narrow(self):
        self.assertTrue(imputation_allowed('R8-23', 'lb', 'PartyScene', 22))
        for args in [('R8-23', 'ra', 'PartyScene', 22), ('R8-1', 'lb', 'PartyScene', 22),
                     ('R8-23', 'lb', 'PartyScene', 27), ('R8-23', 'lb', 'BQMall', 22)]:
            self.assertFalse(imputation_allowed(*args))

    def test_measured_supersedes_imputation(self):
        a, t = [100, 30, 31, 32], [99, 30.1, 31.1, 32.1]
        self.assertEqual(point_values('R2-4', 'lb', 'PartyScene', 22, t, a), (t, 'measured'))
        self.assertEqual(point_values('R2-4', 'lb', 'PartyScene', 22, a, a), (a, 'measured'))
        values, status = point_values('R2-4', 'lb', 'PartyScene', 22, None, a)
        self.assertEqual((values, status), (a, 'anchor_imputed'))
        self.assertIsNot(values, a)

    def test_unapproved_missing_stays_empty(self):
        self.assertEqual(point_values('R3-1', 'ra', 'MarketPlace', 22, None, [1, 2, 3, 4]),
                         (['']*4, 'missing'))

    def test_component_first_bd_and_anchor_identity(self):
        for factor, expected in ((1, 0), (.9, -10), (1.1, 10)):
            result = sequence_result(curve(factor))
            self.assertEqual(result['status'], 'complete')
            for key in BD:
                self.assertAlmostEqual(result[key], expected, places=10)
            self.assertLess(result['max_vba_gap_pp'], 1e-8)
        rows = curve(.98)
        for row in rows:
            row['test_psnr_u_db'] += .05
            row['test_psnr_v_db'] -= .1
        r = sequence_result(rows)
        self.assertAlmostEqual(r['bd_611_pct'], (6*r['bd_y_pct']+r['bd_u_pct']+r['bd_v_pct'])/8)
        self.assertNotEqual(r['bd_y_pct'], r['bd_u_pct'])

    def test_incomplete_curve_not_three_point_or_zero_bd(self):
        rows = curve()
        rows[1]['status'] = 'missing'
        for k in METRICS:
            rows[1]['test_' + k] = ''
        r = sequence_result(rows)
        self.assertEqual(r['status'], 'incomplete')
        self.assertEqual(r['missing_points'], 1)
        self.assertTrue(all(r[k] == '' for k in BD))

    def test_imputation_remains_visible(self):
        rows = curve()
        rows[0]['status'] = 'anchor_imputed'
        r = sequence_result(rows)
        self.assertEqual((r['status'], r['measured_points'], r['imputed_points']), ('imputed', 3, 1))
        self.assertEqual(r['bd_611_pct'], 0)

    def test_failed_reference_forbids_bd_but_keeps_values(self):
        rows = curve()
        rows[-1]['anchor_record_status'] = 'fail(md5 mismatch).'
        r = sequence_result(rows)
        self.assertEqual(r['status'], 'invalid_anchor')
        self.assertTrue(all(r[k] == '' for k in BD))
        self.assertEqual(rows[-1]['anchor_rate_kbps'], 100)

    def test_requires_four_unique_qps(self):
        with self.assertRaises(ValueError):
            sequence_result(curve()[:3])
        with self.assertRaises(ValueError):
            sequence_result(curve()[:3]+curve()[:1])

    def test_no_overlap_and_nonmonotonic_curves(self):
        rows = curve()
        for row in rows:
            row['test_psnr_y_db'] += 100
        self.assertEqual(sequence_result(rows)['status'], 'invalid')
        rows = curve()
        rows[1]['test_psnr_y_db'] = rows[0]['test_psnr_y_db']
        self.assertEqual(sequence_result(rows)['status'], 'invalid')

    def test_sheet_preserves_failed_status_for_later_screening(self):
        cells = {'A1': 'PartyScene.Q22.ecm.lb', 'B1': 100, 'C1': 30, 'D1': 31,
                 'E1': 32, 'J1': 'fail(md5 mismatch).', 'A2': 'PartyScene.Q27.ecm.lb'}
        with patch('ts_results_ledger.sheet_values', return_value=cells):
            values, locations, statuses = read_sheet(Path('unused.xlsm'), 'Reference')
        self.assertEqual(values['PartyScene.Q22.ecm.lb'], [100, 30, 31, 32])
        self.assertEqual(locations['PartyScene.Q22.ecm.lb'], 'Reference!B1:E1')
        self.assertEqual(statuses['PartyScene.Q22.ecm.lb'], 'fail(md5 mismatch).')
        self.assertNotIn('PartyScene.Q27.ecm.lb', values)

    def test_partial_and_duplicate_sheet_rows_rejected(self):
        for cells in ({'A1': 'PartyScene.Q22.ecm.lb', 'B1': 100},
                      {'A1': 'PartyScene.Q22.ecm.lb', 'A2': 'PartyScene.Q22.ecm.lb'}):
            with patch('ts_results_ledger.sheet_values', return_value=cells):
                with self.assertRaises(ValueError):
                    read_sheet(Path('unused.xlsm'), 'Test')

    def test_csv_units_and_empty_not_zero(self):
        result = csv_text([dict(test_rate_kbps='', bd_y_pct=0.0, status='missing')])
        self.assertEqual(result, 'test_rate_kbps,bd_y_pct,status\n,0.0,missing\n')


if __name__ == '__main__':
    unittest.main()
