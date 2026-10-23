"""Pure R14 log fixtures: no builds or video coding."""
import csv
from pathlib import Path
import re
import tempfile
import unittest

from ts_r14_activity import (COUNTERS, KEYS, LABELS, MODES, PREFIXES, SCHEMAS,
                            TRIAL_COUNTERS, TRIAL_KEYS, export, parse)


def records():
    key = dict(mode=22, component=0, width=8, height=4, cu_qp=22, intra=0,
               bdpcm=0, target=1, cg_count_in_tu=2, cutoff=-1, n=-1, state=-1, weight=-1)
    total = dict(key, **dict.fromkeys(COUNTERS, 0))
    total.update(tu_count=1, cg_count=2, tu_valid_sum=6, tu_first_weight_event_sum=2,
                 tu_with_weight=1, tu_with_pdiff=1, tu_remaining_valid_sum=4, next_unpaired_count=1)
    a = dict(key, **dict.fromkeys(COUNTERS, 0))
    a.update(cutoff=10, n=3, state=4, weight=2, coeff_count=4, nonzero_count=3,
             target_count=4, zero_event_count=1, eligible_count=2, neutral_count=1, up_count=1,
             state_change_count=1, phase_only_count=1, p_vs_current=2, actual_remap_vs_current=1,
             actual_remap_nonzero=3, near_nonzero_sum=6, far_nonzero_sum=6, target_distance_sum=1,
             feedback_cost_tie_count=1, step_equal_count=2, next_pair_count=1,
             next_positive_count=1, next_gain_sum=2, next_p_changed=1, next_actual_remap_changed=1)
    b = dict(key, **dict.fromkeys(COUNTERS, 0))
    b.update(cutoff=2, n=4, state=3, weight=1, coeff_count=6, nonzero_count=5,
             target_count=6, zero_event_count=1, eligible_count=4, neutral_count=1, up_count=2, down_count=1,
             state_change_count=3, weight_change_count=2, phase_only_count=1,
             p_vs_current=3, actual_remap_vs_current=2, p_vs_initial_weight=2,
             actual_remap_vs_initial_weight=1, actual_remap_nonzero=4,
             near_nonzero_sum=9, far_nonzero_sum=15, target_distance_sum=3,
             step_better_count=2, step_worse_count=1, step_equal_count=1,
             next_pair_count=4, next_positive_count=1, next_zero_count=2, next_negative_count=1,
             next_gain_sum=-1, next_cross_cg_count=1, next_phase_pair_count=1,
             next_p_changed=2, next_actual_remap_changed=1, direction_reverse_count=1)
    trial = {k: key[k] for k in TRIAL_KEYS}
    trial.update(cg_trial_count=100, zero_cg_count=40, rolled_back_state_count=10)
    return [total, a, b], [trial]


def render(stats=None, trials=None):
    lines = ["encoder ordinary output"]
    for population, rows in (("stats", stats), ("trial", trials)):
        if rows is None:
            continue
        header, prefix = PREFIXES[population]
        columns = SCHEMAS[population]
        lines.append(header + ",".join(columns))
        for row in rows:
            lines.append(prefix + ",".join(str(row[k]) for k in columns))
    return "\n".join(lines) + "\n"


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


