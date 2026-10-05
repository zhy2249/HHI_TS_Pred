"""Inspect wrapper environments without starting batch_test or any video coding."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

from ts_conditional_smoke import observation_environment

ROOT = Path(__file__).resolve().parents[1]
NORMAL = {
    "run_ts_r6_lb_ce.sh": "TS_R6_STATS",
    "run_ts_r8_lb_ce.sh": "TS_R8_STATS",
    "run_ts_r8_preflight.sh": "TS_R8_STATS",
    "run_ts_r9_lb_ce.sh": "TS_R9_STATS",
    "run_ts_r10_lb_ce.sh": "TS_R10_STATS",
    "run_ts_r11_lb_ce.sh": "TS_R11_STATS",
    "run_ts_r12_lb_ce.sh": "TS_R12_STATS",
}
PLAIN = "run_ts_conditional_lb_ce.sh"
SHADOW = "run_ts_rate_shadow.sh"


class StatisticsWrapperDefaults(unittest.TestCase):
    def inspect(self, name, options=None, arguments=()):
        env = {k: v for k, v in os.environ.items() if not k.startswith("TS_")}
        env.update(options or {})
        # Source the real wrapper, but replace the exec shell builtin with a
        # function that only serializes its argv/environment. Thus the final
        # `exec python3 ... batch_test.py` cannot start an encoder or a batch.
        probe = (
            "import json,os,sys; "
            "print(json.dumps({'argv':sys.argv[1:],"
            "'env':{k:v for k,v in os.environ.items() if k.startswith('TS_')}}))"
        )
        shell = (
            "exec() { command " + shlex.quote(sys.executable) + " -c "
            + shlex.quote(probe) + ' "$@"; }; '
            'wrapper_file=$1; shift; source "$wrapper_file" "$@"'
        )
        result = subprocess.run(
            ["bash", "-c", shell, "ts-wrapper-probe", str(ROOT / "scripts" / name), *arguments],
            cwd=ROOT, env=env, capture_output=True, text=True, check=True, timeout=10,
        )
        return json.loads(result.stdout)

    def test_all_wrappers_are_accounted_for(self):
        actual = {p.name for p in (ROOT / "scripts").glob("run_ts_*.sh")}
        self.assertEqual(actual, set(NORMAL) | {PLAIN, SHADOW})

    def test_default_statistics_are_off(self):
        for script, key in NORMAL.items():
            with self.subTest(script=script):
                row = self.inspect(script)
                self.assertEqual(row["env"][key], "0")
                for name, value in row["env"].items():
                    if name.endswith("_STATS"):
                        self.assertEqual(value, "0", name)
                self.assertEqual(row["argv"][:3], ["python3", "-u", "scripts/batch_test.py"])
        self.assertFalse(any(k.endswith("_STATS") for k in self.inspect(PLAIN)["env"]))

    def test_explicit_statistics_settings_are_preserved(self):
        for script, key in NORMAL.items():
            for value in ("0", "1"):
                with self.subTest(script=script, value=value):
                    self.assertEqual(self.inspect(script, {key: value})["env"][key], value)

    def test_arguments_and_existing_trace_policy_are_preserved(self):
        arguments = ("--jobs", "2", "--fixed-predictors", "current")
        for script in (*NORMAL, PLAIN, SHADOW):
            with self.subTest(script=script):
                row = self.inspect(script, {"TS_COND_TRACE": "1"}, arguments)
                self.assertEqual(row["argv"][-len(arguments):], list(arguments))
                self.assertNotIn("TS_COND_TRACE", row["env"])
        self.assertEqual(self.inspect("run_ts_r11_lb_ce.sh", {"TS_R11_TRACE": "1"})["env"]["TS_R11_TRACE"], "0")
        self.assertEqual(self.inspect("run_ts_r12_lb_ce.sh", {"TS_R12_TRACE": "1"})["env"]["TS_R12_TRACE"], "1")

    def test_dedicated_shadow_script_is_an_explicit_exception(self):
        default = self.inspect(SHADOW)["env"]
        self.assertEqual(default["TS_RATE_SHADOW"], "1")
        self.assertEqual(default["TS_RATE_RDOQ_SHADOW"], "0")
        requested = self.inspect(SHADOW, {"TS_RATE_RDOQ_SHADOW": "1"})["env"]
        self.assertEqual(requested["TS_RATE_SHADOW"], "1")
        self.assertEqual(requested["TS_RATE_RDOQ_SHADOW"], "1")

    def test_smoke_observation_phase_explicitly_enables_only_legacy_statistics(self):
        original = {"TS_FIXED_PREDICTOR": "r6_reject_nopred", "TS_R3_STATS": "0",
                    "TS_R8_STATS": "0", "TS_COND_TRACE": "0", "UNRELATED": "kept"}
        expected_original = original.copy()
        observed = observation_environment(original, True)
        self.assertEqual(original, expected_original)
        for revision in range(2, 7):
            self.assertEqual(observed[f"TS_R{revision}_STATS"], "1")
        self.assertEqual(observed["TS_COND_TRACE"], "1")
        self.assertEqual(observed["TS_R8_STATS"], "0")
        self.assertEqual(observed["TS_FIXED_PREDICTOR"], original["TS_FIXED_PREDICTOR"])
        self.assertEqual(observed["UNRELATED"], "kept")

    def test_smoke_off_phase_clears_trace_and_forces_zero_without_mutating_parent(self):
        observed = observation_environment({"TS_R8_STATS": "1"}, True)
        original = observed.copy()
        disabled = observation_environment(observed, False)
        self.assertEqual(observed, original)
        self.assertNotIn("TS_COND_TRACE", disabled)
        for revision in range(2, 7):
            self.assertEqual(disabled[f"TS_R{revision}_STATS"], "0")
        self.assertEqual(disabled["TS_R8_STATS"], "1")


if __name__ == "__main__":
    unittest.main()
