import json
import tempfile
import unittest
from pathlib import Path

from ts_r13_decode_diagnosis import compare_rows, records, validate_stages, validate_decode


class DecoderDiagnosisTest(unittest.TestCase):
    def test_unpaired_geometry_is_not_matched_by_order(self):
        a = dict(kind='CU', poc=16, ctu=36, channel=0, x=768, y=384, w=64, h=64, order=1)
        b = dict(a, w=32, order=1)
        differences, counts = compare_rows([a], [b])
        self.assertEqual(counts['CU']['reference_only'], 1)
        self.assertEqual(counts['CU']['test_only'], 1)
        self.assertEqual(len(differences), 2)

    def test_order_is_not_a_syntax_difference(self):
        a = dict(kind='CU', poc=16, ctu=36, channel=0, x=768, y=384, w=64, h=64, order=1)
        differences, counts = compare_rows([a], [dict(a, order=42)])
        self.assertEqual(differences, [])
        self.assertEqual(counts['CU']['equal'], 1)
        with self.assertRaises(ValueError):
            compare_rows([a, a], [a])

    def test_truncation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'log'
            path.write_text('TS_R13_DEC ' + json.dumps(dict(kind='syntax_summary', truncated=1)))
            with self.assertRaises(ValueError):
                records(path)

    def test_conservation_requires_complete_tiles(self):
        f = dict(kind='frame', poc=0, stage='before_dbf', component=0, samples=4, has_original=1, sse=8)
        t = dict(f, kind='tile', x=0, y=0)
        self.assertEqual(validate_stages([f, t]), 1)
        with self.assertRaises(ValueError):
            validate_stages([f, dict(t, sse=7)])
        with self.assertRaises(ValueError):
            validate_stages([f])
        with self.assertRaises(ValueError):
            validate_stages([f, f, t])

    def test_decode_md5_population(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'log'
            line = 'POC 0 [DT 0.01] [MD5:aa,bb,cc,(OK)]\n'
            path.write_text(line)
            self.assertEqual(validate_decode(path, {0: ('aa', 'bb', 'cc')}), 1)
            path.write_text(line * 2)
            with self.assertRaises(ValueError):
                validate_decode(path, {0: ('aa', 'bb', 'cc')})


if __name__ == '__main__':
    unittest.main()