class R14ActivityTests(unittest.TestCase):
    def test_schema_matches_production_header(self):
        source = (Path(__file__).resolve().parents[1] / "source/Lib/CommonLib/TsR14Stats.h").read_text()
        match = re.search(r'const char \*const fields\[\]=\{(.*?)\};', source, re.S)
        self.assertIsNotNone(match)
        self.assertEqual(tuple(re.findall(r'"([a-z_]+)"', match.group(1))), COUNTERS)
        self.assertIn("TS_R14_STATS_HEADER " + ",".join(KEYS), source)
        self.assertIn("TS_R14_TRIAL_HEADER " + ",".join(SCHEMAS["trial"]), source)

    def test_separate_populations_normalization_and_residence(self):
        stats, trials = records()
        text = render(stats, trials)
        parsed = parse(text)
        self.assertEqual(parsed, {"stats": stats, "trial": trials})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            log, output = root / "input.log", root / "extract"
            log.write_text(text)
            result = export([log], output, "Example", "LB", "27")
            self.assertEqual(result, dict(final_writer_rows=3, trial_rows=1, final_groups=1, trial_groups=1))
            self.assertEqual(log.read_text(), text)
            raw = read_csv(output / "final_writer.csv")
            self.assertEqual(sum(int(r["coeff_count"]) for r in raw), 10)
            self.assertNotIn("cg_trial_count", raw[0])
            summary = read_csv(output / "final_writer_summary.csv")[0]
            self.assertEqual(summary["cu_qp"], "22")
            self.assertEqual(summary["nominal_qp"], "27")
            self.assertEqual(summary["sequence"], "Example")
            self.assertEqual(float(summary["mean_next_gain"]), 0.2)
            self.assertEqual(float(summary["next_positive_fraction"]), 0.4)
            self.assertEqual(float(summary["next_zero_fraction"]), 0.4)
            self.assertEqual(float(summary["next_negative_fraction"]), 0.2)
            self.assertEqual(float(summary["mean_next_phase_gain"]), 0)
            self.assertEqual(float(summary["mean_next_nonphase_gain"]), 0.25)
            self.assertEqual(float(summary["tu_weight_change_fraction"]), 1)
            self.assertAlmostEqual(float(summary["actual_remap_difference_fraction_regular_nonzero"]), 3 / 7)
            self.assertEqual(float(summary["predictor_vs_initial_fraction_target"]), 0.2)
            self.assertEqual(float(summary["next_p_changed_fraction"]), 0.6)
            self.assertEqual(float(summary["mean_first_weight_event_changed_tu"]), 2)
            self.assertEqual(float(summary["mean_remaining_eligible_changed_tu"]), 4)
            residence = read_csv(output / "state_residence.csv")
            self.assertEqual(len(residence), 2)
            self.assertEqual({r["state"]: float(r["coeff_fraction"]) for r in residence}, {"3": 0.6, "4": 0.4})
            self.assertAlmostEqual(sum(float(r["coeff_fraction"]) for r in residence), 1)
            trial = read_csv(output / "rd_trial_summary.csv")[0]
            self.assertEqual(float(trial["zero_cg_fraction_trials"]), 0.4)
            self.assertEqual(float(trial["rollback_fraction_zero_trials"]), 0.25)
            self.assertNotIn("coeff_count", trial)
            report = (output / "summary.md").read_text()
            self.assertIn("neither measured CABAC bits nor BD-rate", report)
            self.assertIn("initial weight", report)

    def test_missing_population_and_zero_denominator_are_not_observed_zero(self):
        stats, trials = records()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for text, missing, wording in ((render(stats), "rd_trial.csv", "No RDOQ trial report"),
                                           (render(trials=trials), "final_writer.csv", "No final-Writer report")):
                log = root / "input.log"
                log.write_text(text)
                export([log], root / "out")
                self.assertEqual(read_csv(root / "out" / missing), [])
                self.assertIn(wording, (root / "out/summary.md").read_text())
            # Fixed mode has no feedback, not a measured g_next=0.
            for row in stats:
                row["mode"] = 19
                if row["state"] >= 0:
                    row["state"] = row["weight"] = 0
                for counter in COUNTERS:
                    if counter not in ("tu_count", "cg_count", "coeff_count", "nonzero_count", "target_count",
                                       "zero_event_count", "p_vs_current", "actual_remap_vs_current", "actual_remap_nonzero"):
                        row[counter] = 0
            stats[0].update(tu_no_weight=1, tu_with_pdiff=1)
            log.write_text(render(stats))
            export([log], root / "out")
            summary = read_csv(root / "out/final_writer_summary.csv")[0]
            self.assertEqual(summary["mean_next_gain"], "")
            self.assertEqual(summary["mean_first_weight_event_changed_tu"], "")
            self.assertEqual(float(summary["tu_weight_change_fraction"]), 0)

    def test_input_protection_duplicate_logs_and_no_statistics(self):
        stats, trials = records()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            log = root / "final_writer.csv"
            original = render(stats, trials)
            log.write_text(original)
            with self.assertRaisesRegex(ValueError, "overwrite"):
                export([log], root)
            with self.assertRaisesRegex(ValueError, "Duplicate input"):
                export([log, log], root / "other")
            empty = root / "empty.log"
            empty.write_text("TS R14 stats=0;\n")
            with self.assertRaisesRegex(ValueError, "defaults OFF"):
                export([log, empty], root / "not-created")
            self.assertFalse((root / "not-created").exists())
            self.assertEqual(log.read_text(), original)

    def test_malformed_schema_rows_headers_and_counts(self):
        stats, trials = records()
        text = render(stats, trials)
        invalid = ["TS_R14_STATS 1,2\n", "TS_R14_TRIAL 1,2\n", text + "TS_R14_STATS 1,2\n",
                   text + render(stats), text + render(trials=trials),
                   text.replace("mode,component", "mode,mode", 1),
                   text.replace("TS_R14_STATS 22,", "TS_R14_STATS x,", 1),
                   text + "TS_R14_STATS " + ",".join(str(stats[0][k]) for k in SCHEMAS["stats"]) + "\n"]
        for case in invalid:
            with self.subTest(case=case[:100]), self.assertRaises(ValueError):
                parse(case)
        for key, value in (("next_phase_gain_sum", 1), ("eligible_count", 7),
                           ("next_positive_count", 3), ("actual_remap_vs_current", 9),
                           ("next_p_changed", 9), ("mode", 2), ("state", 12)):
            changed = [r.copy() for r in stats]
            changed[1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse(render(changed, trials))
        changed = [r.copy() for r in stats]
        changed[0]["next_unpaired_count"] = 0
        with self.assertRaisesRegex(ValueError, "pairing"):
            parse(render(changed))


if __name__ == "__main__":
    unittest.main()
