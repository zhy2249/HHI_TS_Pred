"""R15 macro defaults, runtime overrides and compile-time mutual exclusion."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from ts_predictor_naming import R15_MODE_NUMBERS, r15_protocol

ROOT = Path(__file__).resolve().parents[1]


class R15Defaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ts-r15-defaults-")
        cls.base = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "source/Lib/CommonLib"), str(ROOT / "scripts/ts_fixed_mode_probe.cpp")]
        cls.exes = {}
        for mode in (0, *R15_MODE_NUMBERS.values(), "off"):
            exe = Path(cls.tmp.name) / str(mode)
            flags = [f"-DJVET_BJUT_TS_R15_MODE={0 if mode == 'off' else mode}",
                     f"-DJVET_BJUT_TS_FIXED_PREDICTOR={int(mode != 'off')}"]
            result = subprocess.run(cls.base + flags + ["-o", str(exe)], capture_output=True, text=True)
            if result.returncode:
                cls.tmp.cleanup()
                raise RuntimeError(result.stderr)
            cls.exes[mode] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def probe(self, mode, **env):
        clean = {k: v for k, v in os.environ.items() if not k.startswith('TS_')}
        return subprocess.run([str(self.exes[mode])], env={**clean, **env}, capture_output=True, text=True)

    def test_defaults_and_full_override_matrix(self):
        for name, mode in R15_MODE_NUMBERS.items():
            output = self.probe(mode)
            self.assertEqual(output.returncode, 0, output.stderr)
            self.assertIn(f'ACTUAL_MODE={name}', output.stdout)
            self.assertIn(f'mode={mode}; runtime={name}; engine=PREFIX;', output.stdout)
            self.assertIn('quant-search=map-up-to-1; stats=0;', output.stdout)
            self.assertIn('selection: TypeDef.h default', output.stdout)
        for default in (0, *R15_MODE_NUMBERS.values()):
            for name in (*R15_MODE_NUMBERS, 'current', 'nopred', 'r13_keep_hit_uniform', 'r14_g2_pair2_equal'):
                output = self.probe(default, TS_FIXED_PREDICTOR=name)
                self.assertEqual(output.returncode, 0, (default, name, output.stderr))
                self.assertIn(f'ACTUAL_MODE={name}', output.stdout)
        for mode in (0, 'off'):
            self.assertIn('ACTUAL_MODE=current', self.probe(mode).stdout)
        for name in R15_MODE_NUMBERS:
            self.assertNotEqual(self.probe('off', TS_FIXED_PREDICTOR=name).returncode, 0)

    def test_compile_conflicts_ranges_and_stats_validation(self):
        old = ['CONDITIONAL_MODE', 'FIXED_NOPRED', 'FIXED_GRADIENT', 'FIXED_DIRECTIONAL',
               'R10_CACHE', 'RATE_MODE', *[f'R{i}_MODE' for i in range(2, 15)]]
        cases = [['-DJVET_BJUT_TS_R15_MODE=1', f'-DJVET_BJUT_TS_{key}=1'] for key in old]
        cases += [['-DJVET_BJUT_TS_R15_MODE=1', '-DJVET_BJUT_TS_FIXED_PREDICTOR=0'],
                  ['-DJVET_BJUT_TS_R15_MODE=-1'], ['-DJVET_BJUT_TS_R15_MODE=19'],
                  ['-DJVET_BJUT_TS_R15_STATS=2']]
        for flags in cases:
            output = subprocess.run(self.base + flags + ['-fsyntax-only'], capture_output=True, text=True)
            self.assertNotEqual(output.returncode, 0, flags)
            self.assertIn('R15', output.stderr)
        self.assertIn('stats=1;', self.probe(2, TS_R15_STATS='1').stdout)
        for flag in ('', '2', 'true'):
            self.assertNotEqual(self.probe(2, TS_R15_STATS=flag).returncode, 0)
        self.assertNotEqual(self.probe(0, TS_R15_STATS='1').returncode, 0)
        for key in ('TS_R13_STATS', 'TS_R14_STATS', 'TS_RATE_SHADOW', 'TS_R10_CACHE'):
            self.assertNotEqual(self.probe(2, **{key: '1'}).returncode, 0)


if __name__ == '__main__':
    unittest.main()
