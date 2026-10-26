import unittest
import benchmark_rules as B
import rule_suite as R

class BenchmarkTests(unittest.TestCase):
 def make_rows(self):
  rules=R.catalogue()[:3];rows=[]
  for s in ('A','B','C','D'):
   for q in (22,27,32,37):
    for o in ('R13-1','R13-2'):
     for j,c in enumerate(rules):
      gain=0 if j==0 else .1 if j==1 else 10 if s=='A' else -.2
      rows.append(dict(sequence=s,qp=q,origin=o,component='all',method=c['id'],gain_bits_per_nonzero=gain))
  return rules,rows
 def test_balanced_source_mean(self):
  rules,rows=self.make_rows()
  for r in rows:
   if r['method']==rules[1]['id']:r['gain_bits_per_nonzero']=.1 if r['origin']=='R13-1' else -.01
  pairs,*_=B.describe_and_select(rows,rules)
  for p in pairs:
   if p['method']==rules[1]['id']:self.assertAlmostEqual(p['balanced_gain_bits_per_nonzero'],.045)
 def test_missing_origin_rejected(self):
  rules,rows=self.make_rows();rows.pop()
  with self.assertRaisesRegex(ValueError,'Missing origin'):B.describe_and_select(rows,rules)
 def test_heldout_label_not_selection(self):
  rules,rows=self.make_rows();pairs,seq,ranking,folds=B.describe_and_select(rows,rules)
  self.assertEqual(ranking[0]['method'],rules[2]['id'])
  a=next(f for f in folds if f['held_out_sequence']=='A')
  self.assertEqual(a['selected_method'],rules[1]['id'])
  self.assertAlmostEqual(a['held_out_gain_bits_per_nonzero'],.1)
  for f in folds:self.assertNotIn(f['held_out_sequence'],f['training_sequences'].split(';'))
 def test_duplicate_origin_rejected(self):
  rules,rows=self.make_rows();rows.append(rows[0].copy())
  with self.assertRaisesRegex(ValueError,'Duplicate'):B.describe_and_select(rows,rules)
 def test_null_is_not_zero(self):
  rules,rows=self.make_rows()
  for r in rows:
   if r['sequence']=='A' and r['origin']=='R13-2':r['gain_bits_per_nonzero']=None
  pairs,seq,ranking,folds=B.describe_and_select(rows,rules)
  self.assertTrue(all(p['balanced_gain_bits_per_nonzero'] is None for p in pairs if p['sequence']=='A'))
  self.assertTrue(all(r['supported_sequences']==3 for r in ranking))
  self.assertEqual(folds,[])
 def test_swapped_origins_no_effect(self):
  rules,rows=self.make_rows();a=B.describe_and_select(rows,rules)
  for r in rows:r['origin']='R13-2' if r['origin']=='R13-1' else 'R13-1'
  self.assertEqual(a,B.describe_and_select(rows,rules))

if __name__=='__main__':unittest.main(verbosity=2)
