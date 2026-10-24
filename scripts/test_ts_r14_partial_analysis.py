#!/usr/bin/env python3
"""Checks for partial-data safeguards, not codec tests."""
import csv
from pathlib import Path
import tempfile
import unittest

import ts_r14_partial_analysis as analysis


class PartialR14Tests(unittest.TestCase):
    def write_rows(self, rows):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'results.csv'
        with path.open('w', newline='') as stream:
            csv.writer(stream).writerows(rows)
        return path

    def row(self, status='pass'):
        return ['Johnny.Q27.ecm.lb', '100.1', '40.1', '42.2', '43.3', '', '', '', '', status, '2026-10-24']

    def test_pass_column_and_empty_template(self):
        rows = [['Johnny.Q22.ecm.lb', '', '', '', ''], self.row()]
        points, issues, _ = analysis.read_results(self.write_rows(rows))
        self.assertEqual(issues, [])
        self.assertEqual(set(points), {('Johnny', 27)})

    def test_bad_status_and_duplicate_rejected(self):
        points, issues, _ = analysis.read_results(self.write_rows([self.row('fail'), self.row()]))
        self.assertFalse(points)
        self.assertEqual(len(issues), 2)
        self.assertIn('status', issues[0])
        self.assertIn('duplicate', issues[1])

    def test_bd3_known_rate_scaling_and_no_imputation(self):
        anchor = {qp: (1000 / 2**i, 40-i*4, 43-i*3, 45-i*2) for i, qp in enumerate((27, 32, 37))}
        test = {qp: (rd[0]*.9, *rd[1:]) for qp, rd in anchor.items()}
        for result in analysis.bd3(anchor, test):
            self.assertAlmostEqual(result, -10, places=9)
        del test[27]
        with self.assertRaises(ValueError):
            analysis.bd3(anchor, test)

    def test_rd_equality_includes_every_component(self):
        key = ('Johnny', 27)
        reference = {key: (100, 40, 42, 43)}
        for value in ((99, 40, 42, 43), (100, 40, 42, 43.001)):
            row = analysis.compare({key: value}, reference, 'test', 'reference', 'test')[0]
            self.assertEqual(row['rd_tuple_equal'], 0)


if __name__ == '__main__':
    unittest.main()
