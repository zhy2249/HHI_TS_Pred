"""Exact R12 engineering path vs preserved production formulas; no video I/O.

Run: python3 -m unittest discover -s scripts -p 'test_ts_r12_exact_formula.py'
Optional microbenchmark (not an encoder timing claim):
  g++ -std=c++17 -O2 -Isource/Lib scripts/ts_r12_exact_probe.cpp -o /tmp/ts_r12_exact_probe
  /tmp/ts_r12_exact_probe --benchmark
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class R12ExactFormula(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="ts-r12-exact-formula-")
        cls.executable = Path(cls.temporary.name) / "probe"
        result = subprocess.run(
            ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-isystem", "source/Lib",
             "scripts/ts_r12_exact_probe.cpp", "-o", str(cls.executable)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode:
            raise RuntimeError("R12 exact formula probe compilation failed:\n" + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_probe(self, task, expected):
        result = subprocess.run(
            [str(self.executable), task], cwd=ROOT,
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["pass"])
        self.assertEqual(data["task"], task)
        self.assertEqual(data["comparisons"], expected)

    def test_small_exhaustive_all_modes_and_ties(self):
        self.run_probe("--experts-small", 7776 * 13 * 3)

    def test_nonmonotone_64bit_costs_and_extreme_magnitudes(self):
        self.run_probe("--experts-random", (20000 + 3125) * 13)

    def test_random_selectors_and_exact_lazy_callback_masks(self):
        self.run_probe("--selectors-random", 16000 * 13)

    def test_prespecified_selector_boundaries(self):
        self.run_probe("--selectors-edges", 46)


if __name__ == "__main__":
    unittest.main()
