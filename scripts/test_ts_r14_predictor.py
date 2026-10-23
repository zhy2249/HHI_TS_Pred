"""R14 production versus independent syntax/reference, no video I/O.

Run: python3 -m unittest discover -s scripts -p 'test_ts_r14_predictor.py'
"""
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "r14_design_reference", ROOT / "docs/experiments/reference/ts_r14_design_reference.py")
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference
spec.loader.exec_module(reference)

# Independent list (does not import production naming/registry).
MODES = {
    1: (2, "NONE", 2), 2: (4, "NONE", 4),
    3: (2, "NONE", 1), 4: (4, "NONE", 2),
    5: (2, "NONE", 0), 6: (4, "NONE", 0),
    7: (2, "fixed", 0), 8: (4, "fixed", 1), 9: (4, "fixed", 3),
    10: (2, "PAIR2", 2), 11: (4, "PAIR2", 4),
    12: (2, "PAIR2", 1), 13: (4, "PAIR2", 2),
    14: (2, "PAIR2", 0), 15: (4, "PAIR2", 0),
}


def syntax_cost(a, rice, span):
    if a < 2:
        return a
    cost = 2 + sum(a >= threshold for threshold in (2, 4, 6, 8))
    if a < 10:
        return cost
    rem = (a - 10) // 2
    if rem < 5 * (1 << rice):
        return cost + (rem >> rice) + 1 + rice
    cap, code = 27 - span, (rem >> rice) - 5
    if code >= (1 << cap) - 1:
        return cost + 5 + cap + span
    prefix = 0
    while code + 2 > 1 << (prefix + 1):
        prefix += 1
    return cost + 5 + 2 * prefix + rice + 1


class R14Predictor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ts-r14-predictor-")
        cls.exe = Path(cls.tmp.name) / "probe"
        result = subprocess.run(
            ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-Isource/Lib",
             "scripts/ts_r14_predictor_test.cpp", "-o", str(cls.exe)],
            cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            cls.tmp.cleanup()
            raise RuntimeError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def probe(self, action):
        proc = subprocess.run([str(self.exe), action], check=True, capture_output=True, text=True, timeout=120)
        return json.loads(proc.stdout)

    def query(self, inputs):
        payload = "".join(" ".join(map(str, case)) + "\n" for case in inputs)
        proc = subprocess.run([str(self.exe), "query"], input=payload, check=True,
                              capture_output=True, text=True, timeout=120)
        return [json.loads(line) for line in proc.stdout.splitlines()]

    def test_exhaustive_real_rice_support_candidates_ties_and_r13_equivalence(self):
        result = self.probe("exhaustive")
        self.assertTrue(result["pass"])
        self.assertEqual(result["decisions"], 3125 * 4 * 15)

    def test_large_range_real_rice_and_limited_escape(self):
        result = self.probe("random")
        self.assertTrue(result["pass"])
        self.assertEqual(result["decisions"], 18000 + 2 * 9 * 15)

    def test_state_machine_phase_target_ties_and_fixed7_counterexamples(self):
        result = self.probe("state")
        self.assertTrue(result["pass"])
        self.assertGreater(result["updates"], 1000)
        inputs = [(7, 0, 1, 15, 25, 25, 26, 1, 0, 0),
                  (7, 0, 1, 15, 4095, 4094, 4096, 4095, 0, 0)]
        self.assertEqual([r["predictor"] for r in self.query(inputs)], [25, 4095])
        c = lambda a: syntax_cost(a, 1, 15)
        self.assertEqual(2 * sum(reference.oracle_loss(a, 25, c) for a in (25, 26)), 3400)
        self.assertEqual(2 * sum(reference.oracle_loss(a, 26, c) for a in (25, 26)), 3402)

    def test_python_design_reference_with_full_production_rice_function(self):
        rng = random.Random(20261023)
        inputs = []
        for mode, (k, update, r0) in MODES.items():
            for _ in range(80):
                span, rice = rng.choice((15, 20)), rng.randrange(9)
                h = [rng.choice((0, 1, 2, 3, 25, 26, 4094, 4095, 4096, 1 << span)) for _ in range(5)]
                if update == "fixed":
                    state = r0
                else:
                    state = rng.randrange((k + 1) * (2 if update == "PAIR2" else 1))
                a = rng.choice((0, 1, 2, 25, 26, 4095, 1 << span))
                inputs.append((mode, state, rice, span, a, *h))
        results = self.query(inputs)
        self.assertEqual(len(results), len(inputs))
        for case, actual in zip(inputs, results):
            mode, state, rice, span, a, *h = case
            k, update, r0 = MODES[mode]
            c = lambda x: syntax_cost(x, rice, span)
            grid = tuple(range(k + 1)) if update != "fixed" else (r0,)
            weights = reference.all_winners(h, k, c, grid)
            r = r0 if update == "fixed" else reference.output_weight(reference.State(state), update, grid)
            self.assertEqual(actual["predictor"], reference.oracle_winner(h, k, r, c), case)
            self.assertEqual(actual["winners"], [weights.get(t, -1) for t in range(5)], case)
            eligible = update != "fixed" and reference.eligible(h, a)
            target = reference.feedback_target(weights, r, a, c) if eligible else r
            after = (state if update == "fixed" else
                     reference.step(reference.State(state), target, update, grid, eligible).value)
            self.assertEqual((actual["eligible"], actual["target"], actual["state"]),
                             (eligible, target, after), case)


if __name__ == "__main__":
    unittest.main()
