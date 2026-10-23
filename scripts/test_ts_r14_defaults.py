"""R14 macro/runtime identity and rejection probes; no codec/video runs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    1: "r14_g2_none_equal", 2: "r14_g4_none_equal",
    3: "r14_g2_none_half", 4: "r14_g4_none_half",
    5: "r14_g2_none_zero", 6: "r14_g4_none_zero",
    7: "r14_fixed_near_only", 8: "r14_fixed_quarter", 9: "r14_fixed_threequarter",
    10: "r14_g2_pair2_equal", 11: "r14_g4_pair2_equal",
    12: "r14_g2_pair2_half", 13: "r14_g4_pair2_half",
    14: "r14_g2_pair2_zero", 15: "r14_g4_pair2_zero",
}
OLD_DEFAULTS = ("CONDITIONAL_MODE", "FIXED_NOPRED", "FIXED_GRADIENT", "FIXED_DIRECTIONAL",
                "R10_CACHE", *[f"R{i}_MODE" for i in range(2, 14)], "RATE_MODE")


class R14Defaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ts-r14-defaults-")
        cls.base = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "source/Lib/CommonLib"),
                    str(ROOT / "scripts/ts_fixed_mode_probe.cpp")]
        cls.exes = {}
        for mode in (0, *NAMES, "off"):
            exe = Path(cls.tmp.name) / str(mode)
            defines = [f"-DJVET_BJUT_TS_R14_MODE={0 if mode == 'off' else mode}",
                       f"-DJVET_BJUT_TS_FIXED_PREDICTOR={int(mode != 'off')}"]
            result = subprocess.run(cls.base + defines + ["-o", str(exe)], capture_output=True, text=True)
            if result.returncode:
                cls.tmp.cleanup()
                raise RuntimeError(result.stderr)
            cls.exes[mode] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_probe(self, mode, **env):
        clean = {key: val for key, val in os.environ.items() if not key.startswith("TS_")}
        return subprocess.run([str(self.exes[mode])], env={**clean, **env}, capture_output=True, text=True)

    def test_all_macro_defaults_and_startup_identity(self):
        for mode, name in NAMES.items():
            result = self.run_probe(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"ACTUAL_MODE={name}", result.stdout)
            self.assertIn("selection: TypeDef.h default", result.stdout)
            self.assertIn(f"TS R14 revision=R14-NF-168-v3; numbering=compact-15-v1; mode={mode}; runtime={name};", result.stdout)
            self.assertIn("score-scale=168; target=TSRC-enabled-nonBDPCM; stats=0; trace=0;", result.stdout)
        for mode in (0, "off"):
            result = self.run_probe(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ACTUAL_MODE=current", result.stdout)
            self.assertNotIn("TS R14 revision=", result.stdout)

    def test_override_matrix_and_legacy_runtime(self):
        for default in (0, *NAMES):
            for override in (*NAMES.values(), "current", "r3_risk_guard", "r13_keep_hit_uniform"):
                result = self.run_probe(default, TS_FIXED_PREDICTOR=override)
                self.assertEqual(result.returncode, 0, (default, override, result.stderr))
                self.assertIn(f"ACTUAL_MODE={override}", result.stdout)
        for override in NAMES.values():
            self.assertNotEqual(self.run_probe("off", TS_FIXED_PREDICTOR=override).returncode, 0)

    def test_out_of_range_macros_and_all_legacy_conflicts(self):
        invalid = [i for i in range(-1, 29) if i != 0 and i not in NAMES]
        cases = [[f"-DJVET_BJUT_TS_R14_MODE={mode}"] for mode in invalid]
        cases += [["-DJVET_BJUT_TS_R14_MODE=1", "-DJVET_BJUT_TS_FIXED_PREDICTOR=0"]]
        cases += [["-DJVET_BJUT_TS_R14_MODE=1", f"-DJVET_BJUT_TS_{old}=1"] for old in OLD_DEFAULTS]
        for flags in cases:
            result = subprocess.run(self.base + flags + ["-fsyntax-only"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, flags)
            self.assertIn("R14", result.stderr, flags)

    def test_retired_runtime_names_and_old_observer_misconnection_fail(self):
        retired = [f"r14_g{k}_{update}_{init}" for k in (2, 4)
                   for update in ("target2", "dir2") for init in ("equal", "half", "zero")]
        for name in (*retired, "r14_unknown", "r14_2"):
            self.assertNotEqual(self.run_probe(0, TS_FIXED_PREDICTOR=name).returncode, 0, name)
        for env in ({"TS_R10_CACHE": "1"}, {"TS_RATE_SHADOW": "1"},
                    {"TS_RATE_RDOQ_SHADOW": "1"}, {"TS_R12_STATS": "1"}, {"TS_R13_STATS": "1"}):
            self.assertNotEqual(self.run_probe(1, **env).returncode, 0, env)

    def test_observation_validation_and_no_implicit_enable(self):
        result = self.run_probe(10, TS_R14_STATS="1", TS_R14_TRACE="1", TS_R14_DETAIL_LIMIT="4", TS_R14_POC="2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("update=PAIR2; r0=2; s0=5;", result.stdout)
        self.assertIn("stats=1; trace=1;", result.stdout)
        self.assertIn("detail-limit=4; poc=2;", result.stdout)
        for mode in (0, "off"):
            self.assertNotEqual(self.run_probe(mode, TS_R14_STATS="1").returncode, 0)
        for env in ({"TS_R14_STATS": "2"}, {"TS_R14_TRACE": "true"},
                    {"TS_R14_DETAIL_LIMIT": "1025"}, {"TS_R14_DETAIL_LIMIT": "-1"},
                    {"TS_R14_POC": "2147483648"}, {"TS_R14_POC": ""}):
            self.assertNotEqual(self.run_probe(1, **env).returncode, 0, env)
        result = self.run_probe(1, TS_R14_DETAIL_LIMIT="4", TS_R14_POC="2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stats=0; trace=0;", result.stdout)


if __name__ == "__main__":
    unittest.main()
