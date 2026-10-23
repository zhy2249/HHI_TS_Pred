"""R13 exact keep/hit model and independent production reference; no video I/O.

Run: python3 -m unittest discover -s scripts -p 'test_ts_r13_predictor.py'
This compiles only the standalone predictor probe, not EncoderApp/DecoderApp.
"""
from fractions import Fraction as F
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RHO = F(21, 2)


def positive_linear_integral(slope, intercept, left, right):
    """Integrate max(0, slope*x + intercept), independently of F/V formulas."""
    cuts = [F(left), F(right)]
    if slope:
        crossing = -F(intercept) / slope
        if left < crossing < right:
            cuts.append(crossing)
    cuts.sort()
    value = F(0)
    for lo, hi in zip(cuts, cuts[1:]):
        if slope * (lo + hi) / 2 + intercept > 0:
            value += slope * (hi * hi - lo * lo) / 2 + intercept * (hi - lo)
    return value


def integral_loss(m, p, cost):
    if p <= 1:
        return 168 * cost(m)
    if p == m:
        return 168
    if p == m - 1:
        c = cost(m)
        return 168 * (c - positive_linear_integral(-2 * RHO, c - 1 - RHO, F(-1, 2), F(1, 2)))
    if p == m + 1:
        c = cost(m + 1)
        return 168 * (c - positive_linear_integral(2 * RHO, c - 1 - RHO, F(0), F(1, 2)))
    return 168 * cost(m + (p > m))


def syntax_cost(magnitude, rice=1, dynamic_range=15):
    if magnitude < 2:
        return magnitude
    cost = 2 + sum(magnitude >= boundary for boundary in (2, 4, 6, 8))
    if magnitude < 10:
        return cost
    value = (magnitude - 10) // 2
    cutoff = 5
    if value < cutoff * (1 << rice):
        return cost + (value >> rice) + 1 + rice
    cap = 32 - cutoff - dynamic_range
    code = (value >> rice) - cutoff
    if code >= (1 << cap) - 1:
        return cost + cutoff + cap + dynamic_range
    prefix = 0
    while code + 2 > 1 << (prefix + 1):
        prefix += 1
    return cost + cutoff + 2 * prefix + rice + 1


