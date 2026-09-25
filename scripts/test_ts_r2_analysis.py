#!/usr/bin/env python3
"""Synthetic curves only: integration order, missing-point refusal and reference protection."""
import csv
import io
import json
import math
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ts_r2_analyze as analysis
from ts_predictor_naming import directory_name


class R2AnalysisTests(unittest.TestCase):
    def run_case(self, missing=False, corrupt=False, revision='r2', legacy=False, flat=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mode = {'r2':'r2_modal','r3':'r3_risk_guard','r4':'r4_causal_models','r5':'r5_current_veto','r6':'r6_trim_saving'}[revision]
            folder = root / (mode if legacy else directory_name(mode))
            workbook = (folder if flat else folder/'LB_CE')/'JVET-hhi.xlsm'
            workbook.parent.mkdir(parents=True)
            workbook.touch()
            anchor = root/'anchor.xlsm'
            anchor.touch()
            current, test = {}, {}
            for seq in ('a','b','c','d'):
                for i, qp in enumerate(analysis.QPS):
                    key = f'{seq}.Q{qp}.ecm.lb'
                    row = [math.exp(8-i*.4), 44-i*2, 46-i*2.2, 45-i*1.8]
                    current[key] = (row, 'pass')
                    # Different component shifts ensure weighting PSNR first is not substituted.
                    test[key] = ([row[0]*.99, row[1]+.02, row[2]-.1, row[3]+.3], 'pass')
            if missing:
                del test['a.Q22.ecm.lb']
            def reader(path, sheet):
                if sheet == 'Test':
                    return test
                return {} if corrupt and path == workbook else current
            args = ['ts_r2_analyze.py','--revision',revision,'--run',str(root),'--modes',mode,'--anchor',str(anchor),
                    '--out',str(root/'out')]
            with patch('sys.argv', args), patch.object(analysis, 'points', side_effect=reader), \
                 patch.object(analysis, 'CLASSES', {'a':'C','b':'C','c':'E','d':'E'}), redirect_stdout(io.StringIO()):
                if corrupt:
                    with self.assertRaisesRegex(ValueError, 'Current anchor'):
                        analysis.main()
                    return
                if missing:
                    with self.assertRaises(SystemExit):
                        analysis.main()
                else:
                    analysis.main()
            audit = json.loads((root/'out/audit.json').read_text())
            self.assertEqual(audit['imputed_points'], 0)
            self.assertEqual(audit['anchor_predictor'], 'current')
            with (root/'out/by_sequence.csv').open() as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 3 if missing else 4)
            for row in rows:
                expected = (6*float(row['Y_pchip']) + float(row['U_pchip']) + float(row['V_pchip']))/8
                self.assertAlmostEqual(float(row['weighted_pchip']), expected, places=12)
            with (root/'out/summary.csv').open() as source:
                summaries = list(csv.DictReader(source))
            self.assertEqual(len(summaries), 1 if missing else 3)

    def test_weight_components_after_bdrate(self):
        self.run_case()

    def test_no_missing_qp_imputation(self):
        self.run_case(missing=True)

    def test_current_reference_protection(self):
        self.run_case(corrupt=True)

    def test_r3_weighting(self):
        self.run_case(revision='r3')

    def test_r3_missing(self):
        self.run_case(missing=True, revision='r3')

    def test_r3_reference(self):
        self.run_case(corrupt=True, revision='r3')

    def test_r4_weighting(self):
        self.run_case(revision='r4')

    def test_r4_missing(self):
        self.run_case(missing=True, revision='r4')

    def test_r4_reference(self):
        self.run_case(corrupt=True, revision='r4')

    def test_r4_legacy_directory(self):
        self.run_case(revision='r4', legacy=True)

    def test_r4_numbered_batch_directory(self):
        self.run_case(revision='r4', flat=True)

    def test_r5_numbered_weighting(self):
        self.run_case(revision='r5')

    def test_r5_missing(self):
        self.run_case(missing=True, revision='r5')

    def test_r5_reference(self):
        self.run_case(corrupt=True, revision='r5')

    def test_r5_flat(self):
        self.run_case(revision='r5', flat=True)

    def test_r6_numbered_weighting(self):
        self.run_case(revision='r6')

    def test_r6_missing(self):
        self.run_case(missing=True, revision='r6')

    def test_r6_reference(self):
        self.run_case(corrupt=True, revision='r6')

    def test_r6_flat(self):
        self.run_case(revision='r6', flat=True)


if __name__ == '__main__':
    unittest.main()
