#!/usr/bin/env python3
"""Exercise the actual production observation predicates, without video coding."""
import collections
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class StatsDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.tmp = tempfile.TemporaryDirectory(prefix='ts-stats-defaults-')
        # Compile the expressions copied verbatim from all production guards,
        # including the separate R2 Writer and R9 search-observation gates.
        pattern = re.compile(
            r'!?std::getenv\("(?P<key>TS_R\d+_STATS)"\)\s*(?:\|\||&&)\s*'
            r'!?std::strcmp\(std::getenv\("(?P=key)"\),\s*"[01]"\)')
        cls.predicates = []
        for path in ('source/Lib/CommonLib/ContextModelling.cpp',
                     'source/Lib/CommonLib/TsFixedPrediction.h',
                     'source/Lib/CommonLib/TsR9Quant.h',
                     'source/Lib/EncoderLib/TsR8Search.h',
                     'source/Lib/EncoderLib/CABACWriter.cpp'):
            for match in pattern.finditer((cls.root / path).read_text()):
                cls.predicates.append((match['key'], match.group()))
        cls.counts = collections.Counter(key for key, _ in cls.predicates)
        cls.exe = Path(cls.tmp.name) / 'stats'
        rows = ['#include "TsFixedPrediction.h"', 'int main() {']
        rows += [f'std::printf("{key}=%d\\n", int(bool({expression})));'
                 for key, expression in cls.predicates]
        rows += ['std::printf("TS_R12_STATS=%d\\n", int(TsFixedPrediction::r12Observation().stats));', '}']
        subprocess.run(['g++', '-std=c++17', '-DJVET_BJUT_TS_R12_MODE=11',
                        '-I', str(cls.root / 'source/Lib/CommonLib'),
                        '-x', 'c++', '-', '-o', str(cls.exe)],
                       input='\n'.join(rows), text=True, check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_production_gates_covered(self):
        self.assertEqual(self.counts, collections.Counter({
            'TS_R2_STATS': 2, 'TS_R3_STATS': 1, 'TS_R4_STATS': 1,
            'TS_R5_STATS': 1, 'TS_R6_STATS': 1, 'TS_R8_STATS': 2,
            'TS_R9_STATS': 2, 'TS_R10_STATS': 1, 'TS_R11_STATS': 1}))

    def test_defaults_and_explicit_switches(self):
        clean = {k: v for k, v in os.environ.items() if not k.startswith('TS_')}
        for value, expected in ((None, '0'), ('0', '0'), ('1', '1')):
            settings = {} if value is None else {
                key: value for key in (*self.counts, 'TS_R12_STATS')}
            result = subprocess.run([str(self.exe)], env={**clean, **settings},
                                    capture_output=True, text=True, check=True)
            lines = result.stdout.splitlines()
            self.assertEqual(len(lines), sum(self.counts.values()) + 1)
            for line in lines:
                self.assertEqual(line.split('=')[1], expected, (value, line))


if __name__ == '__main__':
    unittest.main()
