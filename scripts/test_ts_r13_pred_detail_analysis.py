"""Narrow integrity checks for R13 predictor forensic accounting; no video I/O."""
import tempfile
import unittest
from pathlib import Path

from ts_r13_pred_detail_analysis import analyze, loss168, pair_bins, predict, write_csv


class PredictorDetail(unittest.TestCase):
    def test_known_weight_inversion_and_candidate_order(self):
        h = [4, 4, 3, 3, 3]
        eq = predict(h, "eq", 1, 15)
        sp = predict(h, "sp", 1, 15)
        self.assertEqual(eq[:3], (3, [4, 0, 3], [2244, 2856, 1776]))
        self.assertEqual(sp[:3], (4, [4, 0, 3], [2580, 4200, 3048]))
        self.assertEqual(eq[3:], (5, 5))
        self.assertEqual(sp[3:], (5, 7))

    def test_sparse_bypass_and_identity(self):
        self.assertEqual(predict([1, 0, 0, 8, 0], "sp", 1, 15), (1, [], [], 2, 3))
        self.assertEqual(loss168(2, 1, 1, 15), 504)
        self.assertEqual(loss168(1, 2, 1, 15), 488)
        self.assertEqual(loss168(2, 2, 1, 15), 168)
        self.assertEqual(predict([1, 1, 1, 1, 1], "eq", 1, 15)[:3], (0, [0], [840]))

    def test_pairing_accounts_for_context_propagation_and_added_syntax(self):
        base = dict(cg=0, scan=0, **{"pass": 1}, syntax="gt1", value=1, ctx_id=7,
                    state0=2, state1=3, frac0=4, frac1=20, regular_budget_before=30,
                    bypass_length=1, cost_frac=20)
        bins = [dict(base, branch="eq"), dict(base, branch="sp", value=0, cost_frac=4),
                dict(base, branch="eq", scan=1),
                dict(base, branch="sp", scan=1, state1=5, frac1=25, cost_frac=25),
                dict(base, branch="eq", syntax="parity", value=0, cost_frac=4)]
        coefficients = {(scan, branch): {"predictor": 2} for scan in (0, 1) for branch in ("eq", "sp")}
        rows = pair_bins(bins, coefficients)
        self.assertEqual(sum(row["sp_minus_eq_frac"] for row in rows), -15)
        self.assertEqual({row["category"] for row in rows},
                         {"symbol_changed_context_same", "same_symbol_context_changed", "syntax_only_in_eq"})

    def test_full_zero_fixture_conservation_and_detect_tampering(self):
        # One synthetic all-zero 2x2 CG. It tests file/accounting integrity,
        # independently of real-codec replay tests performed by the C++ hook.
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            prefix = directory / "input"
            coefficients, bins, summaries = [], [], []
            for branch in ("current", "eq", "sp"):
                for scan in range(4):
                    x, y = scan % 2, scan // 2
                    row = dict(scan=scan, cg=0, raster=scan, x=x, y=y, q=0, abs_q=0,
                               available_mask=int(x > 0) | (int(y > 0) << 1) | (int(x > 0 and y > 0) << 2),
                               L=0, U=0, D=0, LL=0, UU=0, n=0, branch=branch,
                               weight_sum=0, scored=0, tied=0, predictor=0, regular_remap=0,
                               regular_active=0, actual_coding_level=0, cutoff=0, pass1_last=-1,
                               pass2_last=-1, pass1_frac=0, pass2_frac=0, bypass_frac=0, total_frac=0)
                    coefficients.append(row)
                bins.append(dict(branch=branch, cg=0, scan=-1, **{"pass": 0}, syntax="sig_group", value=0,
                                 ctx_id=10, state0=20, state1=40, frac0=123, frac1=456, cost_frac=123,
                                 cumulative_frac=123, regular_budget_before=7, bypass_length=1))
                summary = dict(branch=branch, cg=0, poc=16, component=0, x=0, y=0, width=2, height=2,
                               rice=1, range=15, first_scan=0, last_scan=3, significant=0, entry_budget=7,
                               end_budget=7, pass1_last=-1, pass2_last=-1, rate_frac=123, native_frac=None, validated=1)
                summaries.extend([dict(summary, kind="CG"), dict(summary, kind="TU", cg=-1,
                                  native_frac=123, validated=int(branch == "eq"))])
            write_csv(Path(str(prefix) + "_coeff.csv"), coefficients)
            write_csv(Path(str(prefix) + "_bins.csv"), bins)
            write_csv(Path(str(prefix) + "_summary.csv"), summaries)
            write_csv(Path(str(prefix) + "_candidates.csv"), [], ["scan", "branch", "candidate_order"])
            result = analyze(prefix, directory / "out", expected_delta=0)
            self.assertEqual(result["rate_frac"], {"current": 123, "eq": 123, "sp": 123})
            self.assertEqual(result["predictor_changed_scans"], [])
            bins[-1]["cumulative_frac"] += 1
            write_csv(Path(str(prefix) + "_bins.csv"), bins)
            with self.assertRaisesRegex(ValueError, "cumulative"):
                analyze(prefix, directory / "invalid", expected_delta=0)


if __name__ == "__main__":
    unittest.main()
