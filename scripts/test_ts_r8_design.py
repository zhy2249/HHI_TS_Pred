import json
from pathlib import Path
import tempfile
import unittest

from ts_r8_design_check import (candidates, check_manifest, check_math,
                                regret_brute, regret_fast, smooth)


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
        data['experiments'][0]['status'] = 'implemented'
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


if __name__ == '__main__':
    unittest.main()
