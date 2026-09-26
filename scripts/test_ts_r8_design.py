import json
from pathlib import Path
import tempfile
import unittest

from ts_r8_design_check import (candidates, check_manifest, check_math,
                                regret_brute, regret_fast, smooth)
from ts_r8_first8_reference import FIRST8, PRIMARY, SPEC, select, verify_grid


class R8DesignTest(unittest.TestCase):
    def test_finite_domain_specification(self):
        result = check_math()
        self.assertEqual(result['original_multisets'], 1287)
        self.assertEqual(result['smoothed_multisets'], 1287)
        self.assertFalse(result['codec_verified'])

    def test_manifest_numbering_and_single_factor_pairs(self):
        path = Path(__file__).with_name('ts_r8_experiment_manifest.json')
        self.assertEqual(check_manifest(path), 24)

    def test_manifest_rejects_false_implementation_status(self):
        source = Path(__file__).with_name('ts_r8_experiment_manifest.json')
        data = json.loads(source.read_text())
        data['experiments'][1]['status'] = 'not_implemented'  # Registry must agree with the delivered code.
        with tempfile.TemporaryDirectory(prefix='ts-r8-design-') as tmp:
            path = Path(tmp) / 'manifest.json'
            path.write_text(json.dumps(data))
            with self.assertRaises(AssertionError):
                check_manifest(path)

    def test_zero_one_and_upper_boundary(self):
        self.assertEqual(candidates([0, 1, 1], 8), [0, 2])
        self.assertEqual(candidates([8], 8), [0, 8])
        self.assertEqual(smooth([1], 8), {0: 1, 1: 2, 2: 1})
        self.assertEqual(smooth([8], 8), {7: 1, 8: 3})

    def test_minimax_keeps_candidate_set_in_each_scenario(self):
        loss = [[0, 9, 1], [3, 3, 3], [9, 0, 1]]
        self.assertEqual(regret_fast(loss), regret_brute(loss))
        self.assertEqual(regret_fast(loss), [9, 5, 9])

    def test_first8_reference_matches_manifest(self):
        path = Path(__file__).with_name('ts_r8_experiment_manifest.json')
        manifest = json.loads(path.read_text())
        rows = manifest['experiments']
        ids = {r['mode']: r['id'] for r in rows}
        for row in rows:
            if row['mode'] in FIRST8:
                self.assertEqual(tuple(row[f] for f in ('cost', 'samples', 'candidates', 'decision', 'sparse')),
                                 SPEC[row['mode']])
                parent = PRIMARY[row['mode']]
                self.assertEqual(manifest['first_batch_primary_controls'][row['id']], ids.get(parent, parent))

    def test_first8_rejects_missing_smoothing_control(self):
        source = Path(__file__).with_name('ts_r8_experiment_manifest.json')
        data = json.loads(source.read_text())
        data['first_batch'].remove('B04')
        with tempfile.TemporaryDirectory(prefix='ts-r8-first8-') as tmp:
            path = Path(tmp) / 'manifest.json'
            path.write_text(json.dumps(data))
            with self.assertRaises(AssertionError):
                check_manifest(path)

    def test_first8_all_formulas_on_synthetic_grid(self):
        result = verify_grid()
        self.assertEqual(result['reference_decisions'], 30720)
        self.assertTrue(all(r['remap_diff_targets'] > 0
                            for r in result['relative_to_primary_controls'].values()))
        self.assertFalse(result['ctc_activity_measured'])

    def test_first8_sparse_and_guard_reject_rules(self):
        ci = tuple(v << 15 for v in (0, 1, 3, 3, 4, 4, 5, 5, 6))
        for mode in FIRST8:
            d = select(mode, (3, 0, 0, 0, 0), ci, ci, 8)
            self.assertEqual(d.predictor, 3 if mode in (8, 15) else 0)
            self.assertEqual(select(mode, (3, 2, 0, 0, 0), ci, ci, 8).predictor, 3)
        d = select(8, (3, 1, 1, 0, 0), ci, ci, 8)
        self.assertEqual((d.raw_winner, d.raw_gain, d.raw_margin, d.predictor), (0, 2 << 15, 0, 0))
        self.assertEqual(select('R7-2', (3, 1, 1, 0, 0), ci, ci, 8).predictor, 3)
        self.assertEqual(select(8, (3, 3, 3, 0, 0), ci, ci, 8).predictor, 3)

    def test_first8_expanded_candidate_can_win_without_hit(self):
        costs = tuple(v << 15 for v in (0, 3, 8, 9, 1, 8, 8, 8, 8))
        neighbours = (3, 3, 3, 0, 0)
        self.assertEqual(select('R7-1', neighbours, costs, costs, 8).predictor, 3)
        self.assertEqual(select(15, neighbours, costs, costs, 8).predictor, 4)
        with self.assertRaises(ValueError):
            select(2, neighbours, costs, costs, 8)


if __name__ == '__main__':
    unittest.main()
