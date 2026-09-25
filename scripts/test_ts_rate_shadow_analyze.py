import unittest
import csv
import tempfile
from pathlib import Path
from ts_rate_shadow_analyze import parse_table, metrics, compare_streams
from collections import defaultdict

class RateShadowTests(unittest.TestCase):
    def test_schema(self):
        h,r=parse_table('TS_RATE_SHADOW_HEADER a,b\nTS_RATE_SHADOW 1,-2\n','TS_RATE_SHADOW')
        self.assertEqual(h,['a','b']);self.assertEqual(r,[{'a':1,'b':-2}])
    def test_partial_rejected(self):
        for s in ('TS_RATE_SHADOW 1,2\n','TS_RATE_SHADOW_HEADER a,b\nTS_RATE_SHADOW 1\n',
                  'TS_RATE_SHADOW_HEADER a,a\nTS_RATE_SHADOW 1,2\n'):
            with self.assertRaises(ValueError):parse_table(s,'TS_RATE_SHADOW')
    def test_denominators(self):
        v=defaultdict(int,eligible=20,winner_disagree=5,current_tie=4,current_tie_broken=2,
                      cost_pairs=10,old_delta_abs_error_q15=327680,new_delta_abs_error_q15=163840)
        m=metrics(v)
        self.assertEqual(m['winner_disagree_pct'],25);self.assertEqual(m['ties_broken_pct'],50)
        self.assertEqual(m['old_delta_mae_bits'],1);self.assertEqual(m['new_delta_mae_bits'],.5)
        self.assertIsNone(metrics(defaultdict(int))['winner_disagree_pct'])
    def test_reference_bit_exact(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); a=root/'shadow.bin';b=root/'parent.bin';ref=root/'parent.csv'
            a.write_bytes(b'bit exact');b.write_bytes(b'bit exact')
            job=dict(sequence='test',qp='22',frames='3',error_info='pass',fixed_predictor='r3_risk_guard',bitstream=str(a))
            with ref.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(job));w.writeheader();w.writerow({**job,'bitstream':str(b)})
            self.assertEqual(len(compare_streams([job],ref)),1)
            b.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed bitstream'):compare_streams([job],ref)
            with self.assertRaisesRegex(ValueError,'Missing successful'):compare_streams([{**job,'qp':'37'}],ref)

if __name__=='__main__':unittest.main()
