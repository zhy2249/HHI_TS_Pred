import csv
from pathlib import Path
import tempfile
import unittest
from ts_r13_activity import export, parse, REQUIRED


class R13ActivityTests(unittest.TestCase):
    def sample(self, n=3):
        record = {key: 0 for key in sorted(REQUIRED)}
        record.update(trajectory_policy=98, shadow_mode=1, component=0, width=8, height=8,
                      cu_qp=22, cutoff=10, n=n, weight_sum=n, coeff_count=2,
                      scored_count=2 if n >= 3 else 0, valid_margin_count=2 if n >= 3 else 0,
                      margin_sum168=1008 if n >= 3 else 0)
        return 'TS_R13_STATS_HEADER '+','.join(record)+'\nTS_R13_STATS '+','.join(map(str, record.values()))+'\n'

    def test_parse_and_normalize(self):
        self.assertEqual(parse(self.sample())[0]['trajectory_policy'], 98)
        with tempfile.TemporaryDirectory() as temp:
            log, out = Path(temp)/'input.log', Path(temp)/'out.csv'
            text = self.sample()
            log.write_text(text)
            self.assertEqual(export([log], out, 'sequence', 'LBeu', '22'), 1)
            with out.open() as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(float(row['mean_margin_per_weight']), 1.0)
            self.assertEqual(row['sequence'], 'sequence')
            self.assertEqual(log.read_text(), text)
            with self.assertRaises(ValueError):
                export([log], log)

    def test_sparse_margin_is_missing_not_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            log, out = Path(temp)/'input.log', Path(temp)/'out.csv'
            log.write_text(self.sample(2))
            export([log], out)
            with out.open() as stream:
                self.assertEqual(next(csv.DictReader(stream))['mean_margin_per_weight'], '')

    def test_invalid_reports(self):
        for text in ('TS_R13_STATS 1,2\n', self.sample()+'TS_R13_STATS 1,2\n', self.sample()*2):
            with self.assertRaises(ValueError):
                parse(text)
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp)/'no_stats.log'
            log.write_text('TS R13 stats=0;\n')
            with self.assertRaises(ValueError):
                export([log], Path(temp)/'out.csv')


if __name__ == '__main__':
    unittest.main()
