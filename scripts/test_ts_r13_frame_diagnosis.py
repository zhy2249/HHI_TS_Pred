import tempfile
import unittest
from pathlib import Path

from ts_r13_frame_diagnosis import compare, parse


class FrameDiagnosisTest(unittest.TestCase):
    def fixture(self, sse=200, original=123):
        common = 'trajectory,poc,layer,stage,component,bitdepth,'
        tail = 'clip_pending,true_original,samples,sse,original_hash,reconstruction_hash'
        return (f'TS_R13_FRAME_HEADER {common}width,height,grid_size,{tail}\n'
                f'TS_R13_FRAME_TILE_HEADER {common}x,y,width,height,{tail}\n'
                f'TS_R13_FRAME 99,0,0,final_clip,1,10,2,1,64,0,0,2,{sse},{original},234\n'
                f'TS_R13_FRAME_TILE 99,0,0,final_clip,1,10,0,0,2,1,0,0,2,{sse},{original},234\n')

    def read(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'log'
            path.write_text(text)
            return parse(path)

    def test_exact_ratio_and_conservation(self):
        rows = compare(self.read(self.fixture()), self.read(self.fixture(400)))['FRAME']
        self.assertEqual(rows[0]['delta_sse_percent'], 100)
        self.assertAlmostEqual(rows[0]['delta_psnr_db'], -3.01029995664)

    def test_original_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            compare(self.read(self.fixture()), self.read(self.fixture(original=124)))

    def test_truncated_population_rejected(self):
        with self.assertRaises(ValueError):
            self.read(self.fixture().replace(',200,123,234\n', ',201,123,234\n', 1))


if __name__ == '__main__':
    unittest.main()