class R13Predictor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ts-r13-predictor-")
        cls.exe = Path(cls.tmp.name) / "probe"
        result = subprocess.run(
            ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-Isource/Lib",
             "scripts/ts_r13_predictor_test.cpp", "-o", str(cls.exe)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode:
            cls.tmp.cleanup()
            raise RuntimeError("R13 predictor probe compilation failed:\n" + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def probe(self, action):
        result = subprocess.run([str(self.exe), action], check=True, capture_output=True, text=True, timeout=120)
        return json.loads(result.stdout)

    def query(self, inputs):
        text = "".join(" ".join(map(str, (mode, rice, span, *h))) + "\n" for mode, rice, span, h in inputs)
        result = subprocess.run([str(self.exe), "query"], input=text, check=True, capture_output=True, text=True)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_exact_fraction_integrals_and_breakpoints(self):
        table = [0, 168, 332, 488, 636, 776, 908, 1032, 1148, 1256, 1356, 1448,
                 1532, 1608, 1676, 1736, 1788, 1832, 1868, 1896, 1916, 1928, 1932]
        result = subprocess.run([str(self.exe), "table"], check=True, capture_output=True, text=True)
        actual = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(actual), 512)
        for c in range(1, 513):
            with self.subTest(c=c):
                down = 168 * (c - positive_linear_integral(-2 * RHO, c - 1 - RHO, F(-1, 2), F(1, 2)))
                up = 168 * (c - positive_linear_integral(2 * RHO, c - 1 - RHO, F(0), F(1, 2)))
                self.assertEqual(down, table[c] if c <= 22 else 1932)
                self.assertEqual(up, table[c] if c <= 11 else 84 * c + 525)
                self.assertEqual(actual[c - 1], [c, down, up])
        # p=1 means identity even when it would also look like a down hit.
        self.assertEqual(integral_loss(2, 1, syntax_cost), 504)
        self.assertEqual(integral_loss(2, 0, syntax_cost), 504)

    def test_production_single_loss_against_independent_integral(self):
        inputs = [(m, p, rice, 15) for rice in range(1, 9) for m in range(1, 33) for p in range(34)]
        payload = "".join(" ".join(map(str, case)) + "\n" for case in inputs)
        result = subprocess.run([str(self.exe), "loss"], input=payload, check=True, capture_output=True, text=True)
        actual = [int(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(actual), 8704)
        for (m, p, rice, span), value in zip(inputs, actual):
            self.assertEqual(value, integral_loss(m, p, lambda t: syntax_cost(t, rice, span)), (m, p, rice, span))

    def test_exhaustive_support_sparse_ties_duplicates_and_identity(self):
        counts = self.probe("exhaustive")
        self.assertTrue(counts["pass"])
        self.assertEqual(counts["decisions"], 32768 * 4 * 2 * 2)
        for key in ("dense", "sparse", "ties", "old_new_disagree", "weighted_disagree"):
            self.assertGreater(counts[key], 0, key)

    def test_large_magnitudes_limited_escape_and_rice_ranges(self):
        counts = self.probe("random")
        self.assertTrue(counts["pass"])
        self.assertEqual(counts["decisions"], (20000 + 2 * 3125) * 2)

    def test_frozen_activity_examples(self):
        inputs = [
            (1, 1, 15, (4, 4, 3, 3, 3)),
            (2, 1, 15, (4, 4, 3, 3, 3)),
            (1, 1, 15, (4, 4, 8, 10, 9)),
            (1, 1, 15, (0, 0, 1, 2, 3)),
        ]
        rows = self.query(inputs)
        expected = [({0: 2856, 3: 1776, 4: 2244}, 3),
                    ({0: 4200, 3: 3048, 4: 2580}, 4),
                    ({0: 4704, 4: 3696, 8: 3764, 9: 3568, 10: 3668}, 9),
                    ({0: 1176, 2: 1144, 3: 1160}, 2)]
        for row, (scores, winner) in zip(rows, expected):
            self.assertEqual(dict(zip(row["candidates"], row["scores"])), scores)
            self.assertEqual(row["predictor"], winner)

    def test_independent_integral_scores_across_sparse_and_boundaries(self):
        neighborhoods = [
            (0, 0, 0, 0, 0), (1, 0, 0, 0, 0), (0, 1, 0, 8, 0),
            (0, 0, 1, 2, 3), (1, 1, 1, 1, 1), (2, 2, 2, 2, 2),
            (0, 4, 3, 3, 3), (4, 0, 3, 3, 3), (4, 4, 8, 10, 9),
            (32768, 32767, 1, 2, 32768), (32768, 0, 0, 0, 0),
        ]
        inputs = [(mode, rice, 15, h) for mode in (1, 2) for rice in (0, 1, 4, 8) for h in neighborhoods]
        for case, row in zip(inputs, self.query(inputs)):
            mode, rice, span, h = case
            weights = (1, 1, 1, 1, 1) if mode == 1 else (2, 2, 1, 1, 1)
            self.assertEqual(row["weight_sum"], sum(w for m, w in zip(h, weights) if m))
            if sum(bool(m) for m in h) < 3:
                self.assertFalse(row["scored"])
                self.assertEqual(row["predictor"], max(h[:2]))
                self.assertEqual(row["second"], -1)
                continue
            cost = lambda value: syntax_cost(value, rice, span)
            expected = [sum(w * integral_loss(m, p, cost) for m, w in zip(h, weights) if m)
                        for p in row["candidates"]]
            self.assertEqual(row["scores"], expected, case)
            self.assertEqual(row["predictor"], row["candidates"][expected.index(min(expected))])


if __name__ == "__main__":
    unittest.main()
