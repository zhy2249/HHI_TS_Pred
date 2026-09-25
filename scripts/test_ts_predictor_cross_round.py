#!/usr/bin/env python3
import math
import unittest

from ts_predictor_cross_round_analysis import compare, quality_bands


class CrossRoundTest(unittest.TestCase):
    def setUp(self):
        # QP order: 22, 27, 32, 37. Components have different quality spans.
        self.anchor = [[100 * math.exp(i), 30 + 2 * i, 35 + i, 32 + 1.5 * i]
                       for i in (3, 2, 1, 0)]

    def test_identical(self):
        self.assertEqual(compare(self.anchor, self.anchor)['weighted'], 0)
        for row in quality_bands(self.anchor, self.anchor):
            self.assertEqual(row['weighted'], 0)

    def test_constant_rate_scaling(self):
        other = [[r * .99, y, u, v] for r, y, u, v in self.anchor]
        for row in quality_bands(self.anchor, other):
            for component in ('Y', 'U', 'V', 'weighted'):
                self.assertAlmostEqual(row[component], -1, places=10)

    def test_component_first_weighting(self):
        other = [[r, y + .01, u - .02, v + .03] for r, y, u, v in self.anchor]
        row = compare(self.anchor, other)
        expected = [100 * math.expm1(-.005), 100 * math.expm1(.02),
                    100 * math.expm1(-.02)]
        self.assertAlmostEqual(row['weighted'], (6 * expected[0] + expected[1] + expected[2]) / 8, places=9)
        # quality_bands also asserts reconstruction of the full component integrals.
        self.assertEqual(len(quality_bands(self.anchor, other)), 3)


if __name__ == '__main__':
    unittest.main()
