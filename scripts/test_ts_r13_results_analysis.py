"""Pure data tests: no codec process, workbook write, or real experiment execution."""
import copy
import contextlib
import csv
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

import ts_r13_results_analysis as analysis


def rows_fixture():
    result = []
    for experiment, mode in analysis.MODES.items():
        for sequence in analysis.SEQS:
            for index, qp in enumerate(analysis.QPS):
                r = dict(experiment=experiment, mode=mode, sequence=sequence,
                         configuration='LB', class_name=analysis.SEQUENCES[sequence][0],
                         qp=str(qp), status='measured', anchor_record_status='pass',
                         test_record_status='pass', source_file='synthetic-test.xlsm',
                         anchor_file='synthetic-current.xlsm')
                for prefix, ratio in (('anchor_', 1), ('test_', .9)):
                    r[prefix + 'rate_kbps'] = str(math.exp(10 - index) * ratio)
                    for c in 'yuv':
                        r[prefix + 'psnr_' + c + '_db'] = str(45 - index * 3)
                result.append(r)
    return result


class R13AnalysisTests(unittest.TestCase):
    def test_whitelist_and_complete_current(self):
        rows = rows_fixture()
        extra = copy.deepcopy(rows[0])
        extra.update(sequence='BQTerrace', class_name='B', status='missing')
        rows.append(extra)
        self.assertEqual(len(analysis.select_rows(rows)), 168)
        for mutation in ('missing', 'duplicate', 'imputed', 'anchor', 'mode'):
            with self.subTest(mutation=mutation):
                broken = rows_fixture()
                if mutation == 'missing':
                    broken.pop()
                elif mutation == 'duplicate':
                    broken.append(copy.deepcopy(broken[0]))
                elif mutation == 'imputed':
                    broken[0]['status'] = 'anchor_imputed'
                elif mutation == 'anchor':
                    broken[0]['anchor_psnr_y_db'] = '45.001'
                else:
                    broken[0]['mode'] = 'nopred'
                with self.assertRaises(ValueError):
                    analysis.select_rows(broken)

    def test_halves_keep_original_four_point_fit(self):
        a = [(math.exp(i), 30 + 2 * i, 31 + 2 * i, 32 + 2 * i) for i in range(4)]
        b = [(p[0] * .9, *p[1:]) for p in a]
        halves = analysis.quality_halves(a, b)
        for row in halves:
            for c in analysis.COMPONENTS:
                self.assertAlmostEqual(row[c], -10, places=10)
        for c in 'YUV':
            self.assertEqual(halves[0][c + '_high_db'], halves[1][c + '_low_db'])

    def test_distribution_seed_percentiles_and_loo(self):
        d = analysis.distribution([-1, 0, 1], count=200)
        self.assertEqual(d, analysis.distribution([-1, 0, 1], count=200))
        self.assertEqual(d['mean'], 0)
        self.assertEqual(d['stddev'], 1)
        self.assertAlmostEqual(d['p10'], -.8)
        self.assertAlmostEqual(d['p90'], .8)
        self.assertEqual((d['loo_mean_min'], d['loo_mean_max']), (-.5, .5))

    def test_output_populations_and_direct_pairing(self):
        tables = analysis.analyze(analysis.select_rows(rows_fixture()), 20)
        self.assertEqual(len(tables['by_sequence']), 42)
        self.assertEqual(len(tables['paired_by_sequence']), 63)
        self.assertEqual(len(tables['qp_delta_by_sequence']), 420)
        self.assertEqual(len(tables['quality_halves_by_sequence']), 210)
        for row in tables['by_sequence']:
            self.assertAlmostEqual(row['weighted'], -10)
        for row in tables['paired_by_sequence']:
            self.assertAlmostEqual(row['weighted'], 0)
        for row in tables['qp_delta_by_sequence']:
            self.assertEqual(row['Y_delta_db'], 0)
            self.assertAlmostEqual(row['rate_delta_pct'], -10 if row['reference'] == 'Current' else 0)

    def test_source_hash_audit_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / 'by_sequence.csv'
            rows = rows_fixture()
            with ledger.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            source_names = ('synthetic-test.xlsm', 'synthetic-current.xlsm')
            for name in source_names:
                (root / name).write_bytes(b'opaque provenance fixture, not a real workbook')
            sources = root / 'sources.json'
            sources.write_text(json.dumps({'sources': [
                dict(path=name, sha256=analysis.digest(root / name)) for name in source_names]}))
            protected = [ledger, sources, *(root / name for name in source_names)]
            original = {path: path.read_bytes() for path in protected}
            args = ['--input', str(ledger), '--sources', str(sources), '--root', str(root),
                    '--bootstrap', '20', '--out']
            with contextlib.redirect_stdout(io.StringIO()):
                analysis.main(args + [str(root / 'derived')])
            audit = json.loads((root / 'derived/audit.json').read_text())
            self.assertEqual(audit['selected_points'], 168)
            self.assertTrue(audit['sources_unchanged'])
            self.assertEqual(audit['bootstrap']['seed'], analysis.SEED)
            self.assertEqual({path: path.read_bytes() for path in protected}, original)
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                analysis.main(args + [str(root)])
            self.assertEqual(ledger.read_bytes(), original[ledger])
            (root / source_names[0]).write_bytes(b'changed source')
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                analysis.main(args + [str(root / 'derived')])


if __name__ == '__main__':
    unittest.main()
