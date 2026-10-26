import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import schedule_storage as S


class StorageTests(unittest.TestCase):
    def test_lossless_pack_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.pred'
            original = b'TSCPRED 1 61\n' + b'0 2 0 3\n' * 10000
            path.write_bytes(original)
            receipt = S.pack(path, 1024**2, hashlib.sha256(original).hexdigest())
            self.assertFalse(path.exists())
            self.assertTrue(receipt['round_trip_verified'])
            S.restore(Path(receipt['archive']))
            self.assertEqual(path.read_bytes(), original)

    def test_bad_identity_preserves_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.pred'
            path.write_text('1 2 3\n')
            with self.assertRaisesRegex(ValueError, 'SHA'):
                S.pack(path, 1024**2, 'wrong')
            self.assertTrue(path.exists())
            self.assertFalse(path.with_name(path.name + '.gz').exists())

    def test_archive_limit_preserves_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.pred'
            path.write_text('1 2 3\n')
            with self.assertRaisesRegex(ValueError, 'size limit'):
                S.pack(path, 1)
            self.assertTrue(path.exists())

    def test_in_flight_schedule_is_not_packed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'schedules').mkdir()
            path = root / 'schedules' / 'active.pred'
            path.write_text('1 2 3\n')
            (root / 'evaluation' / 'active').mkdir(parents=True)
            self.assertEqual(S.pack_completed(root, 1024**2), [])
            self.assertTrue(path.exists())


if __name__ == '__main__':
    unittest.main()
