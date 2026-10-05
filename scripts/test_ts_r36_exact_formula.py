"""Pure R3/R6 exact-optimization checks; no video encoding or decoding."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class R36ExactFormula(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ts-r36-exact-formula-")
        cls.exe = Path(cls.tmp.name) / "probe"
        subprocess.run(
            ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
             "-Isource/Lib", "scripts/ts_r36_exact_probe.cpp", "-o", str(cls.exe)],
            cwd=ROOT, check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def probe(self, action):
        result = subprocess.run(
            [str(self.exe), action], check=True, capture_output=True, text=True,
            timeout=90,
        )
        return json.loads(result.stdout)

    def test_exhaustive_small_support_and_branch_witnesses(self):
        counts = self.probe("exhaustive")
        self.assertEqual(counts["patterns"], 8 ** 5)
        self.assertEqual(counts["guards"], 8 ** 5)
        self.assertEqual(counts["predictors"], 9 * 8 ** 5)
        for name in (
            "sparse_current_one", "dense_canonical_zero", "guard_accepted",
            "identity_rejected", "nonzero_rejected", "duplicate_accepted",
            "raw_tie_current", "tie_current_retained", "rejection_fallback",
        ):
            with self.subTest(witness=name):
                self.assertGreater(counts[name], 0)

    def test_random_extremes_and_rice_range_pairs(self):
        counts = self.probe("random")
        # With the codec's Rice cutoff=5, 45 +/-2 samples around the capped
        # escape transition are reachable inside these two legal ranges.
        expected = 40000 + 2 * 8 * 9 + 45
        self.assertEqual(counts["patterns"], expected)
        self.assertEqual(counts["guards"], expected)
        self.assertEqual(counts["predictors"], 9 * expected)

    def test_guard_complete_fields_with_independent_current(self):
        counts = self.probe("guards")
        self.assertEqual(counts["guards"], 80006)
        self.assertGreater(counts["sparse_current_one"], 0)
        self.assertGreater(counts["dense_canonical_zero"], 0)


if __name__ == "__main__":
    unittest.main()
